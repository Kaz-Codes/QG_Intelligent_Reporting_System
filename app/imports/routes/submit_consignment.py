from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS
from app.imports.helpers import fetch_consignment
from app.imports.serializers import serialize_consignment
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# SUBMIT A CONSIGNMENT
#
# Submit means ONE thing now: "I am finished editing this". It sets
# `record_state` to "submitted" and does nothing else. It runs no rule set, it
# can no longer 422, and it does not lock anything.
#
# BOTH of those used to be true and both were deliberately removed:
#
#   - The rule set (helpers.submission_errors) is deleted. Data quality moves
#     to the input layer; see the long note in app/imports/helpers.py.
#
#   - The lock. This route was the ONLY place is_locked was ever set to True in
#     imports, and it is now set by the UPDATE route on the transition into
#     "Arrived at works" instead. Deleting the write from here without adding
#     it there would have removed the closed lock from the system silently.
#
# So submitting is no longer irreversible, and the confirmation dialog that
# used to sit on it has moved to the status change, which is where the
# irreversible act now lives.
#
# The closed lock still guards THIS route: a closed consignment cannot be
# re-submitted until an admin reopens it.
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
        logger.exception("Unhandled error in app.imports.routes.submit_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
