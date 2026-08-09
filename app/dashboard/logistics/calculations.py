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


#-----------------------------------------------------
# THE KPI-DOCUMENT FIGURES  (Logistics)
#
# From Supply_Chain_KPI's.docx, computed over the same filtered orders as the
# figures above. As elsewhere, every ratio carries the row count it was
# measured over — the delivery dates are sparse and the percentage would
# otherwise read as a fact about all 1,400+ orders.
#-----------------------------------------------------

# An order counts as DISPATCHED once it has actually arrived somewhere, i.e. it
# has an actual_arrival_date. Status alone will not do: the loaded status
# vocabulary has no "dispatched" value, and an order can sit at "Transportation"
# indefinitely.
#
# ON TIME / DELAYED is a narrower measure again — it needs a PLANNED date to
# compare against (cro_arrival_date), which fewer orders carry. So dispatched
# and on-time have different denominators by design, and both are reported.

def is_dispatched(order):
    return order.actual_arrival_date is not None


def arrival_delay_days(order):
    # Positive = arrived after the date it was due. None when either date is
    # missing, which is most orders.
    if order.actual_arrival_date is None or order.cro_arrival_date is None:
        return None
    return (order.actual_arrival_date - order.cro_arrival_date).days


def _pct(part, whole, digits=1):
    if not whole:
        return None
    return round((part / whole) * 100, digits)


def dispatch_kpis(orders):
    dispatched = 0
    weight = Decimal("0")
    on_time = 0
    delayed = 0
    delay_days = []

    for order in orders:
        if is_dispatched(order):
            dispatched += 1
            weight += order_gross_weight(order)

        days = arrival_delay_days(order)
        if days is None:
            continue
        if days > 0:
            delayed += 1
            delay_days.append(days)
        else:
            on_time += 1

    measured = on_time + delayed

    return {
        "total_dispatches": dispatched,
        # Kept in kg — the unit the data is in. Tonnes are a display choice and
        # converting here would bake a rounding into the stored figure.
        "total_weight_dispatched_kg": weight,
        "on_time_dispatches": on_time,
        "delayed_dispatches": delayed,
        "on_time_pct": _pct(on_time, measured),
        "basis": measured,
        "avg_days_late": round(sum(delay_days) / len(delay_days), 1) if delay_days else None,
    }


#-------------------------------------
# TOTAL vs ON-TIME vs DELAYED BY SEGMENT
#
# `department` (Sugar / Cement) is the business segment. Orders without one are
# grouped under "Unassigned" rather than dropped, so the segments still add up
# to the total on the KPI tile beside them.
#
# COVERAGE WARNING, and it is not hypothetical: in the loaded data `department`
# is populated on 810 orders and NULL on 614 — and the 614 are precisely the
# ones carrying arrival dates. So every order this chart can measure is
# currently Unassigned, and the chart draws a single meaningless bar.
#
# `segmented` / `unsegmented` are returned so the front end can detect that and
# show "no segment data" instead of one bar that looks like a finding. The
# figures are correct either way; it is the segmentation that is missing.
#-------------------------------------

UNASSIGNED = "Unassigned"


def dispatch_by_segment(orders, segment_fn=None):
    segment_fn = segment_fn or (lambda o: o.department)
    stats = {}
    segmented = 0
    unsegmented = 0

    for order in orders:
        days = arrival_delay_days(order)
        if days is None:
            continue

        segment = segment_fn(order)
        if segment:
            segmented += 1
        else:
            unsegmented += 1

        entry = stats.setdefault(
            segment or UNASSIGNED,
            {"total": 0, "on_time": 0, "delayed": 0},
        )
        entry["total"] += 1
        if days > 0:
            entry["delayed"] += 1
        else:
            entry["on_time"] += 1

    rows = [
        {
            "segment": segment,
            "total": entry["total"],
            "on_time": entry["on_time"],
            "delayed": entry["delayed"],
            "on_time_pct": _pct(entry["on_time"], entry["total"]),
        }
        for segment, entry in stats.items()
    ]
    rows.sort(key=lambda r: r["total"], reverse=True)

    return {
        "rows": rows,
        "segmented": segmented,
        "unsegmented": unsegmented,
        "has_segmentation": segmented > 0,
    }


