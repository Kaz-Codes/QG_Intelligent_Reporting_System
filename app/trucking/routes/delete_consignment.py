from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_DELETE_TRUCKING
from app.trucking.helpers import fetch_consignment, verify_entry_ownership
from app.trucking.serializers import serialize_consignment
from datetime import datetime, timezone

@router.delete("/{consignment_id}")
def delete_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_DELETE_TRUCKING, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        # Non-admins may only delete their own records.
        verify_entry_ownership(consignment, user, db)

        # Nothing is really deleted, only flagged
        consignment.is_deleted = True
        consignment.deleted_by_id = user.id
        consignment.deleted_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Trucking job deleted",
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
