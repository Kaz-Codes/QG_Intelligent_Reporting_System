from app.imports.consignment_routes.router import router
from app.imports.schemas.consignment_schema import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth import authorize, authenticate
from app.imports.consignment_helpers import create_consignment_item_object, create_consignment_object, create_payment_object, verify_entry_ownership

from app.imports.consignment_serializers import serialize_consignment
from app.imports.consignment_helpers import fetch_consignment

@router.put("/")
def update_consignment(
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

        consignment = fetch_consignment(db, consignment_data.consignment_id)

        verify_entry_ownership(consignment)

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
 