#-------------------------------------
# CONTAINER TYPE USAGE
#
# Counted over the container rows of the filtered orders, not the orders
# themselves — one order can ship several containers of different types.
#-------------------------------------

def container_type_usage(orders):
    counts = {}
    total = 0

    for order in orders:
        for container in order.containers:
            if container.is_deleted:
                continue
            total += 1
            label = container.container_type or "(unspecified)"
            counts[label] = counts.get(label, 0) + 1

    rows = [
        {"container_type": label, "containers": count, "share_pct": _pct(count, total)}
        for label, count in counts.items()
    ]
    rows.sort(key=lambda r: r["containers"], reverse=True)
    return {"total": total, "rows": rows}


#-------------------------------------
# CUSTOMER-WISE DELAY
#
# The document asks for customers whose orders ran more than 7 days late. The
# threshold is a parameter, not a literal, so the same function serves a
# different cut-off later.
#-------------------------------------

DELAY_THRESHOLD_DAYS = 7


def customer_delays(orders, threshold_days=DELAY_THRESHOLD_DAYS, limit=10):
    stats = {}

    for order in orders:
        days = arrival_delay_days(order)
        if days is None or days <= threshold_days:
            continue

        entry = stats.setdefault(
            order.customer_name or "(no customer)",
            {"orders": 0, "days": 0, "worst": 0},
        )
        entry["orders"] += 1
        entry["days"] += days
        entry["worst"] = max(entry["worst"], days)

    rows = [
        {
            "customer": customer,
            "delayed_orders": entry["orders"],
            "avg_days_late": round(entry["days"] / entry["orders"], 1),
            "worst_days_late": entry["worst"],
        }
        for customer, entry in stats.items()
    ]
    rows.sort(key=lambda r: r["avg_days_late"], reverse=True)

    return {"threshold_days": threshold_days, "customers": len(rows), "rows": rows[:limit]}


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


#-------------------------------------
# PACKING COST KPIS (KPI document)
#
# The document asks for total packages, total weight, quoted cost, actual cost,
# savings and average saving per kg.
#
# Weight and package count are solid. THE COST FIGURES ARE NOT: no package in
# the loaded data carries an actual_packing_cost and only a handful carry a
# quoted one, so savings and saving-per-kg have nothing to compute from.
#
# Rather than return a confident Rs 0 — which reads as "we packed for free" —
# each cost figure reports how many packages it was actually measured over, and
# savings stay None until BOTH sides of the subtraction exist on the same
# package. The front end can show "awaiting data" instead of a wrong number.
#-------------------------------------

def packing_cost_kpis(packages):
    total_weight = Decimal("0")
    weighed = 0

    quoted_total = Decimal("0")
    quoted_count = 0
    actual_total = Decimal("0")
    actual_count = 0

    # Savings are only meaningful per package that has both figures; summing
    # two differently-populated columns and subtracting would invent a number.
    comparable_saving = Decimal("0")
    comparable_weight = Decimal("0")
    comparable_count = 0

    for package in packages:
        weight = package.gross_weight
        if weight is not None:
            total_weight += weight
            weighed += 1

        quoted = package.quoted_packing_cost
        actual = package.actual_packing_cost

        if quoted is not None:
            quoted_total += quoted
            quoted_count += 1
        if actual is not None:
            actual_total += actual
            actual_count += 1

        if quoted is not None and actual is not None:
            comparable_saving += quoted - actual
            comparable_count += 1
            if weight is not None:
                comparable_weight += weight

    avg_saving_per_kg = (
        comparable_saving / comparable_weight if comparable_weight > 0 else None
    )

    return {
        "total_packages": len(packages),
        "total_weight_kg": total_weight,
        "packages_with_weight": weighed,

        "total_quoted_cost": quoted_total,
        "packages_with_quoted_cost": quoted_count,
        "total_actual_cost": actual_total,
        "packages_with_actual_cost": actual_count,

        "total_savings": comparable_saving if comparable_count else None,
        "avg_saving_per_kg": avg_saving_per_kg,
        "savings_basis": comparable_count,
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
