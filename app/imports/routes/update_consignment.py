from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_IMPORTS
from app.imports.helpers import updated_fields, updated_payments, updated_items, new_items_to_add, new_payments_to_add, verify_entry_ownership, apply_updates, add_in_consignment_change_history,add_in_eta_revision_history, add_in_status_change_history, delete_missing, is_closed, stamp_landed_cost_audit, recompute_derived

from app.imports.helpers import fetch_consignment
from app.imports.models import ConsignmentItem, Payment
from app.imports.serializers import serialize_consignment, serialize_many

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

        verify_entry_ownership(consignment, user, db)

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

        # If this update pushed the status to "Arrived at works" the
        # consignment is now closed, so lock it. The closing update itself
        # goes through (it started from an unlocked state); only later edits
        # are refused, until an admin reopens.
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

        # Recompute + store the derived money totals and per-line variance from
        # the now-updated lines and rate.
        recompute_derived(consignment)

        db.commit()
        db.refresh(consignment)

        return {
            "status_code":200,
            "detail":"Consignment updated",
            "data":serialize_consignment(consignment, db)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 