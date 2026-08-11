"""
GET /dashboard/imports/references — page 2 and beyond of a KPI's record list.

Same filters as /dashboard/imports, plus `key` naming which list and a page
number. The dashboard payload already carries page 1 and the true total; this
serves the rest. See app/dashboard/references for the contract and for why the
whole list is not shipped up front.
"""

from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS_DASHBOARD
from app.dashboard.period import resolve_period
from app.dashboard.references import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.dashboard.imports.helpers import fetch_filtered_consigments, fetch_shaft_lines
from app.dashboard.imports import calculations as calc
from app.dashboard.imports.routes.router import router

# key -> a function taking the filtered consignments and returning that page.
#
# A fixed registry, not a dynamic lookup: an unknown key is a 400 rather than a
# way to reach a query the screen was never meant to run.
BUILDERS = {
    "total":      lambda cs, p, s: calc.references(cs, p, s),
    "in_process": lambda cs, p, s: calc.references(
        [c for c in cs if c.current_status not in calc.TERMINAL_STATUSES], p, s),
    "arrived":    lambda cs, p, s: calc.references(
        [c for c in cs if c.current_status == calc.CLOSED_STATUS], p, s),
    "cancelled":  lambda cs, p, s: calc.references(
        [c for c in cs if c.current_status in calc.TERMINAL_STATUSES
         and c.current_status != calc.CLOSED_STATUS], p, s),
    "delayed":    lambda cs, p, s: calc.delivery_delay(cs, p, s)["delayed_references"],
    # `shafts` is handled separately below: it is a LINE-level list and is
    # selected from the lines, not from the consignments.
    "efs":        lambda cs, p, s: calc.efs_split(cs, p, s)["efs_references"],
}


@router.get("/imports/references")
def imports_references(
    request: Request,
    key: str = Query(..., description=" | ".join(sorted(list(BUILDERS) + ["shafts"]))),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),

    # Exactly the filters /dashboard/imports takes, so the screen forwards what
    # it already holds and page 2 describes the same set as page 1.
    work: Optional[str] = None,
    supplier: Optional[str] = None,
    country: Optional[str] = None,
    item_category: Optional[str] = None,
    status: Optional[str] = None,
    mode_of_shipment: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    date_field: Optional[str] = None,
    search: Optional[str] = None,
    shafts_only: bool = False,
):
    if key not in BUILDERS and key != "shafts":
        raise HTTPException(status_code=400, detail=f"Unknown reference key '{key}'")

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_IMPORTS_DASHBOARD, db)

        period_from, period_to, _kind = resolve_period(date_from, date_to)

        if key == "shafts":
            return {
                "status_code": 200,
                "detail": "Imports references fetched",
                "data": calc.line_references(
                    fetch_shaft_lines(db, period_from, period_to, date_field,
                                      work, supplier, country),
                    page, page_size,
                ),
            }

        consignments = fetch_filtered_consigments(
            db, work, status, item_category, supplier, country,
            from_date, to_date, mode_of_shipment,
            period_from, period_to,
            date_field=date_field, search=search, shafts_only=shafts_only,
        )

        return {
            "status_code": 200,
            "detail": "Imports references fetched",
            "data": BUILDERS[key](consignments, page, page_size),
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
