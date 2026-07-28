from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import get_row, used_counts
from app.auth.authorize_user import authorize
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException

#-------------------------------------------
# ONE MASTER RECORD (EVERY ROLE)
#
# Used when the edit drawer opens a single
# row. Comes back with the same "used in"
# count the list shows.
#-------------------------------------------

@router.get("/{master}/{row_id}")
async def get_master(master : str, row_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin", "manager", "entry operator", "viewer"], db)

        config = get_master_config(master)
        row = get_row(config["model"], row_id, db)

        counts = used_counts(master, [row.id], db)

        return {
            "status": 200,
            "message": "Record fetched",
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
