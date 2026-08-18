from app.dashboard.purchases.calculations import derive_status as purchase_status
from app.dashboard.inventory.calculations import (
    derive_stock_status, derive_reorder_status,
)
from app.dashboard.logistics.calculations import (
    total_logistics_cost, cost_per_kg, shipment_stage,
)
from app.reports.helpers import reorder_levels_for


#-----------------------------------------------------
# THE NORMALISED REPORT ROW
#
# Every type is flattened into one row shape with a shared set of keys, so the
# four data sources can sit in one table. A key a type has no value for is left
# null. `type` says which source the row came from, so the front end knows which
# type-specific columns apply.
#
# Fields with no backend source were dropped by decision: imports weight / bank
# / documentation status, and inventory's last-restocked date. `material`
# (purchases) has no column either, so it is not emitted or filtered on.
#
# IMPORTS AND LOGISTICS ARE ONE ROW PER LINE, not per consignment/order — the
# per-line fields (HS code, quantity, unit price, ELC/ALC, RFD dates, ...)
# only exist on the child table, and folding them onto one header row per
# consignment either drops them or forces an arbitrary aggregate. Header
# fields (supplier, clearing agent, incoterm, ...) simply repeat on every line
# belonging to the same consignment/order — normal for a flat/denormalised
# export, and the same shape purchases and inventory already have (one row per
# source record). See `_line_value_pkr` for why `value` is a genuine per-LINE
# figure for imports but stays an order-level figure (repeated per line) for
# logistics, which has no per-item cost breakdown to draw on.
#-----------------------------------------------------

ROW_KEYS = [
    "type", "ref", "item", "supplier", "branch", "category", "status",
    "value", "date",
    # purchases
    "po_number", "bill_no", "dc_no", "mop", "sourcing_officer", "quantity",
    "required_date", "ppc_store", "item_code", "specification", "po_date",
    # imports (line): "item_code", "quantity" and "po_date" above are shared
    "country", "mode_of_shipment", "hs_code", "unit_of_measurement",
    "unit_price", "batch_no", "requisition_type", "reference_number",
    "job_number", "mo_number", "elc", "alc", "eta_works",
    # imports (header)
    "clearing_agent", "loading_port", "delivery_port", "incoterm",
    "currency", "consignment_type", "works", "etd", "gd_number",
    "gd_filing_date", "gate_out_date", "exchange_rate", "payment_instrument",
    "gross_weight",
    # inventory
    "specs", "stock_qty", "hold_qty", "reorder_level", "reorder_status", "rank",
    # logistics (line): "job_number" and "gross_weight" above are shared
    "unit_weight", "planned_rfd_date", "actual_rfd_date",
    # logistics (header): "clearing_agent", "incoterm" and "gate_out_date"
    # above are shared with imports
    "customer", "pod", "stage", "shipping_line", "cost_per_kg",
    "order_type", "department", "shipment_mode", "origin_city",
    "origin_province", "batch_label", "pol", "booking_no",
    "etd_sailing_date", "cro_arrival_date", "actual_arrival_date",
    "packing_cost", "transportation_charges", "container_detention",
    "insurance", "trucking_lhr_to_khi", "fumigation_cost", "lashing",
    "qfl_charges", "qfl_container_movement", "custom_clearance_charges",
    "port_charges", "dhl_charges", "sea_air_freight",
]


def _base(report_type):
    row = {key: None for key in ROW_KEYS}
    row["type"] = report_type
    return row


def _line_value_pkr(ci, c):
    """An import LINE'S own PKR value — quantity x unit price, at the
    consignment's booked rate (never a live one, imports rule 4). Replaces the
    whole-consignment `pkr_total` this used to show on every row: repeating a
    5-line consignment's full total on each of its 5 rows would 5x it the
    moment someone sums the Value column."""
    if ci.quantity is None or ci.unit_price is None or c.exchange_rate is None:
        return None
    return ci.quantity * ci.unit_price * c.exchange_rate


