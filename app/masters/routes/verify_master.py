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
# CONFIRM AN INLINE-CREATED RECORD
# (ADMIN, MANAGER)
#
# The review queue holds records somebody
# added mid consignment. Editing one confirms
# it, but sometimes the details were already
# right and there is nothing to change, so
# this marks it verified on its own without
# forcing an edit.
#-------------------------------------------

@router.post("/{master}/{row_id}/verify")
async def verify_master(master : str, row_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_EDIT_MASTER, db)

        config = get_master_config(master)
        row = get_row(config["model"], row_id, db)

        if row.is_verified:
            raise HTTPException(
                status_code=400,
                detail="Record is already verified"
            )

        row.is_verified = True

        db.commit()
        db.refresh(row)

        counts = used_counts(master, [row.id], db)

        return {
            "status": 200,
            "message": "Record verified",
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
