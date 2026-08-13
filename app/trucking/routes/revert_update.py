from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_TRUCKING
from app.trucking.helpers import (
    fetch_consignment, fetch_consignment_history,
    fetch_latest_consignment_history, revert, verify_entry_ownership,
    resolve_transporter_id,
)
from app.trucking.serializers import serialize_consignment
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
        user = authorize(user_payload, CAN_EDIT_TRUCKING, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        # Non-admins may only revert changes on their own records.
        verify_entry_ownership(consignment, user, db)

        consignment_history = fetch_consignment_history(db, consignment.id, change_history_id)
        latest_consignment_history = fetch_latest_consignment_history(db, consignment.id)

        if not consignment_history or not latest_consignment_history:
            raise HTTPException(
                status_code=404,
                detail="Trucking job history not found"
            )

        if consignment_history.is_reverted:
            raise HTTPException(
                status_code=400,
                detail="Changes have already been reverted"
            )

        if consignment_history.id != latest_consignment_history.id:
            raise HTTPException(
                status_code=400,
                detail="Revert latest changes first"
            )

        # Mark the history reverted so it cannot be reverted again
        consignment_history.is_reverted = True
        consignment_history.reverted_by_id = user.id
        consignment_history.reverted_at = datetime.now(timezone.utc)

        # Revert updates
        revert(consignment_history, consignment, db)

        # transporter_id is DERIVED from transporter_name and is not itself in
        # the change history, so reverting the name has to re-derive the id —
        # or a reverted job would show one transporter and link to another.
        resolve_transporter_id(consignment, db)

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Trucking job reverted",
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
