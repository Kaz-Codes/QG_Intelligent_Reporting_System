"""
GET /dashboard/purchases/references — page 2 and beyond of a KPI's record list.

Same filters as /dashboard/purchases, plus `key` and a page number.

NOTE THE TWO UNITS. Every KPI on that screen counts ORDERS, so every key here
returns orders — except `delayed_lines`, which is the level BELOW the Delayed
tile: the 454 late lines inside the 247 late orders. They are published
separately and each is labelled, because conflating them is exactly the bug
this pass was opened to fix.
"""

from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_PURCHASES_DASHBOARD
from app.dashboard.period import resolve_period
from app.dashboard.references import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.dashboard.purchases.helpers import fetch_filtered_consignments
from app.dashboard.purchases import calculations as calc
from app.dashboard.purchases.routes.router import router
import logging

logger = logging.getLogger(__name__)

# `q` is the OPEN PANEL's own search term — distinct from the `search` query
# param below, which narrows which purchase LINES are fetched at all.
BUILDERS = {
    # ORDERS — one row per order, matching every KPI's own unit.
    "orders":       lambda o, k, p, s, q: calc.order_references(o, p, s, search=q),
    "on_time":      lambda o, k, p, s, q: calc.order_references(
        calc.orders_with_status(o, calc.STATUS_COMPLETED), p, s, search=q),
    "delayed":      lambda o, k, p, s, q: calc.delayed_references(o, p, s, q),
    "top_supplier": lambda o, k, p, s, q: calc.order_references(
        calc.supplier_orders(o, k["top_supplier"]), p, s, search=q),

    # LINES — the breakdown inside the delayed orders.
    "delayed_lines": lambda o, k, p, s, q: calc.delayed_line_references(o, p, s, q),
}


@router.get("/purchases/references")
def purchases_references(
    request: Request,
    key: str = Query(..., description=" | ".join(sorted(BUILDERS))),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),

    status: Optional[list[str]] = Query(None),
    supplier: Optional[list[str]] = Query(None),
    branch: Optional[list[str]] = Query(None),
    item_category: Optional[list[str]] = Query(None),
    mop: Optional[list[str]] = Query(None),
    sourcing_o: Optional[list[str]] = Query(None),
    po_from_date: Optional[date] = None,
    po_to_date: Optional[date] = None,
    # Narrows which purchase lines are fetched at all — the dashboard's own
    # filter bar, unrelated to the panel search below.
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    date_field: Optional[str] = None,
    # Narrows the OPEN PANEL to rows whose visible text contains this, without
    # touching which orders were fetched or any other tile on the screen.
    list_search: Optional[str] = None,
):
    if key not in BUILDERS:
        raise HTTPException(status_code=400, detail=f"Unknown reference key '{key}'")

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_PURCHASES_DASHBOARD, db)

        period_from, period_to, _kind = resolve_period(date_from, date_to)

        rows = fetch_filtered_consignments(
            db, supplier, branch, item_category, mop, sourcing_o,
            po_from_date, po_to_date, search,
            period_from, period_to, date_field,
        )
        orders = calc.group_orders(rows)

        # The status filter is derived (Pending / Delayed / On Time), so it is
        # applied to the grouped orders here, exactly as the dashboard does.
        if status:
            wanted = set(status)
            orders = [lines for lines in orders if calc.order_status(lines) in wanted]

        return {
            "status_code": 200,
            "detail": "Purchases references fetched",
            "data": BUILDERS[key](orders, calc.kpis(rows, orders), page, page_size, list_search),
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.dashboard.purchases.routes.purchases_references")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
