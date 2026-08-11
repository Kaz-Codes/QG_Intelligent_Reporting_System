"""
GET /dashboard/logistics/references — page 2 and beyond of a KPI's record list.

ONE ENDPOINT, THREE TABS. Logistics is three screens over three different
sources, so the caller passes `tab` alongside `key` and this routes on it. One
endpoint rather than three near-identical ones, and one place where each tab's
filters and its reference keys have to agree — which is what stops a list
drifting away from the tile it opened from.

Both `tab` and `key` are matched against fixed registries; anything else is a
400, never a way to reach a query the screen was not meant to run.
"""

from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS_DASHBOARD
from app.dashboard.period import resolve_period
from app.dashboard.references import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.dashboard.logistics import references as refs
from app.dashboard.logistics.calculations import (
    DELIVERED, PACKED, TRANSPORT_DELIVERED, TRANSPORT_IN_PROGRESS,
    transport_status,
)
from app.dashboard.logistics.helpers import (
    fetch_filtered_orders, fetch_filtered_packages, fetch_filtered_trucking,
)
from app.dashboard.logistics.routes.router import router

KEYS = {
    "shipments": ("orders", "delivered", "not_linked"),
    "packing": ("packages", "packed"),
    "transport": ("jobs", "delivered", "in_progress"),
}


@router.get("/logistics/references")
def logistics_references(
    request: Request,
    tab: str = Query(..., description="shipments | packing | transport"),
    key: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),

    # The window, shared by all three tabs.
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    date_field: Optional[str] = None,
    search: Optional[str] = None,

    # shipments
    status: Optional[list[str]] = Query(None),
    stage: Optional[list[str]] = Query(None),
    shipping_line: Optional[list[str]] = Query(None),
    country: Optional[list[str]] = Query(None),
    customer: Optional[list[str]] = Query(None),
    order_type: Optional[list[str]] = Query(None),
    etd_from: Optional[date] = None,
    etd_to: Optional[date] = None,

    # packing
    works: Optional[list[str]] = Query(None),
    product_category: Optional[list[str]] = Query(None),
    business_type: Optional[list[str]] = Query(None),
    packing_from: Optional[date] = None,
    packing_to: Optional[date] = None,

    # transport
    movement_type: Optional[list[str]] = Query(None),
    source: Optional[list[str]] = Query(None),
    payment_status: Optional[list[str]] = Query(None),
    transporter: Optional[list[str]] = Query(None),
    exec_from: Optional[date] = None,
    exec_to: Optional[date] = None,
):
    if tab not in KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown tab '{tab}'")
    if key not in KEYS[tab]:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reference key '{key}' for tab '{tab}'",
        )

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_LOGISTICS_DASHBOARD, db)

        period_from, period_to, _kind = resolve_period(date_from, date_to)

        if tab == "shipments":
            orders = fetch_filtered_orders(
                db, status, shipping_line, country, customer,
                etd_from, etd_to, search,
                period_from, period_to, date_field, order_type,
            )
            # Stage is a derived roll-up of the status, so it is applied here —
            # exactly as the dashboard does, or the list counts a different set.
            if stage:
                from app.dashboard.logistics.calculations import shipment_stage
                wanted = set(stage)
                orders = [o for o in orders if shipment_stage(o) in wanted]

            data = refs.shipment_sets(orders, DELIVERED, page, page_size)[key]

        elif tab == "packing":
            packages = fetch_filtered_packages(
                db, status, works, product_category, business_type, customer,
                packing_from, packing_to, search,
                period_from, period_to, date_field,
            )
            data = refs.packing_sets(packages, PACKED, page, page_size)[key]

        else:
            jobs = fetch_filtered_trucking(
                db, movement_type, source, payment_status, transporter,
                exec_from, exec_to, search,
                period_from, period_to, date_field,
            )
            data = refs.transport_sets(
                jobs, transport_status, TRANSPORT_DELIVERED,
                TRANSPORT_IN_PROGRESS, page, page_size,
            )[key]

        return {
            "status_code": 200,
            "detail": "Logistics references fetched",
            "data": data,
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
