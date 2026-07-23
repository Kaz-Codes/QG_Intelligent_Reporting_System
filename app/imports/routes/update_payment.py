from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, get_payment, prefix_fields, record_change,
    sent_fields,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import PaymentSchema
from app.imports.serializers import serialize_payment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 4 OF THE WIZARD, EDIT A PAYMENT
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Normally used to move a row from Unpaid to
# Paid once the bank confirms it, and to fill
# in the reference and the rate it actually
# settled at.
#-------------------------------------------

@router.put("/{consignment_id}/payments/{payment_id}")
async def update_payment(consignment_id : int,
                         payment_id : int,
                         payment_schema : PaymentSchema,
                         request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        payment = get_payment(payment_id, consignment.id, db)

        updates = sent_fields(payment_schema)
        previous_values, new_values = apply_updates(payment, updates)

        record_change(
            consignment.id,
            prefix_fields("payment", payment.id, previous_values),
            prefix_fields("payment", payment.id, new_values),
            user.id,
            db
        )

        db.commit()
        db.refresh(payment)

        return {
            "status": 200,
            "message": "Payment updated",
            "data": serialize_payment(payment, consignment.exchange_rate)
        }

    except HTTPException:
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
