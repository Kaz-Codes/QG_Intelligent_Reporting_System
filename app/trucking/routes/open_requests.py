from app.trucking.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_TRUCKING
from app.cross_module import derive_open_requests

#-----------------------------------------------------
# OPEN TRUCKING REQUESTS
#
# The cross-module inbox: logistics orders handed off with sent_to_trucking and
# import consignments bought FOB, minus the ones a trucking job has already
# taken. Each carries a snapshot the "New Trucking Job" form pre-fills from, so
# the operator never re-keys what the originating record already holds.
#-----------------------------------------------------

@router.get("/open-requests")
def open_requests(request : Request):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_TRUCKING, db)

        requests = derive_open_requests(db)

        return {
            "status_code": 200,
            "detail": "Open trucking requests fetched",
            "data": requests,
            "total": len(requests),
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
