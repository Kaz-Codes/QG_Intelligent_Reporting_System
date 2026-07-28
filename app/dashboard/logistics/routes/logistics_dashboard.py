from app.dashboard.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.logistics.helpers import fetch_consignments
from app.dashboard.logistics.serializers import serialize_logistics_dashboard

@router.get("/logistics")
def logistics_dashboard(request : Request):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action). Dashboards are read only, so every role sees them.
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        consignments = fetch_consignments(db)

        return {
            "status_code":200,
            "detail":"Logistics dashboard fetched",
            "data":serialize_logistics_dashboard(consignments)
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
