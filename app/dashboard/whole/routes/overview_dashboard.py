from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_OVERVIEW_DASHBOARD
from app.dashboard.period import resolve_period, DEAD_STOCK_WINDOW_DAYS
from app.dashboard.whole.helpers import (
    IMPORTS_DATE_FIELDS, IMPORTS_DATE_DEFAULT,
    PURCHASES_DATE_FIELDS, PURCHASES_DATE_DEFAULT,
    TRUCKING_DATE_FIELDS, LOGISTICS_DATE_DEFAULT,
)
from app.dashboard.whole.serializers import serialize_overview
from app.dashboard.whole.routes.router import router

# Default cut-off for a stock line to count as dead. Exposed as a query param
# rather than fixed: how long stock must sit unissued before it is written off
# is a business judgement, so the caller states it and the backend does not
# quietly decide on their behalf. The DEFAULT is shared with the Inventory
# dashboard's own (fixed) dead-stock window — see period.DEAD_STOCK_WINDOW_DAYS.
DEFAULT_DEAD_STOCK_DAYS = DEAD_STOCK_WINDOW_DAYS


def _section(date_from, date_to, field, allowed, default):
    """Resolve one section's window + date choice.

    Each section has its OWN window because a consignment's arrival, a PO's
    date and a truck's run are different events; one shared filter compared
    unlike things. Both bounds omitted still means the current month, resolved
    the same way everywhere.

    An unrecognised field falls back to the default rather than 400ing — the
    dashboard should still render, and the resolved choice comes back in the
    payload so the screen shows which date it actually used.
    """
    start, end, kind = resolve_period(date_from, date_to)
    return {
        "from": start,
        "to": end,
        "kind": kind,
        "field": field if field in allowed else default,
    }


@router.get("/overview")
def overview_dashboard(
    request: Request,

    # --- imports: filter on when goods land, or when they were needed ---
    imports_date_from: Optional[date] = None,
    imports_date_to: Optional[date] = None,
    imports_date_field: Optional[str] = Query(
        None, description="eta_works | required_date"
    ),

    # --- procurement: when the order was placed, or when it was bought ---
    purchases_date_from: Optional[date] = None,
    purchases_date_to: Optional[date] = None,
    purchases_date_field: Optional[str] = Query(
        None, description="po_date | purchase"
    ),

    # --- logistics: departure or arrival ---
    logistics_date_from: Optional[date] = None,
    logistics_date_to: Optional[date] = None,
    logistics_date_field: Optional[str] = Query(None, description="etd | eta"),

    # --- stores: stock is a snapshot, but ISSUANCE happens in a period ---
    stores_date_from: Optional[date] = None,
    stores_date_to: Optional[date] = None,
    dead_stock_days: int = Query(DEFAULT_DEAD_STOCK_DAYS, ge=1, le=1825),

    # The Shafts tab. Narrows EVERY imports figure — tiles, stage chart and
    # reference lists — to shaft consignments, rather than sitting beside them
    # as two tiles measuring a different population from the ones next to them.
    shafts_only: bool = False,
):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only; the overview has its own view permission.
        authorize(user_payload, CAN_VIEW_OVERVIEW_DASHBOARD, db)

        for label, start, end in [
            ("imports", imports_date_from, imports_date_to),
            ("purchases", purchases_date_from, purchases_date_to),
            ("logistics", logistics_date_from, logistics_date_to),
            ("stores", stores_date_from, stores_date_to),
        ]:
            if start and end and start > end:
                raise HTTPException(
                    status_code=400,
                    detail=f"{label}_date_from cannot be after {label}_date_to",
                )

        sections = {
            "imports": _section(
                imports_date_from, imports_date_to, imports_date_field,
                IMPORTS_DATE_FIELDS, IMPORTS_DATE_DEFAULT,
            ),
            "procurement": _section(
                purchases_date_from, purchases_date_to, purchases_date_field,
                PURCHASES_DATE_FIELDS, PURCHASES_DATE_DEFAULT,
            ),
            "logistics": _section(
                logistics_date_from, logistics_date_to, logistics_date_field,
                TRUCKING_DATE_FIELDS, LOGISTICS_DATE_DEFAULT,
            ),
            "stores": {"from": stores_date_from, "to": stores_date_to},
        }

        data = serialize_overview(db, sections, dead_stock_days, shafts_only)

        # The choices the screen can offer, named by the backend so the two
        # cannot disagree about what is selectable.
        data["date_field_options"] = {
            "imports": [
                {"value": "eta_works", "label": "ETA at works"},
                {"value": "required_date", "label": "Required date"},
            ],
            "purchases": [
                {"value": "po_date", "label": "PO date (ordered)"},
                {"value": "purchase", "label": "Purchase date (bought)"},
            ],
            "logistics": [
                {"value": "etd", "label": "ETD (departure)"},
                {"value": "eta", "label": "ETA (arrival)"},
            ],
            # Stores has one date that means anything — when stock was issued.
            "stores": [
                {"value": "issuance_date", "label": "Issuance date"},
            ],
        }

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