#-------------------------------------
# PER-TYPE ROW BUILDERS
#-------------------------------------

def _serialize_purchase(p):
    row = _base("purchases")
    row.update({
        "ref": p.ref_no,
        "item": p.item_name,
        "item_code": p.item_code,
        "specification": p.specification,
        "supplier": p.supplier,
        "branch": p.branch,
        "category": p.item.category if p.item else None,
        "status": purchase_status(p.purchase, p.required_d),
        "value": p.amount,
        "date": p.purchase,
        "po_number": p.po_number,
        "po_date": p.po_date,
        "bill_no": p.bill_no,
        "dc_no": p.dc_no,
        "mop": p.mop,
        "sourcing_officer": p.sourcing_o,
        "quantity": p.qty,
        "required_date": p.required_d,
        "ppc_store": p.ppc_store,
    })
    return row


def _serialize_import(ci):
    """One row per import LINE (`ConsignmentItem`), not per consignment — see
    the ROW_KEYS comment above. Header fields come off `ci.consignment` and
    repeat on every line of the same consignment."""
    c = ci.consignment
    row = _base("imports")
    row.update({
        # No dedicated human reference exists on the consignment; the bank
        # instrument number is the natural one, falling back to the id.
        "ref": c.instrument_number or f"IMP-{c.id}",
        "item": ci.item_name,
        "item_code": ci.item_code,
        "supplier": c.supplier.name if c.supplier else None,
        "branch": c.branch.name if c.branch else None,
        "category": ci.item.category if ci.item else None,
        "status": c.current_status,
        "value": _line_value_pkr(ci, c),
        "date": c.requisition_date,
        "country": c.origin,
        "mode_of_shipment": c.mode_of_shipment,
        "hs_code": ci.hs_code,
        "quantity": ci.quantity,
        "unit_of_measurement": ci.unit_of_measurement,
        "unit_price": ci.unit_price,
        "batch_no": ci.batch_no,
        "requisition_type": ci.requisition_type,
        "reference_number": ci.reference_number,
        "job_number": ci.job_number,
        "mo_number": ci.mo_number,
        "elc": ci.elc,
        "alc": ci.alc,
        # The line's own arrival date, falling back to its consignment's
        # where the line has none — same rule as
        # app.dashboard.imports.helpers.LINE_ETA.
        "eta_works": ci.eta_works or c.eta_works,
        "clearing_agent": c.clearing_agent.name if c.clearing_agent else None,
        "loading_port": c.loading_port.name if c.loading_port else None,
        "delivery_port": c.delivery_port.name if c.delivery_port else None,
        "incoterm": c.incoterm,
        "currency": c.currency,
        "consignment_type": c.consignment_type,
        "works": c.works,
        "po_date": c.po_date,
        "etd": c.etd,
        "gd_number": c.gd_number,
        "gd_filing_date": c.gd_filing_date,
        "gate_out_date": c.gate_out_date,
        "exchange_rate": c.exchange_rate,
        "payment_instrument": c.payment_instrument,
        "gross_weight": ci.gross_weight,
    })
    return row


def _serialize_inventory(s, reorder_levels):
    item = s.item
    key = (s.item_code, s.branch)
    reorder_level = reorder_levels.get(key)
    if reorder_level is None:
        reorder_level = s.reorder_level

    row = _base("inventory")
    row.update({
        "ref": s.item_code,
        "item": s.item_name,
        "branch": s.branch,
        "category": item.category if item else None,
        "specs": item.default_specification if item else None,
        "status": derive_stock_status(s.available_qty, reorder_level),
        "value": s.available_qty,
        "stock_qty": s.stock_qty,
        "hold_qty": s.hold_qty,
        "reorder_level": reorder_level,
        "reorder_status": derive_reorder_status(s.available_qty, reorder_level),
        "rank": s.rank,
    })
    return row


