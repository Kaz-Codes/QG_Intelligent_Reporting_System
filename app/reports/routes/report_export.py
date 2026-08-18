from datetime import date
from typing import Optional

from fastapi import HTTPException, Query, Request

from app.reports.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.export_utils import xlsx_response
from app.reports.helpers import (
    Filters, selected_types, type_included, conditions_for, fetch_all,
)
from app.reports.serializers import serialize_rows, ROW_KEYS
from app.accounts.permissions import CAN_MAKE_REPORTS

# A deliberate download can be large, but not unbounded — a mis-set filter must
# not pull every table into memory. Rows past this are dropped (and flagged in
# the sheet name so nobody mistakes a truncated export for the whole set).
EXPORT_CAP = 20000

# Human column headers for the normalised row keys.
HEADERS = {
    "type": "Type", "ref": "Reference", "item": "Item", "supplier": "Supplier",
    "branch": "Branch", "category": "Category", "status": "Status",
    "value": "Value", "date": "Date", "po_number": "PO Number",
    "bill_no": "Bill No", "dc_no": "DC No", "mop": "MOP",
    "sourcing_officer": "Sourcing Officer",
    "quantity": "Quantity", "required_date": "Required Date",
    "ppc_store": "PPC Store", "item_code": "Item Code",
    "specification": "Specification", "po_date": "PO Date",
    "country": "Country", "mode_of_shipment": "Mode of Shipment",
    "hs_code": "HS Code", "unit_of_measurement": "UoM",
    "unit_price": "Unit Price", "batch_no": "Batch No",
    "requisition_type": "Requisition Type",
    "reference_number": "Reference Number", "job_number": "Job Number",
    "mo_number": "MO Number", "elc": "ELC", "alc": "ALC",
    "eta_works": "ETA Works", "clearing_agent": "Clearing Agent",
    "loading_port": "Loading Port", "delivery_port": "Delivery Port",
    "incoterm": "Incoterm", "currency": "Currency",
    "consignment_type": "Consignment Type", "works": "Works", "etd": "ETD",
    "gd_number": "GD Number", "gd_filing_date": "GD Filing Date",
    "gate_out_date": "Gate Out Date", "exchange_rate": "Exchange Rate",
    "payment_instrument": "Payment Instrument", "gross_weight": "Gross Weight",
    "specs": "Specs", "stock_qty": "Stock Qty", "hold_qty": "Hold Qty",
    "reorder_level": "Reorder Level", "reorder_status": "Reorder Status",
    "rank": "ABC Rank", "unit_weight": "Unit Weight",
    "planned_rfd_date": "Planned RFD Date", "actual_rfd_date": "Actual RFD Date",
    "customer": "Customer", "pod": "POD", "stage": "Stage",
    "shipping_line": "Shipping Line", "cost_per_kg": "Cost / kg",
    "order_type": "Order Type", "department": "Department",
    "shipment_mode": "Shipment Mode", "origin_city": "Origin City",
    "origin_province": "Origin Province", "batch_label": "Batch Label",
    "pol": "Port of Loading", "booking_no": "Booking No",
    "etd_sailing_date": "ETD Sailing Date", "cro_arrival_date": "CRO Arrival Date",
    "actual_arrival_date": "Actual Arrival Date",
    "packing_cost": "Packing Cost", "transportation_charges": "Transportation Charges",
    "container_detention": "Container Detention", "insurance": "Insurance",
    "trucking_lhr_to_khi": "Trucking (LHR-KHI)", "fumigation_cost": "Fumigation Cost",
    "lashing": "Lashing", "qfl_charges": "QFL Charges",
    "qfl_container_movement": "QFL Container Movement",
    "custom_clearance_charges": "Custom Clearance Charges",
    "port_charges": "Port Charges", "dhl_charges": "DHL Charges",
    "sea_air_freight": "Sea/Air Freight",
}


#-----------------------------------------------------
# GET /reports/export
#
# The same query as /reports/data, run over the whole filtered set (no paging)
# and streamed as an .xlsx. `columns` picks and orders which columns land in the
# sheet; unknown keys are ignored and an empty list falls back to every column.
#-----------------------------------------------------

@router.get("/export")
def reports_export(
    request: Request,
    types: Optional[list[str]] = Query(None),
    columns: Optional[list[str]] = Query(None),
    item: Optional[list[str]] = Query(None),
    shaft: Optional[list[str]] = Query(None),
    supplier: Optional[list[str]] = Query(None),
    branch: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
):
    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_MAKE_REPORTS, db)

        filters = Filters(
            item=item, shaft=shaft, supplier=supplier, branch=branch,
            category=category, date_from=date_from, date_to=date_to, search=search,
        )
        types_wanted = selected_types(types)

        rows = []
        remaining = EXPORT_CAP
        truncated = False
        for report_type in types_wanted:
            if remaining <= 0:
                truncated = True
                break
            if not type_included(report_type, filters):
                continue
            conds = conditions_for(report_type, filters)
            objs = fetch_all(db, report_type, conds, remaining)
            if len(objs) >= remaining:
                truncated = True
            rows.extend(serialize_rows(db, report_type, objs))
            remaining = EXPORT_CAP - len(rows)

        # Which columns, in which order. Keep only real row keys; `type` first so
        # every row says where it came from.
        chosen = [c for c in (columns or []) if c in ROW_KEYS]
        if not chosen:
            chosen = list(ROW_KEYS)
        if "type" not in chosen:
            chosen = ["type"] + chosen

        headers = [HEADERS.get(key, key) for key in chosen]
        cells = [[row.get(key) for key in chosen] for row in rows]

        sheet_title = "Report (truncated)" if truncated else "Report"
        return xlsx_response("report.xlsx", headers, cells, sheet_title=sheet_title)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
