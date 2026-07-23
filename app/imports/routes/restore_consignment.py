from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import apply_updates, get_consignment, record_change
from app.imports.permissions import CAN_RESTORE, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# PUT A DELETED CONSIGNMENT BACK
# (ADMIN, MANAGER)
#
# The other half of the soft delete. Because
# deleting only set a flag, undoing it is just
# clearing that flag, and everything hanging
# off the consignment is still there.
#
# This is the one read that asks for a deleted
# row on purpose.
#-------------------------------------------

@router.post("/{consignment_id}/restore")
async def restore_consignment(consignment_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_RESTORE, db)

        consignment = get_consignment(consignment_id, db, include_deleted=True)

        if not consignment.is_deleted:
            raise HTTPException(
                status_code=400,
                detail="Consignment is not deleted"
            )

        previous_values, new_values = apply_updates(consignment, {
            "is_deleted": False,
            "deleted_at": None,
            "deleted_by_id": None
        })

        record_change(
            consignment.id, previous_values, new_values, user.id, db,
            is_revert=True
        )

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Consignment restored",
            "data": serialize_consignment(consignment, date.today())
        }

    except HTTPException:
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