def _serialize_logistics(li):
    """One row per line (`LogisticsItem`), not per order — see the ROW_KEYS
    comment above. Header fields come off `li.consignment` and repeat on
    every line of the same order.

    `value`/`cost_per_kg` stay ORDER-level (repeated per line): logistics has
    no per-item cost breakdown to draw a genuine line figure from, unlike
    imports' `_line_value_pkr`. Summing this column across an order's lines
    overstates its cost the same way summing imports' `value` used to — the
    individual freight/packing/etc. columns below are the true per-order
    figures either way, `value` is just their total, same as before.
    """
    o = li.consignment
    row = _base("logistics")
    row.update({
        "ref": o.mo_no,
        "item": li.item_detail,
        "job_number": li.job_no,
        "quantity": li.quantity,
        "unit_weight": li.unit_weight,
        "gross_weight": li.gross_weight,
        "planned_rfd_date": li.planned_rfd_date,
        "actual_rfd_date": li.actual_rfd_date,
        "customer": o.customer_name,
        "country": o.origin_country,
        "origin_city": o.origin_city,
        "origin_province": o.origin_province,
        "order_type": o.order_type,
        "department": o.department,
        "shipment_mode": o.shipment_mode,
        "batch_label": o.batch_label,
        "incoterm": o.incoterm,
        "pol": o.pol,
        "pod": o.pod,
        "shipping_line": o.shipping_line,
        "clearing_agent": o.clearing_agent,
        "booking_no": o.booking_no,
        "status": o.current_status,
        "stage": shipment_stage(o),
        "value": total_logistics_cost(o),
        "cost_per_kg": cost_per_kg(o),
        "date": o.port_in_date,
        "etd_sailing_date": o.etd_sailing_date,
        "cro_arrival_date": o.cro_arrival_date,
        "actual_arrival_date": o.actual_arrival_date,
        "gate_out_date": o.gate_out_date,
        "packing_cost": o.packing_cost,
        "transportation_charges": o.transportation_charges,
        "container_detention": o.container_detention,
        "insurance": o.insurance,
        "trucking_lhr_to_khi": o.trucking_lhr_to_khi,
        "fumigation_cost": o.fumigation_cost,
        "lashing": o.lashing,
        "qfl_charges": o.qfl_charges,
        "qfl_container_movement": o.qfl_container_movement,
        "custom_clearance_charges": o.custom_clearance_charges,
        "port_charges": o.port_charges,
        "dhl_charges": o.dhl_charges,
        "sea_air_freight": o.sea_air_freight,
    })
    return row


#-------------------------------------
# DISPATCH — serialize a fetched slice
#
# Inventory needs the (item_code, branch) reorder-level map, built here scoped
# to just the rows in the slice. The other types serialize row by row.
# `objs` for imports/logistics are now the LINE rows (ConsignmentItem /
# LogisticsItem), not the header — see helpers._MODEL.
#-------------------------------------

def serialize_rows(db, report_type, objs):
    if report_type == "purchases":
        return [_serialize_purchase(o) for o in objs]
    if report_type == "imports":
        return [_serialize_import(o) for o in objs]
    if report_type == "logistics":
        return [_serialize_logistics(o) for o in objs]
    if report_type == "inventory":
        reorder_levels = reorder_levels_for(db, [o.item_code for o in objs])
        return [_serialize_inventory(o, reorder_levels) for o in objs]
    return []


#-------------------------------------
# SAVED REPORT
#-------------------------------------

def serialize_saved(saved):
    return {
        "id": saved.id,
        "name": saved.name,
        "types": saved.types or [],
        "columns": saved.columns or [],
        "filters": saved.filters or {},
        "created_by": saved.created_by.username if saved.created_by else None,
        "created_by_id": saved.created_by_id,
        "created_at": saved.created_at,
        "updated_at": saved.updated_at,
    }
