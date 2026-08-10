from decimal import Decimal

from app.dashboard.period import build_trend
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
    """Consignments per status, in the order goods actually move.

    Carries the value too, so the donut's tooltip can show what is sitting at
    each stage — a count alone does not say whether the money is stuck.
    """
    counts = {}
    values = {}

    for consignment in consignments:
        status = consignment.current_status
        counts[status] = counts.get(status, 0) + 1
        values[status] = values.get(status, Decimal("0")) + consignment_value_pkr(consignment)

    return [
        {"label": status, "count": counts[status], "value": values[status]}
        for status in [s.value for s in Status]
        if counts.get(status)
    ]


#-------------------------------------
# VALUE GROUPED BY SOMETHING, TOP FIRST
#
# Used for value by country and value by supplier. A generic
# helper so both read from one place. key_fn pulls the label
# off a consignment.
#-------------------------------------

def value_by(consignments, key_fn, limit=None):
    """A breakdown carrying BOTH the count and the value.

    The chart axis plots `count` — how many consignments — because that is the
    question these charts answer, and because a rupee axis on this data prints
    500,496,002 against every gridline. `value` rides along for the tooltip,
    formatted to K/M/B there.

    Sorted by VALUE: the biggest bar should be the one worth most attention, not
    merely the most numerous.
    """
    stats = {}

    for consignment in consignments:
        label = key_fn(consignment)

        if not label:
            continue

        entry = stats.setdefault(label, {"count": 0, "value": Decimal("0")})
        entry["count"] += 1
        entry["value"] += consignment_value_pkr(consignment)

    rows = [
        {"label": label, "count": entry["count"], "value": entry["value"]}
        for label, entry in stats.items()
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

def value_trend(consignments, period_from, period_to):
    """Import value over the window, bucketed to fit it.

    3-day steps inside a month, weeks across a quarter, months beyond — a
    month-long window bucketed by month is one bar. Empty buckets are kept so
    the line never draws straight across a gap.

    Dated on ETA Works (arrival at the factory, the same date the window and the
    delay figure use), falling back through ETD / ETA / cargo readiness for rows
    that have none.
    """
    dated = []
    undated = 0

    for consignment in consignments:
        day = (
            consignment.eta_works or consignment.etd
            or consignment.eta or consignment.cargo_readiness_date
        )

        if day is None:
            undated += 1
            continue

        dated.append((day, consignment_value_pkr(consignment)))

    trend = build_trend(period_from, period_to, dated)
    trend["undated_consignments"] = undated
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
# SHAFTS VALUE
#
# Replaces the old "total import spend" tile, which said the same thing as
# `kpis.total_value_pkr` sitting next to it.
#
# This is the value of the SHAFT LINES, not of the consignments that happen to
# carry one. A consignment usually carries other items too, so its total would
# overstate shafts badly — currently Rs 98.9m of consignment value against
# Rs 30.8m of actual shaft lines.
#
# Line value is quantity x unit price at the consignment's own booked rate
# (imports rule 4: never a live rate). A line with no price or no rate is
# counted as unpriced rather than as zero, and the count is reported.
#-------------------------------------

SHAFT_NAMES = [
    "Forged Alloy Steel Round Bar",
    "Forged Steel Hollow Drill Bars",
    "Forged Steel Alloy Round Bar",
    "Forged Steel Round Bar",
]


def is_shaft(item):
    name = (item.item_name or "").strip().lower()
    return any(shaft.lower() in name for shaft in SHAFT_NAMES)


def shafts_value(consignments):
    """What the shafts are worth, counted in CONSIGNMENTS.

    The value has to be read off the item lines — it is the shaft rows that
    carry the price — but nothing line-level is reported. The count is
    consignments carrying shafts, and `incomplete` is how many of those had a
    shaft row with no price or no booked rate, so a short total is explained
    rather than silently short.
    """
    total = Decimal("0")
    carriers = 0
    incomplete = 0

    for consignment in consignments:
        shaft_lines = [i for i in consignment.items if not i.is_deleted and is_shaft(i)]
        if not shaft_lines:
            continue

        carriers += 1
        missing = False

        for item in shaft_lines:
            if (item.quantity is None or item.unit_price is None
                    or consignment.exchange_rate is None):
                missing = True
                continue
            total += item.quantity * item.unit_price * consignment.exchange_rate

        if missing:
            incomplete += 1

    return {
        "value": total,
        "consignments": carriers,
        "incomplete_consignments": incomplete,
        "item_names": SHAFT_NAMES,
    }


#-------------------------------------
# EFS vs NON-EFS
#
# `consignment_type` carries the sheet's EFS column. Over half the records do
# not state it, so "Not stated" is its own bucket — folding it into Regular
# would assert something the sheet never said, and on this data that single
# assumption would move the split from 25/54 to 25/153.
#-------------------------------------

EFS = "EFS"
REGULAR = "Regular import"
NOT_STATED = "Not stated"
EFS_CLASSES = [EFS, REGULAR, NOT_STATED]


def efs_split(consignments):
    counts = {c: 0 for c in EFS_CLASSES}

    for consignment in consignments:
        counts[consignment.consignment_type or NOT_STATED] = (
            counts.get(consignment.consignment_type or NOT_STATED, 0) + 1
        )

    total = len(consignments)
    stated = counts[EFS] + counts[REGULAR]

    return {
        "counts": [
            {
                "label": name,
                "consignments": counts[name],
                "pct": round(counts[name] / total * 100, 1) if total else None,
            }
            for name in EFS_CLASSES
        ],
        "efs": counts[EFS],
        "regular": counts[REGULAR],
        "not_stated": counts[NOT_STATED],
        # The share among records that actually say — reported separately so a
        # reader can use it without mistaking it for a share of everything.
        "efs_pct_of_stated": round(counts[EFS] / stated * 100, 1) if stated else None,
        "stated_basis": stated,
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
# DELIVERY DELAY
#-------------------------------------

def delivery_delay(consignments):
    """Delay = ETA Works - required date, in days.

    Positive means it reached works AFTER it was needed. Zero or negative is on
    time — arriving early is not a negative delay to be averaged against the
    late ones, so `avg_days_late` covers the late consignments only.

    ETA Works is the arrival at the factory, which is the date the business
    actually cares about — not the port arrival or the gate-out.

    Only consignments carrying BOTH dates can be measured (95 of 178 today), so
    the basis travels with the percentage.
    """
    late = 0
    on_time = 0
    total_days_late = 0
    worst = None

    for consignment in consignments:
        required = consignment.required_date
        arrival = consignment.eta_works

        if required is None or arrival is None:
            continue

        days = (arrival - required).days

        if days > 0:
            late += 1
            total_days_late += days
            worst = days if worst is None else max(worst, days)
        else:
            on_time += 1

    comparable = late + on_time

    return {
        "delay_pct": _pct(late, comparable),
        "delayed": late,
        "on_time": on_time,
        "basis": comparable,
        "not_measurable": len(consignments) - comparable,
        "avg_days_late": round(total_days_late / late, 1) if late else None,
        "worst_days_late": worst,
        "definition": "ETA Works minus required date; 0 or less is on time",
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
    counts = {}

    for consignment in consignments:
        if consignment.pkr_total is None:
            continue
        name = consignment.supplier.name if consignment.supplier else "(no supplier)"
        totals[name] = totals.get(name, Decimal("0")) + consignment.pkr_total
        counts[name] = counts.get(name, 0) + 1

    grand_total = sum(totals.values(), Decimal("0"))

    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    rows = []
    running = Decimal("0")
    for name, value in ordered:
        running += value
        rows.append({
            # `label`/`count` so this drops into the same chart component as
            # every other breakdown: count on the axis, value on hover.
            "label": name,
            "supplier": name,
            "count": counts[name],
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

        for category in consignment_categories(consignment):  # noqa: E501
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
            # `label`/`count` so this feeds the same chart component as every
            # other breakdown: the bar plots delayed CONSIGNMENTS.
            "label": category,
            "count": entry["delayed"],
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
