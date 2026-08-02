from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from app.logistics.models import LogisticsConsignment
from app.imports.models import Consignment
from app.trucking.models import TruckingConsignment

#-----------------------------------------------------
# CROSS-MODULE LINKAGE
#
# The three modules are one flow. Trucking work originates in the other two:
#
#   * a logistics order handed off with sent_to_trucking, and
#   * an import consignment bought FOB (QG arranges the inbound truck).
#
# A trucking job records where it came from as (source, source_ref) — e.g.
# ("from-import-fob", "42"). This module turns those still-inert references
# into live links: it derives the OPEN requests (originating records not yet
# taken by a trucking job) and does the reverse lookup (which trucking jobs
# came from a given order / consignment). The heavy per-vehicle package refs
# are left as stored data; this is the record-level linkage.
#-----------------------------------------------------


def _num(v):
    return float(v) if v is not None else None


def _taken_pairs(db):
    # (source, source_ref) of every trucking job that has taken a request, so
    # taken requests drop out of the open list.
    rows = db.execute(
        select(TruckingConsignment.source, TruckingConsignment.source_ref)
        .where(TruckingConsignment.is_deleted == False)
        .where(TruckingConsignment.source_ref.isnot(None))
    ).all()
    return {(source, ref) for source, ref in rows}


#--------------------------------
# SNAPSHOTS (pre-fill for "Take Action")
#--------------------------------

def _logistics_snapshot(order):
    snapshot = []
    for package in order.packages:
        if package.is_deleted:
            continue
        snapshot.append({
            "source_package_id": str(package.id),
            "label": package.colour_code or f"Package {package.id}",
            "item_details": None,
            "quantity": None,
            "weight": _num(package.gross_weight),
        })
    if not snapshot:
        for item in order.items:
            if item.is_deleted:
                continue
            snapshot.append({
                "source_package_id": None,
                "label": item.item_detail or f"Item {item.id}",
                "item_details": item.item_detail,
                "quantity": _num(item.quantity),
                "weight": _num(item.gross_weight),
            })
    return snapshot


def _import_snapshot(consignment):
    snapshot = []
    for item in consignment.items:
        if item.is_deleted:
            continue
        snapshot.append({
            "source_package_id": None,
            "label": item.item_name or f"Item {item.id}",
            "item_details": item.specification,
            "quantity": _num(item.quantity),
            "weight": None,
        })
    return snapshot


#--------------------------------
# OPEN REQUESTS (logistics + import-FOB, not yet taken)
#--------------------------------

def derive_open_requests(db):
    taken = _taken_pairs(db)
    requests = []

    log_orders = db.execute(
        select(LogisticsConsignment)
        .where(LogisticsConsignment.is_deleted == False)
        .where(LogisticsConsignment.sent_to_trucking == True)
        .options(
            selectinload(LogisticsConsignment.items),
            selectinload(LogisticsConsignment.packages),
        )
        .order_by(LogisticsConsignment.id.desc())
    ).scalars().all()

    for order in log_orders:
        ref = str(order.id)
        if ("from-logistics", ref) in taken:
            continue
        label = " ".join(p for p in [order.department, order.order_type] if p).strip()
        requests.append({
            "source": "from-logistics",
            "source_ref": ref,
            "movement_type": "Outbound",
            "label": f"{label} — {order.customer_name or 'Order ' + ref}".strip(" —"),
            "customer": order.customer_name,
            "mo_no": order.mo_no,
            "snapshot": _logistics_snapshot(order),
        })

    imports_fob = db.execute(
        select(Consignment)
        .where(Consignment.is_deleted == False)
        .where(Consignment.incoterm == "FOB")
        .options(
            selectinload(Consignment.items),
            joinedload(Consignment.supplier),
        )
        .order_by(Consignment.id.desc())
    ).scalars().all()

    for consignment in imports_fob:
        ref = str(consignment.id)
        if ("from-import-fob", ref) in taken:
            continue
        requests.append({
            "source": "from-import-fob",
            "source_ref": ref,
            "movement_type": "Inbound",
            "label": f"Import {ref} — {consignment.supplier.name if consignment.supplier else consignment.origin or ''}".strip(" —"),
            "supplier": consignment.supplier.name if consignment.supplier else None,
            "instrument_number": consignment.instrument_number,
            "snapshot": _import_snapshot(consignment),
        })

    return requests


#--------------------------------
# REVERSE LOOKUP (jobs that came from a given order / consignment)
#--------------------------------

def find_trucking_jobs(db, source, source_ref):
    return db.execute(
        select(TruckingConsignment)
        .where(TruckingConsignment.is_deleted == False)
        .where(TruckingConsignment.source == source)
        .where(TruckingConsignment.source_ref == str(source_ref))
        .options(
            selectinload(TruckingConsignment.vehicles),
            selectinload(TruckingConsignment.change_history),
            joinedload(TruckingConsignment.created_by),
            joinedload(TruckingConsignment.deleted_by),
        )
        .order_by(TruckingConsignment.id.desc())
    ).scalars().all()
