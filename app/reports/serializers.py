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
# Fields with no backend source were dropped by decision: imports customer /
# weight / shipping line / bank / documentation status, and inventory's
# last-restocked date. `material` (purchases) has no column either, so it is not
# emitted or filtered on.
#-----------------------------------------------------

ROW_KEYS = [
    "type", "ref", "item", "supplier", "branch", "category", "status",
    "value", "date",
    # purchases
    "po_number", "bill_no", "mop", "sourcing_officer", "quantity",
    "required_date", "ppc_store",
    # imports
    "country", "mode_of_shipment",
    # inventory
    "specs", "stock_qty", "hold_qty", "reorder_level", "reorder_status",
    # logistics
    "customer", "pod", "stage", "shipping_line", "cost_per_kg",
]


def _base(report_type):
    row = {key: None for key in ROW_KEYS}
    row["type"] = report_type
    return row


def _first_category(consignment):
    for item in consignment.items:
        if item.is_deleted:
            continue
        if item.item and item.item.category:
            return item.item.category
    return None


#-------------------------------------
# PER-TYPE ROW BUILDERS
#-------------------------------------

def _serialize_purchase(p):
    row = _base("purchases")
    row.update({
        "ref": p.ref_no,
        "item": p.item_name,
        "supplier": p.supplier,
        "branch": p.branch,
        "category": p.item.category if p.item else None,
        "status": purchase_status(p.purchase, p.required_d),
        "value": p.amount,
        "date": p.purchase,
        "po_number": p.po_number,
        "bill_no": p.bill_no,
        "mop": p.mop,
        "sourcing_officer": p.sourcing_o,
        "quantity": p.qty,
        "required_date": p.required_d,
        "ppc_store": p.ppc_store,
    })
    return row


def _serialize_import(c):
    row = _base("imports")
    row.update({
        # No dedicated human reference exists on the consignment; the bank
        # instrument number is the natural one, falling back to the id.
        "ref": c.instrument_number or f"IMP-{c.id}",
        "supplier": c.supplier.name if c.supplier else None,
        "branch": c.branch.name if c.branch else None,
        "category": _first_category(c),
        "status": c.current_status,
        "value": c.pkr_total,
        "date": c.requisition_date,
        "country": c.origin,
        "mode_of_shipment": c.mode_of_shipment,
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
    })
    return row


def _serialize_logistics(o):
    row = _base("logistics")
    row.update({
        "ref": o.mo_no,
        "customer": o.customer_name,
        "country": o.origin_country,
        "pod": o.pod,
        "status": o.current_status,
        "stage": shipment_stage(o),
        "shipping_line": o.shipping_line,
        "value": total_logistics_cost(o),
        "cost_per_kg": cost_per_kg(o),
        "date": o.port_in_date,
    })
    return row


#-------------------------------------
# DISPATCH — serialize a fetched slice
#
# Inventory needs the (item_code, branch) reorder-level map, built here scoped
# to just the rows in the slice. The other types serialize row by row.
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
