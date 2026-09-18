from fastapi import Request, HTTPException
from sqlalchemy import select
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_LOGISTICS
from app.database import SessionLocal
from app.logistics.models import LogisticsConsignment
from app.logistics.routes.router import router
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# MO DUPLICATE CHECK — for the Step 1 Excel import feature only.
#
# "An order with this MO already exists" is being treated as a straight
# duplicate right now, because there is no real batching on the backend yet
# (mo_no is a nullable, non-unique grouping key with no batch concept behind
# it in this schema — see the comment on mo_no in models.py). ONE MO CURRENTLY
# MEANS ONE ORDER, BY CONVENTION, NOT BY CONSTRAINT.
#
# WHEN REAL BATCHING IS DESIGNED, THIS CHECK MUST CHANGE. At that point an
# existing MO will mean "this is batch 2" (a valid, expected case), not
# "duplicate" — this endpoint's meaning will need to be redefined (e.g. keyed
# on MO + batch number, or a content hash of the imported file) exactly the
# way imports' ConsignmentBatchGroup/ConsignmentOrderItem split handled the
# same shift. Do not carry this endpoint's current behavior forward
# unexamined once batching exists.
#
# Registered before GET /{consignment_id} in routes/__init__.py, so
# GET /logistics/check-mo is not read as GET /logistics/{consignment_id} with
# consignment_id="check-mo" (which would 422 on the int param).
#-----------------------------------------------------

@router.get("/check-mo")
def check_mo(request: Request, mo_no: str):
    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_ADD_LOGISTICS, db)

        mo_no = mo_no.strip()
        if not mo_no:
            raise HTTPException(status_code=422, detail="mo_no is required")

        exists = db.execute(
            select(LogisticsConsignment.id)
            .where(LogisticsConsignment.mo_no == mo_no)
            .where(LogisticsConsignment.is_deleted == False)  # noqa: E712
            .limit(1)
        ).first() is not None

        return {"status_code": 200, "detail": "MO checked", "data": {"exists": exists}}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        logger.exception("Unhandled error in app.logistics.routes.check_mo")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
