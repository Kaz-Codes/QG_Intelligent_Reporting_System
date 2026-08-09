from decimal import Decimal

from app.enums import Status

#-------------------------------------
# THE NUMBERS THE IMPORTS DASHBOARD SHOWS
#
# Everything here is worked out from the live consignments,
# nothing is stored. The same rule as the imports module: a
# stored foreign value is converted at the rate booked on
# that consignment, never a live one.
#-------------------------------------

# "Arrived at works" is the end of the line, so anything not
# there yet is still open.
CLOSED_STATUS = Status.ARRIVED_AT_WORKS.value
UNDER_CLEARANCE_STATUS = Status.UNDER_CUSTOM_CLEARANCE.value


#-------------------------------------
# THE PKR VALUE OF ONE CONSIGNMENT
#
# Sum of quantity times unit price across the item lines,
# converted at the consignment's own exchange rate. A line
# with no price is left out rather than counted as zero, and
# a consignment with no rate booked yet has no PKR value.
#-------------------------------------

def consignment_value_pkr(consignment):
    foreign_total = Decimal("0")
    priced = False

    for item in consignment.items:
        if item.quantity is not None and item.unit_price is not None:
            foreign_total = foreign_total + (item.quantity * item.unit_price)
            priced = True

    if not priced or consignment.exchange_rate is None:
        return Decimal("0")

    return foreign_total * consignment.exchange_rate


#-------------------------------------
# THE HEADLINE NUMBERS (KPIS)
#-------------------------------------

def kpis(consignments):
    total_value = Decimal("0")
    open_count = 0
    under_clearance = 0
    suppliers = set()

    for consignment in consignments:
        total_value = total_value + consignment_value_pkr(consignment)

        if consignment.current_status != CLOSED_STATUS:
            open_count = open_count + 1

        if consignment.current_status == UNDER_CLEARANCE_STATUS:
            under_clearance = under_clearance + 1

        if consignment.supplier_id is not None:
            suppliers.add(consignment.supplier_id)

    return {
        "total_value_pkr": total_value,
        "consignments_shown": len(consignments),
        "open": open_count,
        "under_clearance": under_clearance,
        "suppliers": len(suppliers)
    }


#-------------------------------------
# HOW MANY CONSIGNMENTS SIT AT EACH STATUS
#
# In the order goods actually move in, and only statuses
# that are actually present, so the donut is not full of
# empty slices.
#-------------------------------------

def status_split(consignments):
    counts = {}

    for consignment in consignments:
        status = consignment.current_status
        counts[status] = counts.get(status, 0) + 1

    ordered = []

    for status in [s.value for s in Status]:
        if counts.get(status):
            ordered.append({"label": status, "value": counts[status]})

    return ordered


#-------------------------------------
# VALUE GROUPED BY SOMETHING, TOP FIRST
#
# Used for value by country and value by supplier. A generic
# helper so both read from one place. key_fn pulls the label
# off a consignment.
#-------------------------------------

def value_by(consignments, key_fn, limit=None):
    totals = {}

    for consignment in consignments:
        label = key_fn(consignment)

        if not label:
            continue

        totals[label] = totals.get(label, Decimal("0")) + consignment_value_pkr(consignment)

    rows = [
        {"label": label, "value": value}
        for label, value in totals.items()
    ]

    rows.sort(key=lambda row: row["value"], reverse=True)

    if limit is not None:
        rows = rows[:limit]

    return rows


def value_by_country(consignments, limit=8):
    return value_by(consignments, lambda c: c.origin, limit)


def value_by_supplier(consignments, limit=8):
    return value_by(
        consignments,
        lambda c: c.supplier.name if c.supplier else None,
        limit
    )


def value_by_branch(consignments, limit=8):
    return value_by(
        consignments,
        lambda c: c.branch.name if c.branch else None,
        limit
    )


#-------------------------------------
# VALUE OVER TIME, MONTH BY MONTH
#
# Grouped by ETA at works, falling back through ETD/ETA/cargo readiness for
# rows missing it. NOT po_date/created_at: po_date is never populated by the
# current loader, and created_at is just the moment the row was bulk-loaded
# — every consignment in a batch shares the same one, which collapsed the
# whole trend into a single point regardless of any real date or filter.
# Oldest month first, so a line chart reads left to right.
#-------------------------------------

def monthly_value_trend(consignments):
    totals = {}

    for consignment in consignments:
        day = (
            consignment.eta_works or consignment.etd
            or consignment.eta or consignment.cargo_readiness_date
        )

        if day is None:
            continue

        month = day.strftime("%Y-%m")
        totals[month] = totals.get(month, Decimal("0")) + consignment_value_pkr(consignment)

    trend = [
        {"month": month, "value": totals[month]}
        for month in sorted(totals.keys())
    ]

    return trend


#=====================================================
# THE KPI-DOCUMENT FIGURES
#
# Everything below comes from Supply_Chain_KPI's.docx. They are computed over
# the SAME filtered consignment list as the figures above, so the whole screen
# always describes one set of rows.
#
# Ratios carry the row count they were measured over (`*_basis`), because
# several of these rest on a small slice of the book and a bare percentage
# would read as a fact about every consignment.
#=====================================================

TERMINAL_STATUSES = (Status.ARRIVED_AT_WORKS.value, Status.ORDER_CANCELLED.value)


def _pct(part, whole, digits=1):
    if not whole:
        return None
    return round((part / whole) * 100, digits)


