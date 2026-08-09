from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_OVERVIEW_DASHBOARD
from app.dashboard.whole.calculations import resolve_period
from app.dashboard.whole.serializers import serialize_overview
from app.dashboard.whole.routes.router import router

# Default cut-off for a stock line to count as dead. Exposed as a query param
# rather than fixed: how long stock must sit unissued before it is written off
# is a business judgement, so the caller states it and the backend does not
# quietly decide on their behalf.
DEFAULT_DEAD_STOCK_DAYS = 180


@router.get("/overview")
def overview_dashboard(
    request: Request,
    # Both bounds omitted -> month to date. Either one given -> that custom
    # range. The resolved window comes back in the payload.
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    dead_stock_days: int = Query(DEFAULT_DEAD_STOCK_DAYS, ge=1, le=1825),
):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only; the overview has its own view permission.
        authorize(user_payload, CAN_VIEW_OVERVIEW_DASHBOARD, db)

        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=400,
                detail="date_from cannot be after date_to"
            )

        resolved_from, resolved_to, period_kind = resolve_period(date_from, date_to)

        data = serialize_overview(
            db, resolved_from, resolved_to, period_kind, dead_stock_days
        )

        return {
            "status_code": 200,
            "detail": "Overview dashboard fetched",
            "data": data,
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
