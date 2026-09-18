from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_IMPORTS
from app.imports.helpers import assert_group_writable, GroupFrozenError, SERVER_RESOLVED_ITEM_FIELDS, legacy_payment_consignment_id, payments_belong_to_this_batch, updated_fields, updated_payments, updated_addenda, updated_items, new_items_to_add, new_payments_to_add, new_addenda_to_add, apply_updates, add_in_consignment_change_history,add_in_eta_revision_history, add_in_status_change_history, delete_missing, stamp_landed_cost_audit, recompute_derived, apply_item_master_values, sync_order_items, split_item_payload, apply_item_updates, apply_group_updates, reconcile_allocation, AllocationError

from app.imports.helpers import (
    fetch_consignment, is_closed, CLOSED_STATUS_VALUE,
    item_current_values,
)
from app.imports.models import ConsignmentItem, Payment, PaymentAddendum
from app.imports.serializers import serialize_consignment, serialize_many
from app.notifications.emit import emit
from app.notifications.lifecycle import notify_status_changed, notify_completed
from datetime import date
import logging
from app.imports.order_view import (
    order_branch_name, order_supplier_name, reference_label,
)

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# NOTIFY ON A MAJOR ETA SLIP
#
# More than a week later than the ETA it replaced. Below that, an ETA moving
# is ordinary traffic and interrupting an executive with it would train them
# to ignore the channel.
#
# ONLY A SLIP, NEVER A PULL-IN. An ETA moving EARLIER is good news and is not
# an alert, so the comparison is signed rather than an absolute difference.
#
# WATCHES `eta`, NOT `eta_works`. Both are recorded in EtaRevisionHistory, but
# `eta` is the one that actually moves — 163 of the 164 revisions in the data
# are against it — and it is already what serializers.build_system_remarks
# treats as THE ETA chain when it writes "1st ETA ... 2nd ETA ...". Watching
# both would also mean two notifications for one save whenever a revision
# touched each of them.
#-----------------------------------------------------

MAJOR_ETA_SLIP_DAYS = 7


def _as_date(value):
    """Dates arrive as `date` from the ORM but as an ISO string out of JSON."""
    if isinstance(value, date):
        return value

    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])

    return None


def _notify_major_eta_slip(db, updation_dict, consignment):
    """Raise imports.eta_slipped_major, if this update slipped the ETA badly.

    WRAPPED, like every emit path. emit() cannot raise, but the work that
    builds its payload can — a missing supplier relation, an unparseable
    date — and this runs AFTER the commit. An exception escaping here would
    turn a consignment that saved perfectly well into a 500 for the operator,
    which is precisely the coupling notifications are not allowed to have.
    """
    try:
        change = updation_dict.get("eta")

        if not change:
            return

        old_eta = _as_date(change.get("old_value"))
        new_eta = _as_date(change.get("new_value"))

        # No previous ETA means this is the first one recorded, not a slip.
        if old_eta is None or new_eta is None:
            return

        slip_days = (new_eta - old_eta).days

        if slip_days <= MAJOR_ETA_SLIP_DAYS:
            return

        emit(
            db,
            "imports.eta_slipped_major",
            payload={
                # Same reference the reports and list screens show.
                "consignment_no": reference_label(consignment),
                "supplier": order_supplier_name(consignment) or "unknown supplier",
                "old_eta": old_eta.isoformat(),
                "new_eta": new_eta.isoformat(),
                "slip_days": slip_days,
            },
            entity_type="consignment",
            entity_id=consignment.id,
            # The indexed column, not a template variable — it is what a feed
            # is narrowed by.
            branch=order_branch_name(consignment),
            # One notification per consignment per landed-on ETA: re-saving
            # the same revision, or two people saving it at once, is one
            # event. Revising AGAIN to a different date is a new one.
            dedupe_key=f"imports.eta_slipped_major:{consignment.id}:{new_eta.isoformat()}",
        )

    except Exception:
        logger.exception(
            "Could not raise the ETA-slip notification for consignment %s — "
            "swallowed; the update itself is already committed",
            getattr(consignment, "id", None),
        )

