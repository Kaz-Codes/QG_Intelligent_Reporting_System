from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_IMPORTS
from app.imports.helpers import updated_fields, updated_payments, updated_items, new_items_to_add, new_payments_to_add, apply_updates, add_in_consignment_change_history,add_in_eta_revision_history, add_in_status_change_history, delete_missing, stamp_landed_cost_audit, recompute_derived, apply_item_master_values, sync_order_items, sync_batch_group

from app.imports.helpers import (
    fetch_consignment, consignment_reference, is_closed, CLOSED_STATUS_VALUE,
)
from app.imports.models import ConsignmentItem, Payment
from app.imports.serializers import serialize_consignment, serialize_many
from app.notifications.emit import emit
from app.notifications.lifecycle import notify_status_changed, notify_completed
from datetime import date
import logging
from app.imports.order_view import order_branch_name, order_reference, order_supplier_name

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
                "consignment_no": order_reference(consignment),
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

        reference = consignment_reference(consignment)
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

        updation_dict = updated_fields(consignment, consignment_data, db)
        new_items = new_items_to_add(consignment, consignment_data)
        item_updates = updated_items(consignment, consignment_data, db)
        new_payments = new_payments_to_add(consignment_data)
        payment_updates = updated_payments(consignment, consignment_data, db)

        # Deleting missing items and payments

        present_item_ids = [
            item.id
            for item in consignment_data.items
            if item.id is not None
        ]

        present_payment_ids = [
            payment.id
            for payment in consignment_data.payments
            if payment.id is not None
        ]

        deleted_items = delete_missing(consignment, present_item_ids, ConsignmentItem.id, db, ConsignmentItem)
        deleted_payments = delete_missing(consignment, present_payment_ids, Payment.id, db, Payment)


        # Adding new items and payments
        created_items = []
        for item_schema in new_items:
            item_dict = item_schema.model_dump()
            item = ConsignmentItem(**item_dict)
            consignment.items.append(item)
            created_items.append(item)
            # Record who entered any landed-cost figure supplied on a new line.
            stamp_landed_cost_audit(item, user, item.elc is not None, item.alc is not None)

        # BEFORE THE FLUSH, because order_item_id is NOT NULL: a line added just
        # above has no order line above it yet, and the flush below would insert
        # it with a NULL and fail. Runs a second time further down, once the
        # field updates have actually landed on the lines.
        sync_order_items(consignment, db)

        created_payments = []
        for payment_schema in new_payments:
            payment_dict = payment_schema.model_dump()
            payment = Payment(**payment_dict)
            consignment.payments.append(payment)
            created_payments.append(payment)

        db.flush()

        # Adding changes in consignment change history and eta revisions and status updates
        add_in_consignment_change_history(updation_dict, serialize_many(created_items), serialize_many(created_payments), deleted_items, deleted_payments, item_updates, payment_updates, consignment, user, db)

        add_in_eta_revision_history(updation_dict, consignment, user, db)
        add_in_status_change_history(updation_dict, consignment, user, db)

        # Applying updates
        apply_updates(updation_dict, consignment)

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

        consignment_payments_map = {payment.id : payment for payment in consignment.payments}

        # The id is read, not popped, so the change history's copy of these
        # dicts keeps its id and a revert can still find the line.
        for updated_item in item_updates:
            item_id = updated_item.get("id")
            old_item = consignment_items_map.get(item_id)
            if old_item:
                apply_updates(updated_item, old_item)
                # Stamp the landed-cost audit only for the figure that changed.
                if "elc" in updated_item or "alc" in updated_item:
                    stamp_landed_cost_audit(old_item, user, "elc" in updated_item, "alc" in updated_item)

        for updated_payment in payment_updates:
            payment_id = updated_payment.get("id")
            old_payment = consignment_payments_map.get(payment_id)
            if old_payment:
                apply_updates(updated_payment, old_payment)

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
        sync_order_items(consignment, db)

        # AND THE ORDER ABOVE THE BATCH, for the same reason one level up. The
        # group holds the copy of supplier / currency / exchange rate that every
        # dashboard now reads; without this an edit updated the batch and left
        # the group showing the value it was created with, for ever. Only batch
        # 1 writes it — see sync_batch_group.
        sync_batch_group(consignment, db)

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
 