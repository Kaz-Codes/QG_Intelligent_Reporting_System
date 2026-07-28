from app.dashboard.whole.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.whole.helpers import fetch_all
from app.dashboard.whole.serializers import serialize_overall_dashboard

@router.get("/overview")
def overview_dashboard(request : Request):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action). Dashboards are read only, so every role sees them.
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        data = fetch_all(db)

        return {
            "status_code":200,
            "detail":"Overall dashboard fetched",
            "data":serialize_overall_dashboard(data)
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
