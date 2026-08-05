from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS
from app.cross_module import find_trucking_jobs
from app.trucking.serializers import serialize_consignment as serialize_trucking

#-----------------------------------------------------
# TRUCKING JOBS FOR A LOGISTICS ORDER
#
# The reverse of "Send to Trucking": which trucking jobs were created from this
# logistics order (source "from-logistics", source_ref = its id).
#-----------------------------------------------------

@router.get("/{consignment_id}/trucking-jobs")
def get_trucking_jobs(request : Request, consignment_id : int):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_LOGISTICS, db)

        jobs = find_trucking_jobs(db, "from-logistics", consignment_id)

        return {
            "status_code": 200,
            "detail": "Linked trucking jobs fetched",
            "data": [serialize_trucking(job) for job in jobs],
            "total": len(jobs),
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
