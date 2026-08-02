from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.trucking.helpers import fetch_consignment
from app.trucking.serializers import serialize_consignment


#-----------------------------------------------------
# REOPEN A CLOSED TRUCKING JOB
#
# A job closes and locks once every vehicle is delivered. Only an admin can
# reopen it, which clears the lock and lets it be edited again. The vehicles
# are left as they are; reopening is only about the lock.
#-----------------------------------------------------

@router.post("/{consignment_id}/reopen")
def reopen_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        user_payload = authenticate(request)

        # Only an admin may reopen a closed job
        user = authorize(user_payload, ["admin"], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        if not consignment.is_locked:
            raise HTTPException(
                status_code=400,
                detail="This trucking job is not closed"
            )

        consignment.is_locked = False

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Trucking job reopened",
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
