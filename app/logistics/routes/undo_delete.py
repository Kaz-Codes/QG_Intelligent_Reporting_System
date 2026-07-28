from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.logistics.helpers import fetch_consignment
from app.logistics.serializers import serialize_consignment

@router.post("/undo-delete/{consignment_id}")
def undo_delete(
        consignment_id : int,
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
                detail="Order not found"
            )

        if not consignment.is_deleted:
            raise HTTPException(
                status_code=400,
                detail="Order is not deleted"
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
            "detail":"Order restored",
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
