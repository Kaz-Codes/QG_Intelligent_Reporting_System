from app.trucking.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_TRUCKING
from app.trucking.helpers import fetch_consignments_page
from app.export_utils import xlsx_response
from typing import Optional

#-----------------------------------------------------
# EXPORT THE FILTERED TRUCKING JOBS TO EXCEL
#
# Same query parameters as the list endpoint, so the export matches the
# filtered set on screen. No page limit.
#-----------------------------------------------------

HEADERS = [
    "ID", "Movement type", "Source", "Source ref", "Execution date",
    "Transporter", "Shifting type", "Item details", "Pickup", "Destination",
    "Reference no.", "Quoted freight", "Actual freight", "Payment status",
    "Paid amount", "Detention", "Dispatch note", "ETA works", "Record state",
    "Vehicles", "Created by", "Remarks",
]


def _row(c):
    vehicles = len([v for v in c.vehicles if not v.is_deleted])
    return [
        c.id,
        c.movement_type,
        c.source,
        c.source_ref,
        c.execution_date,
        c.transporter_name,
        c.shifting_type,
        c.item_details,
        c.pickup,
        c.destination,
        c.reference_no,
        c.quoted_freight,
        c.actual_freight,
        c.payment_status,
        c.paid_amount,
        c.detention,
        c.dispatch_note_date,
        c.eta_works,
        c.record_state,
        vehicles,
        c.created_by.username if c.created_by else "",
        c.remarks,
    ]


@router.get("/export")
def export_consignments(
    request : Request,
    include_deleted : Optional[bool] = False,
    movement_type : Optional[list[str]] = Query(None),
    source : Optional[list[str]] = Query(None),
    open_only : Optional[bool] = False,
    pending_only : Optional[bool] = False,
    q : Optional[str] = None,
    ):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_TRUCKING, db)

        consignments, _ = fetch_consignments_page(
            db, include_deleted, movement_type, source,
            open_only, pending_only, q, page=1, page_size=1_000_000,
        )

        rows = [_row(c) for c in consignments]
        return xlsx_response("trucking_jobs.xlsx", HEADERS, rows, sheet_title="Trucking")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
