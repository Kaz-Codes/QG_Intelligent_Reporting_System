from app.dashboard.inventory.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_INVENTORY_DASHBOARD
from app.dashboard.inventory.helpers import (
    fetch_filtered_stock, consumption_map, reorder_level_map, option_lists,
    purchase_vs_issuance_by_category, issuance_windows, latest_purchase_map,
    issuance_totals_by_item, issuance_in_period, issuance_item_references,
    issuance_coverage,
)
from app.dashboard.period import resolve_period, serialize_period
from app.dashboard.inventory.serializers import serialize_rows, serialize_inventory_dashboard
from app.dashboard.inventory.calculations import (
    STOCK_STATUSES, REORDER_STATUSES, MOVEMENT_CLASSES,
)
from typing import Optional
from datetime import date


@router.get("/inventory")
def inventory_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    reorder_status : Optional[list[str]] = Query(None),
    movement : Optional[list[str]] = Query(None),
    category : Optional[list[str]] = Query(None),
    branch : Optional[list[str]] = Query(None),
    item : Optional[list[str]] = Query(None),
    search : Optional[str] = None,
    # The ISSUANCE window. Stock itself is a snapshot with no date at all, but
    # what was issued genuinely happens in a period — both bounds omitted means
    # the current month, exactly like every other window on the system.
    date_from : Optional[date] = None,
    date_to : Optional[date] = None,
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only, so every role sees them.
        authorize(user_payload, CAN_VIEW_INVENTORY_DASHBOARD, db)

        period_from, period_to, period_kind = resolve_period(date_from, date_to)

        consumption = consumption_map(db)
        reorder_levels = reorder_level_map(db)
        issuance, windows = issuance_windows(db)
        purchase_map = latest_purchase_map(db)
        item_issuance = issuance_totals_by_item(db, branch)

        stocks = fetch_filtered_stock(db, branch, item, category, search)
        rows = serialize_rows(
            stocks, consumption, reorder_levels, issuance,
            purchase_map, windows["from_12m"],
        )

        # Stock status and reorder status are derived, so they are filtered here.
        if status:
            wanted = set(status)
            rows = [r for r in rows if r["stock_status"] in wanted]

        if reorder_status:
            wanted = set(reorder_status)
            rows = [r for r in rows if r["reorder_status"] in wanted]

        # Movement is derived too, so it is filtered here alongside the others.
        if movement:
            wanted = set(movement)
            rows = [r for r in rows if r["movement"] in wanted]

        data = {
            # The "view data" table is being removed from the dashboard, so
            # only the aggregates + filter option lists are returned. The
            # serialized rows are still built above, but only to feed the
            # aggregates, not shipped over the wire. Dropdown values come from
            # cheap DISTINCT queries, not from loading the whole table.
            **serialize_inventory_dashboard(
                rows, windows,
                issuance=issuance_in_period(db, period_from, period_to, branch),
                issuance_references=issuance_item_references(
                    db, period_from, period_to, branch
                ),
                purchase_map=purchase_map,
                item_issuance=item_issuance,
            ),
            # The issuance window actually used, and what the issuance table
            # holds — so an empty month says "latest data is ..." rather than
            # showing a confident Rs 0.
            "period": serialize_period(period_from, period_to, period_kind),
            "coverage": issuance_coverage(db, period_from, period_to),
            # KPI document. Built from purchases + issuance rather than the
            # stock rows above, so it takes only the category filter — see the
            # helper for why branch cannot be applied to both sides.
            "purchase_vs_issuance_by_category": purchase_vs_issuance_by_category(
                db, category
            ),
            "statuses": STOCK_STATUSES,
            "reorder_statuses": REORDER_STATUSES,
            "movement_classes": MOVEMENT_CLASSES,
            **option_lists(db),
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
