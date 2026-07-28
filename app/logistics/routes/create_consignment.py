from app.logistics.routes.router import router
from app.logistics.schemas import LogisticsConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.logistics.helpers import create_consignment_object, fetch_consignment
from app.logistics.serializers import serialize_consignment

@router.post("/")
def create_consignment(
        consignment_data : LogisticsConsignmentSchema,
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, ["admin", "manager", "entry operator"], db)

        # Create object to add in database
        consignment = create_consignment_object(consignment_data, user)

        db.add(consignment)
        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":201,
            "detail":"Order created",
            "data":serialize_consignment(consignment)
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
