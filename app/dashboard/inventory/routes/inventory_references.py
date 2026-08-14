"""
GET /dashboard/inventory/references — page 2 and beyond of a KPI's record list.

Same filters as /dashboard/inventory, plus `key` and a page number.

Every list here is a list of ITEMS, folded across the branches that stock them,
because that is what every tile on the screen counts — an item still moving at
one factory is not dead because it sat still at another.
"""

from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_INVENTORY_DASHBOARD
from app.dashboard.period import resolve_period
from app.dashboard.references import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.dashboard.inventory.helpers import (
    fetch_filtered_stock, consumption_map, reorder_level_map, issuance_windows,
    issuance_item_references, latest_purchase_map, issuance_totals_by_item,
)
from app.dashboard.inventory.serializers import serialize_rows
from app.dashboard.inventory import calculations as calc
from app.dashboard.inventory.routes.router import router

# `q` is the OPEN PANEL's own search term — distinct from the `search` query
# param below, which narrows which stock rows are fetched at all.
BUILDERS = {
    "items":         lambda i, p, s, q: calc.item_references(i, page=p, page_size=s, search=q),
    "out_of_stock":  lambda i, p, s, q: calc.item_references(
        calc.items_where(i, lambda x: x["stock_status"] == calc.OUT_OF_STOCK),
        page=p, page_size=s, search=q),
    "below_reorder": lambda i, p, s, q: calc.item_references(
        calc.items_where(i, lambda x: x["stock_status"] == calc.BELOW_REORDER),
        page=p, page_size=s, search=q),
    "fast":          lambda i, p, s, q: calc.item_references(
        calc.items_where(i, lambda x: x["movement"] == calc.MOVE_FAST),
        page=p, page_size=s, search=q),
    "slow":          lambda i, p, s, q: calc.item_references(
        calc.items_where(i, lambda x: x["movement"] == calc.MOVE_SLOW),
        page=p, page_size=s, search=q),
    "dead":          lambda i, p, s, q: calc.item_references(
        calc.items_where(i, lambda x: x["movement"] == calc.MOVE_DEAD),
        page=p, page_size=s, search=q),
}

# Issuance is not derived from the stock rows — it is its own windowed query —
# so it is built separately rather than squeezed into the registry above.
ISSUANCE_KEY = "issuance"


@router.get("/inventory/references")
def inventory_references(
    request: Request,
    key: str = Query(..., description=" | ".join(sorted(list(BUILDERS) + [ISSUANCE_KEY]))),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),

    status: Optional[list[str]] = Query(None),
    reorder_status: Optional[list[str]] = Query(None),
    movement: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    branch: Optional[list[str]] = Query(None),
    item: Optional[list[str]] = Query(None),
    # Narrows which stock rows are fetched at all — the dashboard's own filter
    # bar, unrelated to the panel search below.
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    # Narrows the OPEN PANEL to rows whose visible text contains this, without
    # touching which items were fetched or any other tile on the screen.
    list_search: Optional[str] = None,
):
    if key not in BUILDERS and key != ISSUANCE_KEY:
        raise HTTPException(status_code=400, detail=f"Unknown reference key '{key}'")

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_INVENTORY_DASHBOARD, db)

        period_from, period_to, _kind = resolve_period(date_from, date_to)

        if key == ISSUANCE_KEY:
            return {
                "status_code": 200,
                "detail": "Inventory references fetched",
                "data": issuance_item_references(
                    db, period_from, period_to, branch, page, page_size, list_search
                ),
            }

        consumption = consumption_map(db)
        reorder_levels = reorder_level_map(db)
        issuance, windows = issuance_windows(db)
        purchase_map = latest_purchase_map(db)
        item_issuance = issuance_totals_by_item(db, branch)

        rows = serialize_rows(
            fetch_filtered_stock(db, branch, item, category, search),
            consumption, reorder_levels, issuance,
            purchase_map, windows["from_12m"],
        )

        # The three derived filters, applied exactly as the dashboard applies
        # them — otherwise the list and the tile count different populations.
        if status:
            rows = [r for r in rows if r["stock_status"] in set(status)]
        if reorder_status:
            rows = [r for r in rows if r["reorder_status"] in set(reorder_status)]
        if movement:
            rows = [r for r in rows if r["movement"] in set(movement)]

        items = calc.group_by_item(rows, purchase_map, windows["from_12m"], item_issuance)

        return {
            "status_code": 200,
            "detail": "Inventory references fetched",
            "data": BUILDERS[key](items, page, page_size, list_search),
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
