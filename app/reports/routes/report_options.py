from typing import Optional

from fastapi import HTTPException, Query, Request

from app.reports.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.reports.helpers import selected_types, build_options

ROLES = ["admin", "manager", "viewer", "entry operator"]


#-----------------------------------------------------
# GET /reports/options
#
# The dropdown values for the report filters (items, suppliers, branches,
# categories), distinct and scoped to the selected types, built from the whole
# tables so every value that exists is offered — not just those on a page.
#-----------------------------------------------------

@router.get("/options")
def reports_options(
    request: Request,
    types: Optional[list[str]] = Query(None),
):
    db = SessionLocal()
    try:
        authorize(authenticate(request), ROLES, db)

        options = build_options(db, selected_types(types))

        return {
            "status_code": 200,
            "detail": "Report options fetched",
            "data": options,
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
