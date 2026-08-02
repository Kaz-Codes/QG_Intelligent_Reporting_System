from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.cross_module import find_trucking_jobs
from app.trucking.serializers import serialize_consignment as serialize_trucking

#-----------------------------------------------------
# TRUCKING JOBS FOR AN IMPORT CONSIGNMENT
#
# The reverse of the FOB handoff: which trucking jobs were created from this
# import consignment (source "from-import-fob", source_ref = its id).
#-----------------------------------------------------

@router.get("/{consignment_id}/trucking-jobs")
def get_trucking_jobs(request : Request, consignment_id : int):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        jobs = find_trucking_jobs(db, "from-import-fob", consignment_id)

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
