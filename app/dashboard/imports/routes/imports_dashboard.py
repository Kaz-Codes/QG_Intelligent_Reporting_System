from app.dashboard.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.imports.helpers import fetch_consignments
from app.dashboard.imports.serializers import serialize_imports_dashboard

@router.get("/imports")
def imports_dashboard(request : Request):

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
            "detail":"Imports dashboard fetched",
            "data":serialize_imports_dashboard(consignments)
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
