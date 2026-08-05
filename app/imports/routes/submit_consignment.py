from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS
from app.imports.helpers import fetch_consignment, verify_entry_ownership, submission_errors
from app.imports.serializers import serialize_consignment


#-----------------------------------------------------
# SUBMIT A CONSIGNMENT
#
# The strict counterpart to save-draft. A draft saves with anything filled
# (the normal create/update). Submitting runs the full rule set and only
# flips record_state to "submitted" if nothing is missing. The rules live in
# helpers.submission_errors, mirroring the front end, and are enforced here
# server-side because template/client validation is never the boundary.
#
# Submitting does NOT lock the record — a submitted consignment is still
# editable. Only closing it (status "Arrived at works") locks it.
#-----------------------------------------------------

@router.post("/{consignment_id}/submit")
def submit_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, [CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        # A closed consignment is locked; it cannot be re-submitted until an
        # admin reopens it.
        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This consignment is closed. An admin must reopen it first."
            )

        verify_entry_ownership(consignment, user, db)

        errors = submission_errors(consignment)

        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "This consignment cannot be submitted yet.",
                    "errors": errors
                }
            )

        consignment.record_state = "submitted"

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Consignment submitted",
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
