from app.imports.routes.router import router
from app.notifications.lifecycle import notify_created
from app.imports.helpers import consignment_reference
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS
from app.imports.helpers import create_consignment_item_object, create_consignment_object, create_payment_object, stamp_landed_cost_audit, recompute_derived, apply_item_master_values, new_batch_group, sync_order_items

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

        # Create objects to add in daatabase
        consignment = create_consignment_object(consignment_data, user)
        consignment_payments = create_payment_object(consignment_data)
        consignment_items = create_consignment_item_object(consignment_data)

        # THE ORDER GOES IN BEFORE THE GOODS DO, and the two flushes inside
        # new_batch_group are the only sequence the constraints allow — see the
        # block comment on that helper. The items are attached AFTERWARDS on
        # purpose: each line needs an order line above it, and an order line
        # cannot exist before the group it hangs off has been written.
        new_batch_group(consignment, user, db)

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
            consignment.payments = consignment_payments

            # One order line per shipment line. While a group holds one batch
            # the two mirror each other, which is what the migration
            # back-filled for every consignment that already existed.
            sync_order_items(consignment, db)

            # Record who entered any landed-cost figure supplied at entry.
            for item in consignment_items:
                stamp_landed_cost_audit(item, user, item.elc is not None, item.alc is not None)

        # A line whose code is in the item master takes its name and
        # specification from there, whatever the payload said. The wizard
        # locks those inputs too; this is the part that actually guarantees it.
        apply_item_master_values(consignment, db)

        # Again, so the order line carries the name and specification the master
        # just corrected rather than whatever the payload said.
        sync_order_items(consignment, db)

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
            reference=consignment_reference(consignment),
            party=order_supplier_name(consignment) or "unknown supplier",
            branch=order_branch_name(consignment),
        )

        return {
            "status_code":201,
            "detail":"Consignment created",
            "data":serialize_consignment(consignment, db)
        }

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
 