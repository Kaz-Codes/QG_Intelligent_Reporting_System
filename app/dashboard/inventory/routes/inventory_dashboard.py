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
    issuance_coverage, latest_issuance_date,
)
from app.dashboard.period import resolve_period, serialize_period
from app.dashboard.inventory.serializers import serialize_rows, serialize_inventory_dashboard
from app.dashboard.inventory.calculations import (
    STOCK_STATUSES, REORDER_STATUSES, MOVEMENT_CLASSES,
)
from typing import Optional
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)


def _build_stock_rows(branch, item, category, search):
    """Group A: the stock-row pipeline. Each step feeds the next, so this
    stays sequential internally — the concurrency win is running this whole
    chain on one thread while Group B runs on another, each with its own
    session. serialize_rows runs in here too, not after rejoining the main
    thread: it needs stock.item (joinedload'd by fetch_filtered_stock) while
    this session is still open.
    """
    db = SessionLocal()
    try:
        latest = latest_issuance_date(db)
        consumption = consumption_map(db, latest=latest)
        reorder_levels = reorder_level_map(db)
        issuance, windows = issuance_windows(db, latest=latest)
        purchase_map = latest_purchase_map(db)
        item_issuance = issuance_totals_by_item(db, branch, latest=latest)
        stocks = fetch_filtered_stock(db, branch, item, category, search)
        rows = serialize_rows(
            stocks, consumption, reorder_levels, issuance,
            purchase_map, windows["from_12m"],
        )
        return rows, windows, purchase_map, item_issuance
    finally:
        db.close()


def _build_group_b(period_from, period_to, branch, category):
    """Group B: fully independent of Group A and of each other — one worker
    thread, five calls sequential within it but concurrent with Group A."""
    db = SessionLocal()
    try:
        return {
            "purchase_vs_issuance_by_category": purchase_vs_issuance_by_category(db, category),
            "coverage": issuance_coverage(db, period_from, period_to),
            "issuance": issuance_in_period(db, period_from, period_to, branch),
            "issuance_references": issuance_item_references(db, period_from, period_to, branch),
            "option_lists": option_lists(db),
        }
    finally:
        db.close()


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

        # Group A (the stock-row pipeline) and Group B (five independent
        # calls) run concurrently, each on its own SessionLocal() — never the
        # route's own `db` above, which stays reserved for authorize(). Every
        # future's .result() is awaited below (via as_completed), including
        # ones that finish without error, so an exception in either group
        # still propagates to the except Exception handler unchanged.
        jobs = {
            "group_a": (_build_stock_rows, (branch, item, category, search)),
            "group_b": (_build_group_b, (period_from, period_to, branch, category)),
        }
        results = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(fn, *args): name for name, (fn, args) in jobs.items()}
            for future in as_completed(futures):
                results[futures[future]] = future.result()

        rows, windows, purchase_map, item_issuance = results["group_a"]
        group_b = results["group_b"]

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
                issuance=group_b["issuance"],
                issuance_references=group_b["issuance_references"],
                purchase_map=purchase_map,
                item_issuance=item_issuance,
            ),
            # The issuance window actually used, and what the issuance table
            # holds — so an empty month says "latest data is ..." rather than
            # showing a confident Rs 0.
            "period": serialize_period(period_from, period_to, period_kind),
            "coverage": group_b["coverage"],
            # KPI document. Built from purchases + issuance rather than the
            # stock rows above, so it takes only the category filter — see the
            # helper for why branch cannot be applied to both sides.
            "purchase_vs_issuance_by_category": group_b["purchase_vs_issuance_by_category"],
            "statuses": STOCK_STATUSES,
            "reorder_statuses": REORDER_STATUSES,
            "movement_classes": MOVEMENT_CLASSES,
            **group_b["option_lists"],
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
        logger.exception("Unhandled error in app.dashboard.inventory.routes.inventory_dashboard")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