#-------------------------------------
# TOTAL IMPORT SPEND
#
# The STORED pkr_total, not the line-by-line recomputation `kpis` does.
# Imports rule 4: the money totals are stored precisely so a later rate change
# or edit cannot restate a printed report. A consignment with no stored total
# contributes nothing rather than being recomputed at some other basis.
#-------------------------------------

def total_import_spend(consignments):
    total = Decimal("0")
    priced = 0

    for consignment in consignments:
        if consignment.pkr_total is not None:
            total += consignment.pkr_total
            priced += 1

    return {
        "value": total,
        "consignments": priced,
        "consignments_without_value": len(consignments) - priced,
    }


#-------------------------------------
# DEMANDS RECEIVED / PROCESSED / IN PROCESS
#
# A "demand" is one consignment. Processed = it reached a terminal state
# (arrived at works, or cancelled — a cancelled demand is finished, not
# pending); in process = everything else. Received is simply all of them, so
# processed + in_process always reconciles back to received.
#-------------------------------------

def demand_counts(consignments):
    processed = 0

    for consignment in consignments:
        if consignment.current_status in TERMINAL_STATUSES:
            processed += 1

    received = len(consignments)
    in_process = received - processed

    return {
        "received": received,
        "processed": processed,
        "in_process": in_process,
        "processed_pct": _pct(processed, received),
    }


#-------------------------------------
# DELAY PERCENTAGE
#
# A demand is late when it arrived (or is now expected) after the date it was
# required. Arrival is the gate-out date where one exists, falling back to the
# current ETA — so a consignment still in transit counts as late the moment its
# ETA passes the required date, instead of dropping out of the measure until it
# lands. Which basis each row used is reported, since the two are not equally
# certain.
#-------------------------------------

def delay_stats(consignments):
    late = 0
    comparable = 0
    on_actual = 0
    total_days_late = 0

    for consignment in consignments:
        required = consignment.required_date
        if required is None:
            continue

        arrival = consignment.gate_out_date
        if arrival is not None:
            on_actual += 1
        else:
            arrival = consignment.eta

        if arrival is None:
            continue

        comparable += 1
        if arrival > required:
            late += 1
            total_days_late += (arrival - required).days

    return {
        "delay_pct": _pct(late, comparable),
        "delayed": late,
        "on_time": comparable - late,
        "basis": comparable,
        "measured_on_actual_arrival": on_actual,
        "avg_days_late": round(total_days_late / late, 1) if late else None,
    }


#-------------------------------------
# SUPPLIER SPEND + CUMULATIVE CONTRIBUTION (the Pareto chart)
#
# Suppliers by spend, descending, each carrying its own share and the running
# cumulative share — the line that makes a Pareto readable. The cumulative
# percentage is computed over EVERY supplier before the list is truncated, so
# the last bar shown still tells the truth about where it sits in the whole
# book rather than summing to 100% over an arbitrary top-N.
#-------------------------------------

def supplier_spend_pareto(consignments, limit=10):
    totals = {}

    for consignment in consignments:
        if consignment.pkr_total is None:
            continue
        name = consignment.supplier.name if consignment.supplier else "(no supplier)"
        totals[name] = totals.get(name, Decimal("0")) + consignment.pkr_total

    grand_total = sum(totals.values(), Decimal("0"))

    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    rows = []
    running = Decimal("0")
    for name, value in ordered:
        running += value
        rows.append({
            "supplier": name,
            "value": value,
            "share_pct": _pct(value, grand_total),
            "cumulative_pct": _pct(running, grand_total),
        })

    return {
        "total": grand_total,
        "suppliers_total": len(ordered),
        "rows": rows[:limit],
    }


#-------------------------------------
# CATEGORY DELAYS
#
# Replaces the chart the document flagged as wrong. Delay is a property of the
# consignment, but category is a property of its item lines, so a consignment
# counts once toward EVERY distinct category it carries — a mixed consignment
# genuinely delays all of them, and splitting its delay across them would
# understate each.
#
# Category comes from the item master through the line's item_id. Lines that do
# not resolve (currently most of them) fall into "Uncategorised" rather than
# disappearing, so the bars still account for every delayed consignment.
#-------------------------------------

UNCATEGORISED = "Uncategorised"


def consignment_categories(consignment):
    categories = set()

    for item in consignment.items:
        if item.is_deleted:
            continue
        category = item.item.category if item.item else None
        categories.add(category or UNCATEGORISED)

    return categories or {UNCATEGORISED}


def category_delays(consignments, limit=10):
    stats = {}

    for consignment in consignments:
        required = consignment.required_date
        if required is None:
            continue

        arrival = consignment.gate_out_date or consignment.eta
        if arrival is None:
            continue

        days_late = (arrival - required).days

        for category in consignment_categories(consignment):
            entry = stats.setdefault(
                category, {"total": 0, "delayed": 0, "days_late": 0}
            )
            entry["total"] += 1
            if days_late > 0:
                entry["delayed"] += 1
                entry["days_late"] += days_late

    rows = [
        {
            "category": category,
            "consignments": entry["total"],
            "delayed": entry["delayed"],
            "delay_pct": _pct(entry["delayed"], entry["total"]),
            "avg_days_late": (
                round(entry["days_late"] / entry["delayed"], 1)
                if entry["delayed"] else None
            ),
        }
        for category, entry in stats.items()
    ]

    # Ranked by the NUMBER of delayed consignments, not the percentage. Sorting
    # on percentage puts categories with a single delayed consignment at 100%
    # above a category with 17 delayed out of 34 — which is noise sitting on top
    # of the real problem. Count first, then percentage to break ties.
    rows.sort(key=lambda r: (r["delayed"], r["delay_pct"] or 0), reverse=True)
    return rows[:limit]
