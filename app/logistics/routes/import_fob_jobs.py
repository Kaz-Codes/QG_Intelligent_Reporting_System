from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS
from app.cross_module import derive_import_fob_jobs
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# IMPORT-FOB SERVICE JOBS
#
# The read-only half of logistics' Service Jobs tab: import consignments that
# imports explicitly handed over (sent_to_logistics_at). Their home stays
# imports — the item details were entered there — so these are a read-through,
# never copied into logistics, and the row links back to the source
# consignment rather than opening anything here.
#
# The other half of that tab (customer rework) IS a logistics record: a
# logistics_consignments row with job_kind='rework', served by the normal list.
#-----------------------------------------------------

@router.get("/import-fob-jobs")
def import_fob_jobs(request: Request):
    db = SessionLocal()

    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS, db)

        jobs = derive_import_fob_jobs(db)

        return {
            "status_code": 200,
            "detail": "Import FOB service jobs fetched",
            "data": jobs,
            "total": len(jobs),
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.import_fob_jobs")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
