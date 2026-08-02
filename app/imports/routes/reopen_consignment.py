from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.imports.helpers import fetch_consignment
from app.imports.serializers import serialize_consignment


#-----------------------------------------------------
# REOPEN A CLOSED CONSIGNMENT
#
# A consignment closes and locks when its status reaches "Arrived at works".
# Only an admin can reopen it, which clears the lock and lets it be edited
# again. The status is left as it is; reopening is only about the lock, so an
# admin can correct a closed record without the status having to move.
#-----------------------------------------------------

@router.post("/{consignment_id}/reopen")
def reopen_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Only an admin may reopen a closed consignment)
        user = authorize(user_payload, ["admin"], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        if not consignment.is_locked:
            raise HTTPException(
                status_code=400,
                detail="This consignment is not closed"
            )

        consignment.is_locked = False

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Consignment reopened",
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
