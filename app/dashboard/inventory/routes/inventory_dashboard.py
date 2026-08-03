from app.dashboard.inventory.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.inventory.helpers import fetch_stock, fetch_filtered_stock, consumption_map, reorder_level_map
from app.dashboard.inventory.serializers import serialize_rows, serialize_inventory_dashboard
from app.dashboard.inventory.calculations import STOCK_STATUSES, REORDER_STATUSES
from typing import Optional


@router.get("/inventory")
def inventory_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    reorder_status : Optional[list[str]] = Query(None),
    category : Optional[list[str]] = Query(None),
    branch : Optional[list[str]] = Query(None),
    item : Optional[list[str]] = Query(None),
    search : Optional[str] = None,
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only, so every role sees them.
        authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        all_stock = fetch_stock(db)
        consumption = consumption_map(db)
        reorder_levels = reorder_level_map(db)

        stocks = fetch_filtered_stock(db, branch, item, category, search)
        rows = serialize_rows(stocks, consumption, reorder_levels)

        # Stock status and reorder status are derived, so they are filtered here.
        if status:
            wanted = set(status)
            rows = [r for r in rows if r["stock_status"] in wanted]

        if reorder_status:
            wanted = set(reorder_status)
            rows = [r for r in rows if r["reorder_status"] in wanted]

        # Filter option lists, built dynamically from the whole table.
        branches = set()
        items = set()
        item_categories = set()

        for stock in all_stock:
            if stock.branch:
                branches.add(stock.branch)
            if stock.item_name:
                items.add(stock.item_name)
            if stock.item and stock.item.category:
                item_categories.add(stock.item.category)

        data = {
            # The "view data" table is being removed from the dashboard, so
            # only the aggregates + filter option lists are returned. The
            # serialized rows are still built above, but only to feed the
            # aggregates, not shipped over the wire.
            **serialize_inventory_dashboard(rows),
            "statuses": STOCK_STATUSES,
            "reorder_statuses": REORDER_STATUSES,
            "branches": sorted(branches),
            "items": sorted(items),
            "item_categories": sorted(item_categories),
        }

        return {
            "status_code": 200,
            "detail": "Inventory dashboard fetched",
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
