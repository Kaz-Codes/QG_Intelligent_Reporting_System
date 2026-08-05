from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.helpers import fetch_consignment_history, fetch_consignment
from app.imports.serializers import serialize_consignment_history

@router.get("/change-history/{consignment_id}/{consignment_history_id}")
def get_consignment_history(
    request : Request,
    consignment_id : int,
    consignment_history_id : int,
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, CAN_VIEW_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )
        
        consignment_history = fetch_consignment_history(db, consignment.id, consignment_history_id)

        if not consignment_history:
            raise HTTPException(
                status_code=404,
                detail="Consignment history not found"
            )
      
        return {
            "status_code":200,
            "detail":"Consignment history fetched",
            "data":serialize_consignment_history(consignment_history)
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
 