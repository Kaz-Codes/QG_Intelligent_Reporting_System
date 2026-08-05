from app.logistics.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS
from app.logistics.helpers import fetch_consignments_page
from app.export_utils import xlsx_response
from typing import Optional
from datetime import date

#-----------------------------------------------------
# EXPORT THE FILTERED LOGISTICS ORDERS TO EXCEL
#
# Same query parameters as the list endpoint, so the export matches the
# filtered set on screen. No page limit.
#-----------------------------------------------------

HEADERS = [
    "ID", "Order type", "Department", "Customer", "Origin country",
    "Origin city", "Origin province", "MO no.", "Batch no.", "Batch label",
    "Incoterm", "Status", "Record state", "POL", "POD", "Shipping line",
    "Clearing agent", "Booking no.", "Port in", "ETD / sailing", "CRO arrival",
    "Actual arrival", "Gate out", "Sent to trucking", "Items", "Packages",
    "Containers", "Created by",
]


def _row(c):
    active_items = [i for i in c.items if not i.is_deleted]
    item_details = "; ".join(i.item_detail for i in active_items if i.item_detail)
    packages = len([p for p in c.packages if not p.is_deleted])
    containers = len([ct for ct in c.containers if not ct.is_deleted])

    return [
        c.id,
        c.order_type,
        c.department,
        c.customer_name,
        c.origin_country,
        c.origin_city,
        c.origin_province,
        c.mo_no,
        c.batch_no,
        c.batch_label,
        c.incoterm,
        c.current_status,
        c.record_state,
        c.pol,
        c.pod,
        c.shipping_line,
        c.clearing_agent,
        c.booking_no,
        c.port_in_date,
        c.etd_sailing_date,
        c.cro_arrival_date,
        c.actual_arrival_date,
        c.gate_out_date,
        "Yes" if c.sent_to_trucking else "No",
        item_details,
        packages,
        containers,
        c.created_by.username if c.created_by else "",
    ]


@router.get("/export")
def export_consignments(
    request : Request,
    include_deleted : Optional[bool] = False,
    status : Optional[list[str]] = Query(None),
    order_type : Optional[list[str]] = Query(None),
    customer : Optional[list[str]] = Query(None),
    gate_out_from : Optional[date] = None,
    gate_out_to : Optional[date] = None,
    q : Optional[str] = None,
    ):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_LOGISTICS, db)

        consignments, _ = fetch_consignments_page(
            db, include_deleted, status, order_type, customer,
            gate_out_from, gate_out_to, q, page=1, page_size=1_000_000,
        )

        rows = [_row(c) for c in consignments]
        return xlsx_response("logistics_orders.xlsx", HEADERS, rows, sheet_title="Logistics")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
