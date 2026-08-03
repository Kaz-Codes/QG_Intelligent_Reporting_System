from decimal import Decimal

from app.enums import VehicleTrackingStatus

#-----------------------------------------------------
# LOGISTICS DASHBOARD CALCULATIONS
#
# Three independent tabs, three data sources:
#   * Shipments  — LogisticsConsignment (the shipping leg)
#   * Packing    — LogisticsPackage (+ its order)
#   * Transport  — TruckingConsignment (export trucking / shifting)
#
# Everything is derived at request time; the "view data" table is gone, so the
# endpoints return aggregates + filter option lists only, never rows.
#-----------------------------------------------------

DELIVERED = "Delivered"


def _num(value):
    return value if value is not None else Decimal("0")


#=====================================================
# SHIPMENTS  (LogisticsConsignment)
#=====================================================

# The named cost columns on the order; their sum is the total logistics cost.
COST_FIELDS = [
    "packing_cost", "transportation_charges", "container_detention", "insurance",
    "trucking_lhr_to_khi", "fumigation_cost", "lashing", "qfl_charges",
    "qfl_container_movement", "custom_clearance_charges", "port_charges",
    "dhl_charges", "sea_air_freight",
]

# Best-effort roll-up of the order status into the four shipment stages. The
# loaded statuses are messy, so anything unmapped lands in Pre-Shipment.
STAGE_PRE = "Pre-Shipment"
STAGE_TRANSIT = "In Transit"
STAGE_CUSTOMS = "Customs"
STAGE_DELIVERED = "Delivered"
SHIPMENT_STAGES = [STAGE_PRE, STAGE_TRANSIT, STAGE_CUSTOMS, STAGE_DELIVERED]

_STAGE_MAP = {
    "delivered": STAGE_DELIVERED,
    "at port": STAGE_CUSTOMS,
    "at qfl": STAGE_CUSTOMS,
    "on water": STAGE_TRANSIT,
    "sailing": STAGE_TRANSIT,
    "transportation": STAGE_TRANSIT,
    "under shipping arrangement": STAGE_TRANSIT,
    "gate out": STAGE_TRANSIT,
}


def total_logistics_cost(order):
    total = Decimal("0")
    for field in COST_FIELDS:
        total += _num(getattr(order, field))
    return total


def order_gross_weight(order):
    total = Decimal("0")
    for item in order.items:
        if not item.is_deleted and item.gross_weight is not None:
            total += item.gross_weight
    return total


def cost_per_kg(order):
    weight = order_gross_weight(order)
    if weight <= 0:
        return None
    return total_logistics_cost(order) / weight


def shipment_stage(order):
    status = (order.current_status or "").strip().lower()
    return _STAGE_MAP.get(status, STAGE_PRE)


def shipments_kpis(orders):
    total_cost = Decimal("0")
    delivered = 0
    not_yet_linked = 0
    countries = set()
    cpk_values = []

    for order in orders:
        total_cost += total_logistics_cost(order)
        if order.current_status == DELIVERED:
            delivered += 1
        if not order.mo_no:                       # no export number yet
            not_yet_linked += 1
        if order.origin_country:
            countries.add(order.origin_country)
        cpk = cost_per_kg(order)
        if cpk is not None:
            cpk_values.append(cpk)

    avg_cpk = (sum(cpk_values) / len(cpk_values)) if cpk_values else Decimal("0")

    return {
        "shipments_shown": len(orders),
        "delivered": delivered,
        "not_yet_linked": not_yet_linked,
        "total_cost": total_cost,
        "avg_cost_per_kg": avg_cpk,
        "countries": len(countries),
    }


def cost_per_kg_by_country(orders, limit=8):
    sums = {}
    counts = {}
    for order in orders:
        country = order.origin_country
        cpk = cost_per_kg(order)
        if not country or cpk is None:
            continue
        sums[country] = sums.get(country, Decimal("0")) + cpk
        counts[country] = counts.get(country, 0) + 1

    rows = [{"label": c, "value": sums[c] / counts[c]} for c in sums]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:limit]


