from app.dashboard.purchases.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_PURCHASES_DASHBOARD
from app.dashboard.purchases.helpers import (
    fetch_filtered_consignments, option_lists, source_coverage,
    DATE_FIELDS, DATE_FIELD_DEFAULT, DATE_FIELD_OPTIONS,
)
from app.dashboard.period import resolve_period, serialize_period
from app.dashboard.purchases.serializers import serialize_purchases_dashboard
from app.dashboard.purchases.calculations import (
    PURCHASE_STATUSES, group_orders, order_status,
)
from typing import Optional
from datetime import date


@router.get("/purchases")
def purchases_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    supplier : Optional[list[str]] = Query(None),
    branch : Optional[list[str]] = Query(None),
    item_category : Optional[list[str]] = Query(None),
    mop : Optional[list[str]] = Query(None),
    sourcing_o : Optional[list[str]] = Query(None),
    po_from_date : Optional[date] = None,
    po_to_date : Optional[date] = None,
    search : Optional[str] = None,
    # The dashboard-wide reporting window. Both omitted -> the current month.
    date_from : Optional[date] = None,
    date_to : Optional[date] = None,
    # Which procurement event the window measures: po_date | purchase.
    date_field : Optional[str] = None,
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only, so every role sees them.
        authorize(user_payload, CAN_VIEW_PURCHASES_DASHBOARD, db)

        # Only the filtered set is materialized; the dropdown values come from
        # cheap DISTINCT queries, not from loading the whole table.
        period_from, period_to, period_kind = resolve_period(date_from, date_to)
        # An unrecognised field falls back rather than 400ing — the dashboard
        # should still render, and the resolved choice comes back below so the
        # screen shows which date it actually used.
        field = date_field if date_field in DATE_FIELDS else DATE_FIELD_DEFAULT

        rows = fetch_filtered_consignments(
            db, supplier, branch, item_category, mop,
            sourcing_o, po_from_date, po_to_date, search,
            period_from, period_to, field,
        )

        # Status is derived, so it is filtered here rather than in SQL — and
        # filtered on the ORDER's status, keeping all of that order's lines.
        # Judging each line on its own would leave an order half in and half
        # out, and every figure below counts orders.
        if status:
            wanted = set(status)
            rows = [
                line
                for lines in group_orders(rows)
                if order_status(lines) in wanted
                for line in lines
            ]

        data = {
            # The "view data" table is being removed from the dashboard, so
            # only the aggregates + filter option lists are returned (keeping
            # the payload in KBs, like the imports dashboard).
            **serialize_purchases_dashboard(rows, period_from, period_to, date_field=field),
            # The window actually used, and what the table holds — so an empty
            # month reads as "no purchases in Aug 2026, latest is 23 Jan 2026"
            # rather than as a confident zero.
            "period": serialize_period(period_from, period_to, period_kind),
            "coverage": source_coverage(db, period_from, period_to, field),
            "date_field": field,
            "date_field_options": DATE_FIELD_OPTIONS,
            "statuses": PURCHASE_STATUSES,
            **option_lists(db),
        }

        return {
            "status_code": 200,
            "detail": "Purchases dashboard fetched",
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
