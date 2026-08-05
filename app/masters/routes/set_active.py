from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import get_row, used_counts
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_MASTER
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException

#-------------------------------------------
# DEACTIVATE OR REACTIVATE A MASTER
# (ADMIN, MANAGER)
#
# This is the soft delete for masters. A
# record is never removed, it is only turned
# off, so consignments already pointing at it
# keep working and it stays in past reports.
# Turning it off just keeps it out of the
# dropdowns on new data entry.
#
# Reactivate is the same switch the other way,
# for when something was deactivated by
# mistake or is needed again.
#-------------------------------------------

@router.post("/{master}/{row_id}/deactivate")
async def deactivate_master(master : str, row_id : int, request: Request):
    return _set_active(master, row_id, False, request)


@router.post("/{master}/{row_id}/reactivate")
async def reactivate_master(master : str, row_id : int, request: Request):
    return _set_active(master, row_id, True, request)


def _set_active(master, row_id, active, request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_EDIT_MASTER, db)

        config = get_master_config(master)
        row = get_row(config["model"], row_id, db)

        row.is_active = active

        db.commit()
        db.refresh(row)

        counts = used_counts(master, [row.id], db)

        return {
            "status": 200,
            "message": "Record reactivated" if active else "Record deactivated",
            "data": serialize(master, row, counts.get(row.id, 0))
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
