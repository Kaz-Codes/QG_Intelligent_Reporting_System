from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.enums import PaymentStatus
from app.imports.helpers import get_consignment, prefix_fields, record_change, to_json
from app.imports.models import Payment
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import PaymentSchema
from app.imports.serializers import serialize_payment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 4 OF THE WIZARD, RECORD A PAYMENT
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Partial payments are normal and expected, so
# a consignment usually ends up with several
# of these rather than one.
#
# Each payment carries its own exchange rate,
# because instalments made months apart settle
# at different rates and a single consignment
# level rate would misstate what was actually
# paid in PKR. Leave the rate blank and the
# rate booked in step 2 is used instead, and
# the response says which of the two it was.
#-------------------------------------------

@router.post("/{consignment_id}/payments")
async def add_payment(consignment_id : int,
                      payment_schema : PaymentSchema,
                      request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        payment = Payment(
            consignment_id=consignment.id,
            retirement_date=payment_schema.retirement_date,
            value=payment_schema.value,
            exchange_rate=payment_schema.exchange_rate,
            bank_charges=payment_schema.bank_charges,
            status=payment_schema.status or PaymentStatus.UNPAID.value,
            bank_reference=payment_schema.bank_reference
        )

        db.add(payment)
        db.flush()

        record_change(
            consignment.id,
            {},
            prefix_fields("payment", payment.id, {
                "value": to_json(payment.value),
                "status": payment.status,
                "retirement_date": to_json(payment.retirement_date)
            }),
            user.id,
            db
        )

        db.commit()
        db.refresh(payment)

        return {
            "status": 201,
            "message": "Payment recorded",
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