#---------------------------------------
# THE LIFECYCLE STATUS EVENT
#
# Fires on the CHANGE, not on the save. `updation_dict` only carries a field
# when the diff engine found it actually different, so a wizard step that
# posts the whole draft back with the same status produces nothing here —
# which is what keeps every draft save from becoming a notification.
#
# COMPLETION SUPPRESSES THE PAIRED STATUS CHANGE. Reaching "Arrived at Works"
# IS a status change, so the naive reading emits both and tells one person the
# same thing twice, one line apart. The completion is the more informative of
# the two, so it is emitted INSTEAD.
#
# "Order Cancelled" is deliberately NOT a completion. It is terminal — the
# list groups it under Closed — but the consignment did not finish, it stopped,
# and calling that "completed" in somebody's feed would misreport what
# happened. It emits an ordinary status change.
#---------------------------------------

def _notify_status_lifecycle(db, updation_dict, consignment):
    try:
        change = updation_dict.get("current_status")

        if not change:
            return

        old_status = change.get("old_value")
        new_status = change.get("new_value")

        if not new_status or old_status == new_status:
            return

        reference = reference_label(consignment)
        branch = order_branch_name(consignment)

        if new_status == CLOSED_STATUS_VALUE:
            notify_completed(
                db, "imports", consignment.id,
                reference=reference,
                party=order_supplier_name(consignment) or "unknown supplier",
                status=new_status,
                branch=branch,
            )
            return

        notify_status_changed(
            db, "imports", consignment.id,
            reference=reference,
            old_status=old_status,
            new_status=new_status,
            branch=branch,
        )

    except Exception:
        logger.exception(
            "Could not raise the lifecycle notification for consignment %s — "
            "swallowed; the update itself is already committed",
            getattr(consignment, "id", None),
        )


def posted_item_payloads(consignment, consignment_data):
    """{ConsignmentItem instance: the order-line half of what was posted for it}.

    Keyed by INSTANCE rather than by id, because that is what
    `sync_order_items` matches on - on an update its collection is a mix of
    rows that existed, rows just added and rows soft-deleted, and position
    means nothing across those three.

    Only items the client actually sent are included. A line absent from the
    payload keeps whatever its order line already holds, which is what a
    partial save should do.

    A KEY THE CLIENT DID NOT SET IS DROPPED, for the fields in
    `SERVER_RESOLVED_ITEM_FIELDS`. THIS IS THE SECOND WRITER OF THOSE COLUMNS
    AND IT HAD TO LEARN THE SAME RULE.

    `updated_items` already skips them in the DIFF, and that was not enough:
    `sync_order_item_from_line` writes `ORDER_ITEM_LINE_FIELDS` straight from
    this payload with `if field in line_payload`, and `model_dump()` includes
    every schema field whether or not the client sent it. So a payload omitting
    `price_basis` - which is NOT NULL - arrived here as an explicit None and
    produced

        UPDATE consignment_order_items SET price_basis = NULL
        NotNullViolation

    a 500 on an ordinary save, found by running `tests.batch_fixture` against a
    tree where only the diff had been guarded. One rule, both writers.
    """
    by_id = {item.id: item for item in consignment.items if item.id is not None}

    payloads = {}
    for schema in consignment_data.items:
        item = by_id.get(schema.id)
        if item is None:
            continue
        posted = schema.model_fields_set
        dumped = {
            key: value for key, value in schema.model_dump().items()
            if key not in SERVER_RESOLVED_ITEM_FIELDS or key in posted
        }
        _line_fields, order_item_fields = split_item_payload(dumped)
        payloads[item] = order_item_fields

    return payloads


