from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.imports.helpers import create_consignment_item_object, create_consignment_object, create_payment_object

from app.imports.serializers import serialize_consignment

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
        user = authorize(user_payload, ["admin", "manager", "entry operator"], db)

        # Create objects to add in daatabase
        consignment = create_consignment_object(consignment_data, user)
        consignment_payments = create_payment_object(consignment_data)
        consignment_items = create_consignment_item_object(consignment_data)

        consignment.items = consignment_items
        consignment.payments = consignment_payments

        db.add(consignment)
        db.commit()
        db.refresh(consignment)

        return {
            "status_code":201,
            "detail":"Consignment created",
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
 