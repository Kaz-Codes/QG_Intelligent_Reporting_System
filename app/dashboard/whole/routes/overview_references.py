"""
GET /dashboard/overview/references — page 2 and beyond of a KPI's record list.

The dashboard payload carries the true total plus the first page of every
reference list (see app/dashboard/references for why it is not all of it). This
endpoint serves the rest: same filters, one `key` naming which list, and a page
number. Nothing is hidden — it is just fetched when somebody scrolls.

`key` is matched against a fixed registry rather than being used to look
anything up dynamically, so an unknown key is a 400 and never a way to reach a
query the screen was not meant to run.
"""

from datetime import date
from typing import Optional

from fastapi import Request, HTTPException, Query

from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_OVERVIEW_DASHBOARD
from app.dashboard.period import resolve_period, DEAD_STOCK_WINDOW_DAYS
from app.dashboard.references import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.dashboard.whole import references as refs
from app.dashboard.whole.helpers import (
    IMPORTS_DATE_FIELDS, IMPORTS_DATE_DEFAULT,
    PURCHASES_DATE_FIELDS, PURCHASES_DATE_DEFAULT,
    TRUCKING_DATE_FIELDS, LOGISTICS_DATE_DEFAULT,
)
from app.dashboard.whole.routes.router import router

# Shared with the Inventory dashboard's own (fixed) dead-stock window — see
# period.DEAD_STOCK_WINDOW_DAYS and overview_dashboard.py's identical constant.
DEFAULT_DEAD_STOCK_DAYS = DEAD_STOCK_WINDOW_DAYS

# key -> (which section's window it uses, the builder)
#
# The section matters: each has its own window and its own choice of date, so a
# list has to be paged over the same window the tile was computed on or page 2
# describes a different set from page 1.
# Each builder takes (db, window, options, page, page_size, search) — `search`
# is threaded to every entry uniformly, even where a given builder ignores it,
# so this registry is the ONE place that has to agree with references.py's
# signatures rather than trusting every lambda to remember it.
BUILDERS = {
    "imports.period_value":  ("imports", lambda db, w, o, p, s, q: refs.imports_value_references(
        db, w["from"], w["to"], w["field"], o["shafts_only"], page=p, page_size=s, search=q)),
    "imports.in_process":    ("imports", lambda db, w, o, p, s, q: refs.imports_in_process_references(
        db, w["from"], w["to"], w["field"], o["shafts_only"], page=p, page_size=s, search=q)),
    "imports.arrived":       ("imports", lambda db, w, o, p, s, q: refs.imports_status_references(
        db, "arrived", w["from"], w["to"], w["field"], o["shafts_only"], page=p, page_size=s, search=q)),
    "imports.cancelled":     ("imports", lambda db, w, o, p, s, q: refs.imports_status_references(
        db, "cancelled", w["from"], w["to"], w["field"], o["shafts_only"], page=p, page_size=s, search=q)),
    "imports.delayed":       ("imports", lambda db, w, o, p, s, q: refs.imports_delayed_references(
        db, w["from"], w["to"], w["field"], o["shafts_only"], page=p, page_size=s, search=q)),

    "procurement.period_value": ("procurement", lambda db, w, o, p, s, q: refs.procurement_value_references(
        db, w["from"], w["to"], w["field"], page=p, page_size=s, search=q)),
    "procurement.delay":        ("procurement", lambda db, w, o, p, s, q: refs.procurement_delay_references(
        db, w["from"], w["to"], w["field"], page=p, page_size=s, search=q)),

    "logistics.trucking_cost":     ("logistics", lambda db, w, o, p, s, q: refs.trucking_cost_references(
        db, w["from"], w["to"], w["field"], movement=o["movement"], page=p, page_size=s, search=q)),
    "logistics.shipments_handled": ("logistics", lambda db, w, o, p, s, q: refs.shipments_handled_references(
        db, w["from"], w["to"], w["field"], page=p, page_size=s, search=q)),

    "stores.stock_value": ("stores", lambda db, w, o, p, s, q: refs.stock_value_references(
        db, page=p, page_size=s, search=q)),
    "stores.dead_stock":  ("stores", lambda db, w, o, p, s, q: refs.dead_stock_references(
        db, o["dead_stock_days"], page=p, page_size=s, search=q)),
    "stores.issuance":    ("stores", lambda db, w, o, p, s, q: refs.issuance_references(
        db, w["from"], w["to"], page=p, page_size=s, search=q)),
}

FIELD_SETS = {
    "imports": (IMPORTS_DATE_FIELDS, IMPORTS_DATE_DEFAULT),
    "procurement": (PURCHASES_DATE_FIELDS, PURCHASES_DATE_DEFAULT),
    "logistics": (TRUCKING_DATE_FIELDS, LOGISTICS_DATE_DEFAULT),
    "stores": ({}, None),
}


@router.get("/overview/references")
def overview_references(
    request: Request,
    key: str = Query(..., description=" | ".join(sorted(BUILDERS))),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    # Filters the OPEN PANEL to rows whose visible text (reference/detail/meta)
    # contains this, case-insensitive. Named `list_search`, not `search`: the
    # other four dashboards already have a `search` that narrows which records
    # COUNT toward the KPI in the first place (the screen's own filter bar).
    # This one only narrows what the already-open list SHOWS — it must never
    # change the tile's own value, or typing into the panel would silently
    # edit the figure it was opened to explain. Narrows `total` itself, not
    # just the current page — a box that only hides rows already on screen
    # would miss everything on the other 43 pages.
    list_search: Optional[str] = None,

    # The section's own window + date choice, named exactly as on /overview so
    # the screen can forward the filters it already holds.
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    date_field: Optional[str] = None,

    # Figure-specific narrowing.
    shafts_only: bool = False,
    movement: Optional[str] = None,
    dead_stock_days: int = Query(DEFAULT_DEAD_STOCK_DAYS, ge=1, le=1825),
):
    if key not in BUILDERS:
        raise HTTPException(status_code=400, detail=f"Unknown reference key '{key}'")

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_OVERVIEW_DASHBOARD, db)

        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=400,
                                detail="date_from cannot be after date_to")

        section, build = BUILDERS[key]
        allowed, default = FIELD_SETS[section]
        start, end, _kind = resolve_period(date_from, date_to)

        window = {
            "from": start,
            "to": end,
            "field": date_field if date_field in allowed else default,
        }
        options = {
            "shafts_only": shafts_only,
            "movement": movement,
            "dead_stock_days": dead_stock_days,
        }

        return {
            "status_code": 200,
            "detail": "Overview references fetched",
            "data": build(db, window, options, page, page_size, list_search),
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
