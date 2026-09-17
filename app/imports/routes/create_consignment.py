from app.imports.routes.router import router
from app.notifications.lifecycle import notify_created
from app.imports.order_view import reference_label
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS
from app.imports.helpers import legacy_payment_consignment_id, has_something_to_save, EMPTY_DRAFT_MESSAGE, create_consignment_item_object, create_consignment_object, create_payment_object, create_addendum_object, stamp_landed_cost_audit, recompute_derived, apply_item_master_values, new_batch_group, sync_order_items, split_consignment_payload, reconcile_allocation, AllocationError

from app.imports.serializers import serialize_consignment
import logging
from app.imports.order_view import order_branch_name, order_supplier_name

logger = logging.getLogger(__name__)

@router.post("/")
def create_consignment(
        consignment_data : ConsignmentSchema, 
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, CAN_ADD_IMPORTS, db)

        # NOTHING IS SAVED UNTIL THERE IS SOMETHING TO SAVE (requirements line
        # 161). Checked on the payload as posted, before anything is written -
        # a 422 that names what is needed, not a silent no-op, because a save
        # that quietly does nothing is indistinguishable from one that failed.
        #
        # CREATE ONLY. The wizard POSTs once and PUTs after, so the update
        # route is untouched and clearing a field on an existing record stays
        # an ordinary edit.
        if not has_something_to_save(
            consignment_data.model_dump(exclude_none=True)
        ):
            raise HTTPException(status_code=422, detail=EMPTY_DRAFT_MESSAGE)

        # ONE FLAT PAYLOAD, THREE TABLES. The wizard posts a consignment the way
        # an operator thinks of one; splitting it is the server's job now that a
        # batch, its order and its order lines are separate rows.
        header_payload = consignment_data.model_dump(
            exclude_none=True, exclude={"items", "payments", "addenda"}
        )
        _header, group_fields, order_item_header = split_consignment_payload(header_payload)

        consignment = create_consignment_object(consignment_data, user)
        consignment_payments = create_payment_object(consignment_data)
        consignment_addenda = create_addendum_object(consignment_data)

        # Pairs, not objects: each line carries the order-line half of its own
        # payload until sync_order_items writes it.
        item_pairs = create_consignment_item_object(consignment_data)
        consignment_items = [line for line, _ in item_pairs]
        order_item_payloads = {line: fields for line, fields in item_pairs}

        # THE ORDER GOES IN BEFORE THE GOODS DO, and the two flushes inside
        # new_batch_group are the only sequence the constraints allow — see the
        # block comment on that helper. The items are attached AFTERWARDS on
        # purpose: each line needs an order line above it, and an order line
        # cannot exist before the group it hangs off has been written.
        new_batch_group(consignment, user, db, group_fields=group_fields)

        # NOTHING MAY REACH THE DATABASE UNTIL EVERY LINE HAS ITS ORDER LINE.
        #
        # The consignment is already persistent by this point — new_batch_group
        # had to flush it — so assigning a collection on it makes SQLAlchemy
        # read the previous value first, and that read is a lazy load, and a
        # lazy load autoflushes. The items assigned on the first line below are
        # in the session by the time the second line runs, still carrying a NULL
        # order_item_id, and the autoflush that `consignment.payments = ...`
        # provokes inserts them and hits the NOT NULL constraint.
        #
        # Found by driving the real route, not by reasoning about it: the ORM
        # helpers pass on their own and this only appears once a request runs
        # them in this order.
        with db.no_autoflush:
            consignment.items = consignment_items
            # PAYMENTS GO ON THE ORDER. On a create the order is this
            # consignment's own brand-new group, so there is no batch-1 question
            # to ask - `new_batch_group` runs just below and the group is
            # attached by then.
            group = consignment.batch_group
            for payment in consignment_payments:
                # The orphaned NOT NULL column, written by its single writer.
                payment.consignment_id = legacy_payment_consignment_id(group) or consignment.id
                group.payments.append(payment)

            # ADDENDA GO ON THE ORDER TOO, and are simpler than payments here:
            # there is no orphaned NOT NULL column to fill, because the table is
            # new. Nothing like `legacy_payment_consignment_id` exists for them
            # and none should be invented.
            for addendum in consignment_addenda:
                group.addenda.append(addendum)

            # One order line per shipment line, written from the PAYLOAD -
            # the line no longer holds the thirteen columns it used to be
            # mirrored from. `order_item_header` is the consignment-level
            # demand data (requisition/required date, branch) fanned out to
            # every line.
            sync_order_items(consignment, db, payloads=order_item_payloads,
                             header_fields=order_item_header)

            # Record who entered any landed-cost figure supplied at entry.
            for item in consignment_items:
                stamp_landed_cost_audit(item, user, item.elc is not None, item.alc is not None)

        # A line whose code is in the item master takes its name and
        # specification from there, whatever the payload said. The wizard
        # locks those inputs too; this is the part that actually guarantees it.
        apply_item_master_values(consignment, db)

        # apply_item_master_values writes the corrected name and specification
        # straight to the order line now, so there is nothing left to re-mirror
        # and the second sync is gone.

        # THE ALLOCATION INVARIANT, on the create path too.
        #
        # A brand-new order has one batch and no contention, so this can never
        # refuse here today - every line is the whole of its own order line.
        # It runs anyway, because `allocated_quantity` has ONE writer and this
        # is it: leaving create to set it some other way would put a second
        # spelling of the sum in the codebase, and the two would agree right up
        # until one of them changed.
        reconcile_allocation(db, consignment.batch_group_id)

        # Store the derived money totals + per-line variance.
        recompute_derived(consignment)

        # already added by new_batch_group; add() again is a no-op and is left
        # out so the ordering above is not made to look optional.
        db.commit()
        db.refresh(consignment)

        # AFTER the commit. The record is durable by this point, so nothing
        # the notification does can undo it — and emit() holds its own
        # session, so it could not reach this transaction even if it were
        # still open. Fires on the CREATE route only: the wizard saves the
        # same draft repeatedly through PUT, and only this first save is the
        # record starting.
        notify_created(
            db, "imports", consignment.id,
            reference=reference_label(consignment),
            party=order_supplier_name(consignment) or "unknown supplier",
            branch=order_branch_name(consignment),
        )

        return {
            "status_code":201,
            "detail":"Consignment created",
            "data":serialize_consignment(consignment, db)
        }

    except AllocationError as e:
        # A readable 422 naming the item and the overage, not a 500. It cannot
        # fire on a brand-new order (see the call site) but the handler is here
        # because the call is, and a refusal that reaches the client as
        # "Internal server error" is a refusal nobody can act on.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.create_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 