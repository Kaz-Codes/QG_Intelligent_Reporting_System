from app.imports.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.helpers import fetch_consignments_page
from app.export_utils import xlsx_response
from typing import Optional
from datetime import date
import logging
from app.imports.demand_dates import earliest_required_date, earliest_requisition_date
from app.imports.order_view import (
    line_item_name, line_requisition_type, line_unit_price, order_branch_name,
    order_currency, order_exchange_rate, order_incoterm,
    order_instrument_number, order_origin, order_payment_instrument,
    order_rate_booked_on, order_supplier_name, order_type,
)

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# EXPORT THE FILTERED CONSIGNMENTS TO EXCEL
#
# Same query parameters as the list endpoint, so the export always matches the
# filtered set on screen. Runs the shared list query with no page limit.
#-----------------------------------------------------

HEADERS = [
    "ID", "Branch", "Supplier", "Works", "Country of origin", "Currency",
    "Type", "Incoterm", "Status", "Marked finished", "Requisition date",
    "Required date", "ETD", "ETA", "ETA works", "Payment instrument",
    "Instrument no.", "Exchange rate", "Rate booked on", "GD number",
    "GD filing date", "Free days", "Gate out", "Demurrage", "Container detention",
    "Foreign total", "Items", "Requisition types", "Created by", "User remarks",
]


def _row(c):
    foreign_total = sum(
        (item.quantity or 0) * (line_unit_price(item) or 0)
        for item in c.items if not item.is_deleted
    )
    active_items = [i for i in c.items if not i.is_deleted]
    item_names = "; ".join(line_item_name(i) for i in active_items if line_item_name(i))
    req_types = " + ".join(sorted(
        {line_requisition_type(i) for i in active_items if line_requisition_type(i)}
    ))

    return [
        c.id,
        # TWELVE OF THESE COLUMNS NOW COME FROM THE ORDER OR THE ORDER LINE.
        # A wrong accessor here does not crash - it returns None and the sheet
        # gets a blank column, which reads as missing data rather than a bug.
        # Asserted by value, not by status code, in the export check.
        order_branch_name(c) or "",
        order_supplier_name(c) or "",
        # `works` is retired; the order's branch is what it always meant.
        order_branch_name(c),
        order_origin(c),
        order_currency(c),
        order_type(c),
        order_incoterm(c),
        c.current_status,
        c.record_state,
        # Requisition date is per LINE with no header aggregate (section 3.3),
        # so the header row shows the earliest of this batch's lines - the same
        # rule `required_date` uses, and the only honest single value here.
        earliest_requisition_date(c),
        earliest_required_date(c),
        c.etd,
        c.eta,
        c.eta_works,
        order_payment_instrument(c),
        order_instrument_number(c),
        order_exchange_rate(c),
        order_rate_booked_on(c),
        c.gd_number,
        c.gd_filing_date,
        c.free_days_allowed,
        c.gate_out_date,
        c.demurrage_or_detention_paid,
        c.container_detention,
        foreign_total,
        item_names,
        req_types,
        c.created_by.username if c.created_by else "",
        c.remarks,
    ]


@router.get("/export")
def export_consignments(
    request : Request,
    include_deleted : Optional[bool] = False,
    include_closed : Optional[bool] = False,
    status : Optional[list[str]] = Query(None),
    stage : Optional[str] = None,
    branch_id : Optional[list[int]] = Query(None),
    supplier_id : Optional[list[int]] = Query(None),
    requisition_type : Optional[list[str]] = Query(None),
    drafts_only : Optional[bool] = False,
    etd_from : Optional[date] = None,
    etd_to : Optional[date] = None,
    q : Optional[str] = None,
    ):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_IMPORTS, db)

        # No page limit: the whole filtered set, newest first.
        consignments, _ = fetch_consignments_page(
            db, include_deleted, include_closed, status, stage,
            branch_id, supplier_id, requisition_type,
            drafts_only, etd_from, etd_to, q, page=1, page_size=1_000_000,
        )

        rows = [_row(c) for c in consignments]
        return xlsx_response("consignments.xlsx", HEADERS, rows, sheet_title="Consignments")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.export_consignments")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
