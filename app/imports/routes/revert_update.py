from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.imports.helpers import fetch_consignment, fetch_consignment_history, fetch_latest_consignment_history, revert
from app.imports.serializers import serialize_consignment
from datetime import datetime, timezone

@router.put("/revert-update/{consignment_id}/{change_history_id}")
def revert_update(
        consignment_id : int,
        change_history_id : int, 
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, ["admin", "manager"], db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        consignment_history = fetch_consignment_history(db, consignment.id, change_history_id)
        latest_consignment_history = fetch_latest_consignment_history(db, consignment.id)

        if not consignment_history or not latest_consignment_history:
            raise HTTPException(
                status_code=404,
                detail="Consignment history not found"
            )


        if consignment_history.is_reverted:
            raise HTTPException(
                status_code=200,
                detail="Changes have already been reverted"
            )
        
        if consignment_history.id != latest_consignment_history.id:
            raise HTTPException(
                status_code=400,
                detail="Revert latest changes first"
            )                     

        # Make the consignment history reverted so that user cannot revert it again
        consignment_history.is_reverted = True
        consignment_history.reverted_by_id = user.id
        consignment_history.reverted_at = datetime.now(timezone.utc)

        # Revert updates
        revert(consignment_history, consignment, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status_code":200,
            "detail":"Consignment reverted",
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
 