#=====================================================
# PACKING  (LogisticsPackage + its order)
#=====================================================

PACKED = "Packed"


def rfd_delay_days(package):
    # How many days packing ran past the ready/RFD date. None when either date
    # is missing.
    if package.packing_date is not None and package.packing_ready_date is not None:
        return (package.packing_date - package.packing_ready_date).days
    return None


def packing_kpis(packages):
    total_cost = Decimal("0")
    packed = 0
    delays = []
    categories = set()

    for package in packages:
        total_cost += _num(package.actual_packing_cost)
        if package.status == PACKED:
            packed += 1
        delay = rfd_delay_days(package)
        if delay is not None:
            delays.append(delay)
        order = package.consignment
        if order and order.department:
            categories.add(order.department)

    avg_delay = round(sum(delays) / len(delays), 1) if delays else None

    return {
        "packing_jobs_shown": len(packages),
        "packed": packed,
        "total_cost": total_cost,
        "avg_rfd_delay_days": avg_delay,
        "categories": len(categories),
    }


#=====================================================
# TRANSPORT  (TruckingConsignment — export trucking)
#=====================================================

TRANSPORT_BOOKED = "Booked"
TRANSPORT_IN_PROGRESS = "In Progress"
TRANSPORT_DELIVERED = "Delivered"
TRANSPORT_STATUSES = [TRANSPORT_BOOKED, TRANSPORT_IN_PROGRESS, TRANSPORT_DELIVERED]


def transport_status(job):
    # Trucking has no stored job status — it is a rollup over the vehicles.
    active = [v for v in job.vehicles if not v.is_deleted]
    if not active:
        return TRANSPORT_BOOKED
    if all(v.tracking_status == VehicleTrackingStatus.DELIVERED.value for v in active):
        return TRANSPORT_DELIVERED
    return TRANSPORT_IN_PROGRESS


# Customer / city / province are not on the trucking job — for a job that came
# from a logistics order they live on that order (resolved into `links`).

def _job_link(job, links):
    if job.source == "from-logistics" and job.source_ref:
        return links.get(job.source_ref)
    return None


def job_customer(job, links):
    link = _job_link(job, links)
    return link.get("customer") if link else None


def job_province(job, links):
    link = _job_link(job, links)
    return link.get("province") if link else None


def job_city(job, links):
    link = _job_link(job, links)
    return link.get("city") if link else None


def freight_savings(job):
    if job.quoted_freight is not None and job.actual_freight is not None:
        saving = job.quoted_freight - job.actual_freight
        return saving if saving > 0 else Decimal("0")
    return Decimal("0")


def transport_kpis(jobs):
    delivered = 0
    in_progress = 0
    total_freight = Decimal("0")
    total_savings = Decimal("0")

    for job in jobs:
        status = transport_status(job)
        if status == TRANSPORT_DELIVERED:
            delivered += 1
        elif status == TRANSPORT_IN_PROGRESS:
            in_progress += 1
        total_freight += _num(job.actual_freight)
        total_savings += freight_savings(job)

    return {
        "jobs_shown": len(jobs),
        "delivered": delivered,
        "in_progress": in_progress,
        "total_freight": total_freight,
        "total_savings": total_savings,
    }


#=====================================================
# SHARED CHART HELPER
#=====================================================

def count_split(items, label_fn, order=None):
    """[{label, value}] counts. If `order` (a list of labels) is given the
    output follows it and keeps only present labels; otherwise it is sorted by
    count, descending."""
    counts = {}
    for item in items:
        label = label_fn(item)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1

    if order is not None:
        return [{"label": lbl, "value": counts[lbl]} for lbl in order if counts.get(lbl)]

    rows = [{"label": lbl, "value": count} for lbl, count in counts.items()]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows
