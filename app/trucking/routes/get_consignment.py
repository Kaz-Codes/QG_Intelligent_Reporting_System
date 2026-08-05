from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_TRUCKING
from app.trucking.helpers import fetch_consignment
from app.trucking.serializers import serialize_consignment

@router.get("/{consignment_id}")
def get_consignment(
    request : Request,
    consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_VIEW_TRUCKING, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        return {
            "status_code":200,
            "detail":"Trucking job fetched",
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
