from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from app.trucking.helpers import fetch_consignment
from app.trucking.serializers import serialize_consignment

@router.post("/undo-delete/{consignment_id}")
def undo_delete(
        consignment_id : int,
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # ADMIN ONLY, and necessarily so: the only way to see a deleted record
        # is the admin-only `include_deleted` view, so nobody else could reach
        # this in the first place.
        user = require_admin(user_payload, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        if not consignment.is_deleted:
            raise HTTPException(
                status_code=400,
                detail="Trucking job is not deleted"
            )

        # Undo the soft delete and clear the delete stamps
        consignment.is_deleted = False
        consignment.deleted_by_id = None
        consignment.deleted_at = None

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Trucking job restored",
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
