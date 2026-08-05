from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_DELETE_IMPORTS
from app.imports.helpers import fetch_consignment, verify_entry_ownership
from app.imports.serializers import serialize_consignment

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
        user = authorize(user_payload, CAN_DELETE_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        # Non-admins may only undo the deletion of their own records.
        verify_entry_ownership(consignment, user, db)

        consignment.is_deleted = False
        consignment.deleted_by_id = None
        consignment.deleted_at = None

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
 