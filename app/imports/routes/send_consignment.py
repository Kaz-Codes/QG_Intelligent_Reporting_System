from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS
from app.imports.helpers import fetch_consignment
from app.imports.serializers import serialize_consignment
from app.enums import Incoterm
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# HAND A CONSIGNMENT OVER TO LOGISTICS / TRUCKING
#
# The three modules are one flow, and this is where imports pushes into the
# other two. Sending is an explicit ACT, not something inferred: a consignment
# bought FOB is merely eligible to be sent (QG arranges the onward legs), it is
# not automatically anyone else's work. That is why the trucking inbox reads
# sent_to_trucking_at and not the incoterm — see cross_module.derive_open_requests.
#
# The record stays visible everywhere afterwards. It keeps its own row in
# imports, appears under logistics' Service Jobs, and sits in trucking's open
# requests until a trucking job takes it — after which the JOB is the link back
# (GET /consignments/{id}/trucking-jobs), which is why a taken request drops off
# that queue rather than lingering.
#
# Idempotent by design: sending again just re-stamps the time. The front end
# disables the button once sent, so this is a safety net, not a workflow.
#-----------------------------------------------------


def _send(request, consignment_id, field, label):
    db = SessionLocal()

    try:
        user_payload = authenticate(request)

        # Sending is an edit to the consignment's own hand-off state, so it
        # takes the same permission as adding or editing one.
        user = authorize(user_payload, [CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        # A closed consignment is finished work; handing it onward now would
        # create downstream work against a record nobody may edit.
        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This consignment is closed. An admin must reopen it first."
            )

        # FOB is what makes a consignment eligible: on other incoterms the
        # supplier arranges the onward legs, so there is nothing to hand over.
        if consignment.incoterm != Incoterm.FOB.value:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only FOB consignments can be sent onward — on other "
                    "incoterms the supplier arranges shipping and inland movement."
                )
            )

        setattr(consignment, field, datetime.now(timezone.utc))

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code": 200,
            "detail": f"Consignment sent to {label}",
            "data": serialize_consignment(consignment, db)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.send_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()


@router.post("/{consignment_id}/send-to-logistics")
def send_to_logistics(request: Request, consignment_id: int):
    return _send(request, consignment_id, "sent_to_logistics_at", "Logistics")


@router.post("/{consignment_id}/send-to-trucking")
def send_to_trucking(request: Request, consignment_id: int):
    return _send(request, consignment_id, "sent_to_trucking_at", "Trucking")
