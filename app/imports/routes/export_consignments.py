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

#-----------------------------------------------------
# EXPORT THE FILTERED CONSIGNMENTS TO EXCEL
#
# Same query parameters as the list endpoint, so the export always matches the
# filtered set on screen. Runs the shared list query with no page limit.
#-----------------------------------------------------

HEADERS = [
    "ID", "Branch", "Supplier", "Works", "Country of origin", "Currency",
    "Type", "Incoterm", "Status", "Record state", "Requisition date",
    "Required date", "ETD", "ETA", "ETA works", "Payment instrument",
    "Instrument no.", "Exchange rate", "Rate booked on", "GD number",
    "GD filing date", "Free days", "Gate out", "Demurrage", "Container detention",
    "Foreign total", "Items", "Requisition types", "Created by", "User remarks",
]


def _row(c):
    foreign_total = sum(
        (item.quantity or 0) * (item.unit_price or 0)
        for item in c.items if not item.is_deleted
    )
    active_items = [i for i in c.items if not i.is_deleted]
    item_names = "; ".join(i.item_name for i in active_items if i.item_name)
    req_types = " + ".join(sorted({i.requisition_type for i in active_items if i.requisition_type}))

    return [
        c.id,
        c.branch.name if c.branch else "",
        c.supplier.name if c.supplier else "",
        c.works,
        c.origin,
        c.currency,
        c.consignment_type,
        c.incoterm,
        c.current_status,
        c.record_state,
        c.requisition_date,
        c.required_date,
        c.etd,
        c.eta,
        c.eta_works,
        c.payment_instrument,
        c.instrument_number,
        c.exchange_rate,
        c.rate_booked_on,
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
    missing_only : Optional[bool] = False,
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
            missing_only, etd_from, etd_to, q, page=1, page_size=1_000_000,
        )

        rows = [_row(c) for c in consignments]
        return xlsx_response("consignments.xlsx", HEADERS, rows, sheet_title="Consignments")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
