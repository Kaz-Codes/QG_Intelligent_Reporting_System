from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS
from app.logistics.helpers import fetch_consignment, verify_entry_ownership, submission_errors, is_closed
from app.logistics.serializers import serialize_consignment
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# SUBMIT AN ORDER
#
# The strict counterpart to save-draft. Opt-in: the front end may keep saving
# drafts (the normal create/update) and never call this. Submitting runs the
# full rule set and only flips record_state to "submitted" if nothing is
# missing.
#
# Submitting does not lock the order by itself — a submitted order at any
# other status stays editable. But an order closes once it is BOTH submitted
# AND "Delivered" (helpers.is_closed), so if it was already at that status
# when submitted, this is the moment it actually locks. The update route no
# longer locks at all. Mirrors imports.
#-----------------------------------------------------

@router.post("/{consignment_id}/submit")
def submit_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        user_payload = authenticate(request)

        user = authorize(user_payload, [CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This order is closed. An admin must reopen it first."
            )

        verify_entry_ownership(consignment, user, db)

        errors = submission_errors(consignment)

        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "This order cannot be submitted yet.",
                    "errors": errors
                }
            )

        consignment.record_state = "submitted"

        if is_closed(consignment):
            consignment.is_locked = True

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Order submitted",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.submit_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