@router.put("/{consignment_id}")
def update_consignment(
        consignment_data : ConsignmentSchema, 
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, CAN_EDIT_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        # A closed consignment (status reached "Arrived at works") is locked
        # for everyone until an admin reopens it.
        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This consignment is closed. An admin must reopen it before it can be edited."
            )

        # THREE DICTS, BECAUSE A CONSIGNMENT IS THREE ROWS NOW. The group's
        # changes are diffed against the GROUP, not against a stale copy on the
        # batch; the order-line fields are header-level in the payload and fan
        # out to every line, so they carry no single old value to diff.
        updation_dict, group_updates, order_item_header = updated_fields(
            consignment, consignment_data, db
        )
        new_items = new_items_to_add(consignment, consignment_data)
        item_updates = updated_items(consignment, consignment_data, db)
        # STEP 4 IS BATCH 1's - see helpers.payments_belong_to_this_batch, and
        # the note at `posted_payments` below. Computed here because the new
        # payments and the payment diff have to be suppressed too: a later batch
        # posting the order's list back would otherwise show up as "no change"
        # only by luck.
        payments_editable = payments_belong_to_this_batch(consignment)

        new_payments = new_payments_to_add(consignment_data) if payments_editable else []
        payment_updates = (
            updated_payments(consignment, consignment_data, db) if payments_editable else []
        )

        # ADDENDA RIDE THE SAME PREDICATE. They are LC-level like payments, they
        # sit inside the same step, and they arrive in the same payload from the
        # same disabled fieldset - so a later batch posting the order's addenda
        # back must be ignored for exactly the reason its payments are.
        new_addenda = new_addenda_to_add(consignment_data) if payments_editable else []
        addenda_updates = (
            updated_addenda(consignment, consignment_data, db) if payments_editable else []
        )

        # Deleting missing items and payments

        present_item_ids = [
            item.id
            for item in consignment_data.items
            if item.id is not None
        ]

        # STEP 4 IS BATCH 1's - the requirements say payments are done once per
        # consignment, on the founding batch. The wizard disables the step on a
        # later batch, but a disabled fieldset stops typing and not posting, so
        # the array still arrives. IGNORED here rather than accepted: accepting
        # is only safe while the posted values happen to match what the order
        # already holds, and a client bug would otherwise rewrite an order's
        # payment history from batch 2. Same condition the front end uses -
        # see helpers.payments_belong_to_this_batch.
        posted_payments = list(consignment_data.payments) if payments_editable else []

        present_payment_ids = [
            payment.id
            for payment in posted_payments
            if payment.id is not None
        ]

        posted_addenda = list(consignment_data.addenda or []) if payments_editable else []

        present_addendum_ids = [
            addendum.id
            for addendum in posted_addenda
            if addendum.id is not None
        ]

        deleted_items = delete_missing(present_item_ids, ConsignmentItem,
                                       ConsignmentItem.consignment_id, consignment.id,
                                       ConsignmentItem.id, db)
        # Only when this batch owns the step. On a later batch nothing was
        # posted and nothing may be removed - passing the empty list through
        # `delete_missing` would soft-delete the ORDER's whole payment history.
        deleted_payments = (
            delete_missing(present_payment_ids, Payment,
                           Payment.batch_group_id, consignment.batch_group_id,
                           Payment.id, db)
            if payments_editable else []
        )
        # Same guard, same reason: an empty list from a batch that may not edit
        # the step would erase the ORDER's whole addenda history.
        deleted_addenda = (
            delete_missing(present_addendum_ids, PaymentAddendum,
                           PaymentAddendum.batch_group_id, consignment.batch_group_id,
                           PaymentAddendum.id, db)
            if payments_editable else []
        )


        # Adding new items and payments
        created_items = []
        new_item_payloads = {}
        for item_schema in new_items:
            line_fields, order_item_fields = split_item_payload(item_schema.model_dump())
            item = ConsignmentItem(**line_fields)
            consignment.items.append(item)
            created_items.append(item)
            new_item_payloads[item] = order_item_fields
            # Record who entered any landed-cost figure supplied on a new line.
            stamp_landed_cost_audit(item, user, item.elc is not None, item.alc is not None)

        # BEFORE THE FLUSH, because order_item_id is NOT NULL: a line added just
        # above has no order line above it yet, and the flush below would insert
        # it with a NULL and fail. Runs a second time further down, once the
        # field updates have actually landed on the lines.
        sync_order_items(consignment, db, payloads=new_item_payloads,
                         header_fields=order_item_header)

        created_payments = []
        for payment_schema in new_payments:
            payment_dict = payment_schema.model_dump()
            payment = Payment(**payment_dict)
            # ON THE ORDER, with the orphaned column filled by its one writer.
            payment.consignment_id = (
                legacy_payment_consignment_id(consignment.batch_group)
                or consignment.id
            )
            consignment.batch_group.payments.append(payment)
            created_payments.append(payment)

        created_addenda = []
        for addendum_schema in new_addenda:
            addendum = PaymentAddendum(**addendum_schema.model_dump())
            # ON THE ORDER, and with no orphaned column to fill - the table is
            # new, so nothing like `legacy_payment_consignment_id` applies.
            consignment.batch_group.addenda.append(addendum)
            created_addenda.append(addendum)

        db.flush()

        # Adding changes in consignment change history and eta revisions and status updates
        # created_items goes through item_current_values for the same reason
        # deleted_items does (app/imports/helpers.py) - serialize_many walks the
        # mapper and the item fields have left it. Payments keep serialize_many.
        add_in_consignment_change_history(
            updation_dict, [item_current_values(i) for i in created_items],
            serialize_many(created_payments), deleted_items, deleted_payments,
            item_updates, payment_updates, consignment, user, db,
            group_updates=group_updates,
            # Keyword-only, so the three cannot be swapped with the unlabelled
            # run above them - see the note on the function.
            new_addenda_added=serialize_many(created_addenda),
            deleted_addenda=deleted_addenda,
            addenda_updates=addenda_updates,
        )

        add_in_eta_revision_history(updation_dict, consignment, user, db)
        add_in_status_change_history(updation_dict, consignment, user, db)

        # Applying updates - to the batch, and to the ORDER above it. A group
        # field posted by the wizard is written here and nowhere else; it used
        # to be written onto the consignment and mirrored across afterwards.
        apply_updates(updation_dict, consignment)
        if group_updates and consignment.batch_group is not None:
            apply_group_updates(group_updates, consignment.batch_group, user)

        # THE CLOSED LOCK IS WRITTEN HERE, AND ONLY HERE.
        #
        # Reaching "Arrived at works" closes the consignment: the goods are at
        # the factory, so it is finished whether or not anyone marks it so.
        # /submit used to be the only place is_locked was ever set to True and
        # no longer sets it at all, so if this line is ever deleted the closed
        # lock ceases to exist rather than moving somewhere else.
        #
        # PLACEMENT IS LOAD-BEARING, in two ways:
        #
        #   - AFTER apply_updates, because the new status has to be on the
        #     record before is_closed() can see it.
        #   - AFTER the is_locked guard at the top of this route, or the very
        #     request that closes the consignment would reject itself.
        #
        # Setting it when it is already true is a no-op, so a later edit that
        # somehow reaches a locked record cannot un-close it.
        if is_closed(consignment):
            consignment.is_locked = True

        consignment_items_map = {item.id : item for item in consignment.items}

        consignment_payments_map = {
            payment.id: payment
            for payment in (consignment.batch_group.payments if consignment.batch_group else [])
        }

        # The id is read, not popped, so the change history's copy of these
        # dicts keeps its id and a revert can still find the line.
        for updated_item in item_updates:
            item_id = updated_item.get("id")
            old_item = consignment_items_map.get(item_id)
            if old_item:
                apply_item_updates(updated_item, old_item)
                # Stamp the landed-cost audit only for the figure that changed.
                if "elc" in updated_item or "alc" in updated_item:
                    stamp_landed_cost_audit(old_item, user, "elc" in updated_item, "alc" in updated_item)

        for updated_payment in payment_updates:
            payment_id = updated_payment.get("id")
            old_payment = consignment_payments_map.get(payment_id)
            if old_payment:
                apply_updates(updated_payment, old_payment)

        consignment_addenda_map = {
            addendum.id: addendum
            for addendum in (consignment.batch_group.addenda if consignment.batch_group else [])
        }

        for updated_addendum in addenda_updates:
            old_addendum = consignment_addenda_map.get(updated_addendum.get("id"))
            if old_addendum:
                apply_updates(updated_addendum, old_addendum)

        # A line whose code is in the item master takes its name and
        # specification from there, whatever the payload said — applied after
        # the line updates land, so it is the stored value that gets corrected.
        apply_item_master_values(consignment, db)

        # AFTER the line updates and the master correction, so the order line
        # mirrors what the line actually ends up holding. This is the call that
        # matters for an EDIT: a changed quantity or a soft-deleted line would
        # otherwise leave `allocated_quantity` describing quantities the lines
        # no longer carry, which is the drift the over-allocation CHECK cannot
        # see and `post_load`'s "Allocation totals" check exists to catch.
        #
        # PASSED THE POSTED ITEM PAYLOADS, and that is not belt and braces.
        # This call used to receive only `header_fields`, which was fine while
        # every order-line field was written by `apply_item_updates` from the
        # diff. `ordered_quantity` broke that: with no payload in hand,
        # `resolve_ordered_quantity` falls through to "an order with one batch
        # follows its line" and overwrites an explicitly posted order quantity
        # with the line's. Handing it the payload means case 1 - the client
        # said so - wins, here as it does on create.
        #
        # (`order_item_id` is validated separately - `resolve_order_line`
        # reads it off the line's own column, so it is checked however it
        # arrived.)
        sync_order_items(consignment, db, payloads=posted_item_payloads(
            consignment, consignment_data), header_fields=order_item_header)

        # THE ALLOCATION INVARIANT. Changing a line's quantity IS
        # re-allocation, so an ordinary edit goes through the same locked check
        # the batch-create route does - a route that enforces the rule while
        # the edit beside it walks round the rule is worth nothing.
        #
        # AFTER the line updates and the order-line sync, so the sum it reads
        # back out of the database is the one this save actually leaves behind.
        # It takes the order's row locks first (see app/imports/allocation.py),
        # which is also why the group's own UPDATE from apply_group_updates
        # above has not been flushed yet: order lines before the group row,
        # always, or two concurrent saves deadlock against each other.
        reconcile_allocation(db, consignment.batch_group_id)

        # Recompute + store the derived money totals and per-line variance from
        # the now-updated lines and rate.
        recompute_derived(consignment)

        db.commit()
        db.refresh(consignment)

        # AFTER the commit, deliberately. The ETA revision is durable by this
        # point, so nothing the notification does can undo it — and emit()
        # holds its own session, so it could not reach this transaction even
        # if it were still open.
        _notify_major_eta_slip(db, updation_dict, consignment)
        _notify_status_lifecycle(db, updation_dict, consignment)

        return {
            "status_code":200,
            "detail":"Consignment updated",
            "data":serialize_consignment(consignment, db)
        }

    except GroupFrozenError as e:
        # 423, THE SAME STATUS THE ROW LOCK RETURNS, so the front end's existing
        # "this record is closed" handling applies unchanged and there is no
        # second locked-state vocabulary to learn (design 3.9).
        #
        # NOTE WHAT IS NOT HERE: an admin bypass. Tier 1 refuses an admin too,
        # and this is the only rule in the application where is_admin does not
        # pass - every other check in authorize() lets an admin through
        # unconditionally. That asymmetry is deliberate: a rate money has moved
        # against is a historical fact rather than a permission. Anyone
        # "fixing" it here should read helpers.frozen_columns_for first.
        db.rollback()
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
            headers=None,
        )

    except AllocationError as e:
        # 422 naming the item and the overage. Raising a bare 500 here would
        # tell an operator who has typed a quantity too large that the system
        # is broken, rather than that the number is.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.update_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 