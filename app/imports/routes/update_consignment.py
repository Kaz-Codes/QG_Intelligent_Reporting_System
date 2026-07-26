from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.imports.helpers import updated_fields, updated_payments, updated_items, new_items_to_add, new_payments_to_add, verify_entry_ownership, apply_updates, add_in_consignment_change_history,add_in_eta_revision_history, add_in_status_change_history

from app.imports.helpers import fetch_consignment
from app.imports.models import ConsignmentItem, Payment
from app.imports.serializers import serialize_consignment

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
        user = authorize(user_payload, ["admin", "manager", "entry operator"], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )
        
        verify_entry_ownership(consignment, user, db)

        updation_dict = updated_fields(consignment, consignment_data, db)
        new_items = new_items_to_add(consignment, consignment_data)
        item_updates = updated_items(consignment, consignment_data, db)
        new_payments = new_payments_to_add(consignment_data)
        payment_updates = updated_payments(consignment, consignment_data, db)

        # Adding changes in consignment change history and eta revisions and status updates
        add_in_consignment_change_history(updation_dict, new_items, new_payments, item_updates, payment_updates, consignment, user, db)

        add_in_eta_revision_history(updation_dict, consignment, user, db)
        add_in_status_change_history(updation_dict, consignment, user, db)

        # Applying updates
        apply_updates(updation_dict, consignment)

        consignment_items_map = {item.id : item for item in consignment.items}

        consignment_payments_map = {payment.id : payment for payment in consignment.payments}

        for updated_item in item_updates:
            item_id = updated_item.pop("id")
            old_item = consignment_items_map.get(item_id)
            if old_item:
                apply_updates(updated_item, old_item)

        for updated_payment in payment_updates:
            payment_id = updated_payment.pop("id")
            old_payment = consignment_payments_map.get(payment_id)
            if old_payment:
                apply_updates(updated_payment, old_payment)


        # Adding new items and payments
        for item_schema in new_items:
            item_dict = item_schema.model_dump()
            item = ConsignmentItem(**item_dict)
            consignment.items.append(item)

        for payment_schema in new_payments:
            payment_dict = payment_schema.model_dump()
            payment = Payment(**payment_dict)
            consignment.payments.append(payment)

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
 