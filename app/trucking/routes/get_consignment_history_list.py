from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.trucking.helpers import fetch_all_consignment_history, fetch_consignment
from app.trucking.serializers import serialize_consignment_history
from typing import Optional

@router.get("/change-history/{consignment_id}")
def get_consignment_history_list(
    request : Request,
    consignment_id : int,
    include_reverted : Optional[bool] = False
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        consignment_history = fetch_all_consignment_history(db, include_reverted, consignment.id)

        # Serializeing all change histories
        serialized_consignment_history = [
            serialize_consignment_history(history) for history in consignment_history
        ]

        return {
            "status_code":200,
            "detail":"Trucking job history fetched",
            "data":serialized_consignment_history
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
