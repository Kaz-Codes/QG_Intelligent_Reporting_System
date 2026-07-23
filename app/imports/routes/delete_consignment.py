from datetime import datetime, timezone

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.enums import ChangeType
from app.imports.helpers import apply_updates, get_consignment, record_change
from app.imports.permissions import CAN_DELETE, allow
from app.imports.routes.router import router
from fastapi import Request, HTTPException

#-------------------------------------------
# DELETE A CONSIGNMENT (ADMIN, MANAGER)
#
# Nothing is ever really deleted. This only
# sets a flag, so the row stays and an admin or
# a manager can put it back, and so the item
# lines, payments and history hanging off it
# are not destroyed along with it. Closed and
# deleted records have to stay available to
# reports.
#
# It disappears from the list immediately
# either way, because every read filters the
# flag out.
#-------------------------------------------

@router.delete("/{consignment_id}")
async def delete_consignment(consignment_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_DELETE, db)

        consignment = get_consignment(consignment_id, db)

        previous_values, new_values = apply_updates(consignment, {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc),
            "deleted_by_id": user.id
        })

        record_change(
            consignment.id, previous_values, new_values, user.id, db,
            change_type=ChangeType.DELETE.value
        )

        db.commit()

        return {
            "status": 200,
            "message": "Consignment deleted",
            "data": {"id": consignment.id, "is_deleted": True}
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
