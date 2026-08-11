from decimal import Decimal

from app.dashboard.references import paginate

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

STORED = "stored"
COMPUTED = "computed"
UNVALUED = "unvalued"


def computed_value_pkr(consignment):
    """Rebuilt from the item lines: qty x unit price, at the booked rate.

    Only ever a FALLBACK — see consignment_value_pkr. Returns None when the
    lines carry no price or the consignment has no rate, so "cannot be valued"
    stays distinct from "worth nothing".
    """
    foreign_total = Decimal("0")
    priced = False

    for item in consignment.items:
        if item.is_deleted:
            continue
        if item.quantity is not None and item.unit_price is not None:
            foreign_total += item.quantity * item.unit_price
            priced = True

    if not priced or consignment.exchange_rate is None:
        return None

    return foreign_total * consignment.exchange_rate


def value_basis(consignment):
    """Which of the three cases this consignment falls into."""
    if consignment.pkr_total is not None:
        return STORED
    return COMPUTED if computed_value_pkr(consignment) is not None else UNVALUED


def consignment_value_pkr(consignment):
    """The consignment's PKR value: the booked total, or the lines if there is none.

    THE STORED TOTAL WINS. Imports rule 4: the money totals are stored precisely
    so a later edit or rate change cannot restate a figure that has already been
    printed, and the overview reads the same column — so the same consignment is
    no longer worth two different amounts depending which screen you are on.

    Where nothing was booked, the value is rebuilt from the item lines rather
    than dropped: an unbooked consignment is worth something, and counting it as
    zero understates the period as surely as the old double-basis overstated the
    difference between screens.

    Where neither is possible the consignment contributes nothing and is COUNTED
    as unvalued, so the shortfall is reported rather than absorbed — see
    value_data_notes.

    (Shafts value is the one figure still derived from the lines by design: it
    is the value of the shaft ITEMS, which no consignment-level total can give.)
    """
    if consignment.pkr_total is not None:
        return consignment.pkr_total

    return computed_value_pkr(consignment) or Decimal("0")


#-------------------------------------
# THE HEADLINE NUMBERS (KPIS)
#-------------------------------------

def value_data_notes(consignments):
    """How the money on this screen was arrived at, and what it misses.

    Two things worth saying, and only when they are true:

      * how many consignments had no booked total and were valued from their
        item lines instead — a sound fallback, but a different basis, and the
        reader should know some of the total was reconstructed;
      * how many could not be valued at all, because those contribute nothing
        and would otherwise silently shrink the total.
    """
    from app.dashboard.data_quality import coverage_note, note, collect, WARNING

    total = len(consignments)
    if not total:
        return []

    computed = sum(1 for c in consignments if value_basis(c) == COMPUTED)
    unvalued = sum(1 for c in consignments if value_basis(c) == UNVALUED)

    return collect(
        coverage_note(
            total - unvalued, total, "consignments shown", "a value",
            "The rest contribute nothing to the money figures.",
        ),
        note(WARNING, (
            f"{computed} of {total} consignments have no booked PKR total, so "
            f"their value was rebuilt from the item lines (quantity x unit price "
            f"at the booked rate). The rest use the figure finance booked."
        )) if computed else None,
    )


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


#-------------------------------------
# WHICH CONSIGNMENTS IS THIS NUMBER ABOUT?
#
# Every headline count is an aggregate, and an aggregate on its own cannot be
# checked or acted on: "42 delayed" gives nobody anything to chase. Each KPI
# therefore carries the REFERENCES of the records behind it, so the screen can
# open a list and somebody can go and look them up.
#
# The payment reference is the number the business actually files against (the
# LC or TT number); the GD number, supplier and works come along because a
# consignment is just as often looked up by those. `id` is there so the row can
# be opened in the imports module later.
#
# Capped: a KPI covering hundreds of records does not need to ship them all to
# a popover, and the count is already on the tile. The cap is reported so the
# list can say it is showing the first N.
#-------------------------------------

# The lists are COMPLETE — no cap. Only one page travels per request; the rest
# is fetched from GET /dashboard/imports/references. See app/dashboard/references.



def consignment_reference(consignment):
    """One consignment in the shared reference shape (see ReferenceList).

    `detail` names the items it carries, because "payment ref 70386" alone does
    not tell you what to chase — the same reason the purchases list shows the
    item on each line.
    """
    items = [i.item_name for i in consignment.items if not i.is_deleted and i.item_name]
    detail = ", ".join(items[:2])
    if len(items) > 2:
        detail += f" +{len(items) - 2} more"

    meta = " · ".join(part for part in (
        consignment.supplier.name if consignment.supplier else None,
        consignment.branch.name if consignment.branch else None,
        f"GD {consignment.gd_number}" if consignment.gd_number else None,
    ) if part)

    return {
        "id": consignment.id,
        "reference": consignment.instrument_number or f"IMP-{consignment.id}",
        "detail": detail or None,
        "meta": meta or None,
        "badge": consignment.current_status,
    }


def references(consignments, page=None, page_size=None):
    """The consignments behind a figure, as one page of the complete list."""
    return paginate(
        [consignment_reference(c) for c in consignments], page, page_size
    )


def late_references(dated_consignments, page=None, page_size=None):
    """Delayed consignments ranked by how late they are.

    Takes (days_late, consignment) pairs rather than plain consignments so the
    badge states the lateness instead of repeating the status, which is what
    makes an average legible: you can see the 200-day outlier behind it.
    """
    rows = []
    for days, consignment in sorted(dated_consignments, key=lambda p: p[0], reverse=True):
        row = consignment_reference(consignment)
        row["badge"] = f"{days} days late"
        rows.append(row)

    return paginate(rows, page, page_size)


#-------------------------------------
# COUNT AND VALUE, IN ONE SHAPE
#
# Every consignment figure on this screen — total, in process, arrived,
# delayed — is a set of consignments, and the two things worth knowing about a
# set are how many and how much. They used to be inconsistent: the total showed
# both while In Process showed only a count, so a reader could see that 30
# consignments were in flight but not that they were Rs 96m of the book.
#
# So they all return the SAME shape, valued the SAME way (consignment_value_pkr,
# stored total first — imports rule 4), and the front end renders them
# identically. A figure that cannot be compared with the one beside it is not
# worth showing next to it.
#-------------------------------------

def count_and_value(consignments, total_value=None):
    """{count, value, value_pct} — value_pct against the whole screen's money."""
    value = sum((consignment_value_pkr(c) for c in consignments), Decimal("0"))

    return {
        "count": len(consignments),
        "value": value,
        "value_pct": _pct(float(value), float(total_value)) if total_value else None,
    }


def population_split(consignments):
    """The screen's consignments cut by where they have got to.

    IN PROCESS is everything not yet terminal. ARRIVED and CANCELLED are the two
    terminal states, reported separately because they mean opposite things — an
    arrival is work completed, a cancellation is work abandoned, and folding them
    into one "closed" tile hides the difference.
    """
    total = sum((consignment_value_pkr(c) for c in consignments), Decimal("0"))

    in_process, arrived, cancelled = [], [], []
    for consignment in consignments:
        if consignment.current_status == CLOSED_STATUS:
            arrived.append(consignment)
        elif consignment.current_status in TERMINAL_STATUSES:
            cancelled.append(consignment)
        else:
            in_process.append(consignment)

    return {
        "total": count_and_value(consignments),
        "in_process": count_and_value(in_process, total),
        "arrived": count_and_value(arrived, total),
        "cancelled": count_and_value(cancelled, total),
        "references": {
            "total": references(consignments),
            "in_process": references(in_process),
            "arrived": references(arrived),
            "cancelled": references(cancelled),
        },
    }


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


def shafts_value(consignments, page=None, page_size=None):
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
    carrier_consignments = []

    for consignment in consignments:
        shaft_lines = [i for i in consignment.items if not i.is_deleted and is_shaft(i)]
        if not shaft_lines:
            continue

        carriers += 1
        carrier_consignments.append(consignment)
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
        "references": references(carrier_consignments, page, page_size),
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


def efs_split(consignments, page=None, page_size=None):
    counts = {c: 0 for c in EFS_CLASSES}
    by_class = {c: [] for c in EFS_CLASSES}
    # Value as well as count, for the same reason every other tile carries both:
    # 12 EFS shipments worth Rs 400m and 12 worth Rs 4m are not the same news.

    for consignment in consignments:
        name = consignment.consignment_type or NOT_STATED
        counts[name] = counts.get(name, 0) + 1
        by_class.setdefault(name, []).append(consignment)

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
        # The EFS consignments themselves, so the tile can list them.
        "efs_references": references(by_class[EFS], page, page_size),
        "efs": counts[EFS],
        "efs_value": count_and_value(by_class[EFS])["value"],
        "regular": counts[REGULAR],
        "regular_value": count_and_value(by_class[REGULAR])["value"],
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
    processed_consignments = []

    for consignment in consignments:
        if consignment.current_status in TERMINAL_STATUSES:
            processed += 1
            processed_consignments.append(consignment)

    received = len(consignments)
    in_process = received - processed

    return {
        "received": received,
        "processed": processed,
        "in_process": in_process,
        "processed_pct": _pct(processed, received),
        # Which ones reached a terminal status, so the tile is not a dead end.
        "processed_references": references(processed_consignments),
    }


#-------------------------------------
# DELIVERY DELAY
#-------------------------------------

# A consignment is not "late" for slipping a day or two — port scheduling and
# sailing dates move by that much routinely. Only a slip of MORE THAN A WEEK
# counts as a delay; anything inside the week is on time.
DELAY_GRACE_DAYS = 7


def delivery_delay(consignments, page=None, page_size=None):
    """Delay = ETA Works - required date, in days, beyond a 7-day grace.

    More than 7 days past the required date is delayed. Anything from arriving
    early up to a week late is ON TIME — a couple of days' slip is normal
    scheduling noise, and counting it as a delay made the figure describe the
    shipping calendar rather than a problem worth acting on.

    ETA Works is the arrival at the factory, which is the date the business
    actually cares about — not the port arrival or the gate-out.

    `avg_days_late` covers the delayed consignments only: arriving early is not
    a negative delay to be averaged against them. Only consignments carrying
    BOTH dates can be measured, so the basis travels with the percentage.
    """
    late = 0
    on_time = 0
    within_grace = 0
    total_days_late = 0
    worst = None
    late_consignments = []   # (days_late, consignment), so the list can rank

    for consignment in consignments:
        required = consignment.required_date
        arrival = consignment.eta_works

        if required is None or arrival is None:
            continue

        days = (arrival - required).days

        if days > DELAY_GRACE_DAYS:
            late += 1
            late_consignments.append((days, consignment))
            total_days_late += days
            worst = days if worst is None else max(worst, days)
        else:
            on_time += 1
            if days > 0:
                within_grace += 1

    comparable = late + on_time

    late_value = sum(
        (consignment_value_pkr(c) for _days, c in late_consignments), Decimal("0")
    )

    return {
        "delay_pct": _pct(late, comparable),
        "delayed": late,
        # The money sitting behind the delay, so the tile reports count AND
        # value like every other consignment figure on the screen.
        "delayed_value": late_value,
        "on_time": on_time,
        # The actual delayed consignments, WORST FIRST and badged with their
        # own lateness — the average is only useful if you can see what pulls
        # it. Serves both the Delivery Delay and Avg Days Late tiles: they are
        # computed over exactly this set.
        "delayed_references": late_references(late_consignments, page, page_size),
        # Late, but inside the grace — reported so "on time" is not mistaken
        # for "arrived by the required date".
        "within_grace": within_grace,
        "grace_days": DELAY_GRACE_DAYS,
        "basis": comparable,
        "not_measurable": len(consignments) - comparable,
        "avg_days_late": round(total_days_late / late, 1) if late else None,
        "worst_days_late": worst,
        "definition": (
            f"ETA Works minus required date; more than {DELAY_GRACE_DAYS} days "
            f"late counts as delayed, anything less is on time"
        ),
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
    """Suppliers by spend, with the running cumulative share.

    Valued with consignment_value_pkr — the SAME basis as every other chart on
    this screen. It used to read the stored `pkr_total` instead, which is
    populated on fewer consignments (160 of 178), so this chart went empty while
    the country and works charts beside it showed data from the same rows. Two
    money bases on one screen is a bug whichever way the numbers land.
    """
    totals = {}
    counts = {}

    for consignment in consignments:
        name = consignment.supplier.name if consignment.supplier else "(no supplier)"
        totals[name] = totals.get(name, Decimal("0")) + consignment_value_pkr(consignment)
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
            # Same 7-day grace as the headline delay figure, so a category
            # cannot read as delayed on this chart while the KPI beside it
            # calls the very same consignment on time.
            if days_late > DELAY_GRACE_DAYS:
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


#-----------------------------------------------------
# LINE-LEVEL REFERENCE LISTS
#
# A reference list NEVER HIDES LINES. A consignment carrying three shaft rows
# shows as three rows, each with its own arrival date and its own value.
#
# Folding them into one line per consignment is what made payment ref 65704
# unexplainable: a single row standing for seven lines that arrived on two
# different dates, Rs 8.98m of it in August and Rs 1.25m the previous month.
# Nobody could see that from the list, because the list showed the header.
#
# The KPI still counts CONSIGNMENTS. The list says so — `unit` and `groups`
# carry "3 lines across 1 consignment" — so the two numbers are reconcilable
# instead of merely different.
#-----------------------------------------------------

def line_reference(row):
    """One consignment ITEM line in the shared reference shape."""
    quantity = row.quantity
    unit = row.unit_of_measurement or ""
    measure = f"{quantity:,.3f}".rstrip("0").rstrip(".") if quantity is not None else "?"

    return {
        # The LINE's id, so two identical rows on one consignment stay distinct.
        "id": f"line-{row.id}",
        # The number it is looked up by is still the consignment's.
        "reference": row.instrument_number or f"IMP-{row.consignment_id}",
        "detail": row.item_name,
        "meta": " · ".join(part for part in (
            f"{measure} {unit}".strip() or None,
            f"ETA {row.line_eta}" if row.line_eta else "no ETA",
            row.supplier,
        ) if part),
        "badge": _money(row.value),
    }


def _money(amount):
    value = float(amount or 0)
    if abs(value) >= 1_000_000_000:
        return f"Rs {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"Rs {value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"Rs {value / 1_000:.0f}K"
    return f"Rs {value:,.0f}"


def line_references(rows, page=None, page_size=None):
    """{total in LINES, groups in CONSIGNMENTS} for a set of item lines."""
    return paginate(
        [line_reference(row) for row in rows], page, page_size,
        unit="line",
        groups=len({row.consignment_id for row in rows}),
        group_unit="consignment",
    )


def shafts_from_lines(rows):
    """The shafts tile, computed from the LINES and dated by them.

    It used to take the consignments whose HEADER fell in the window and sum
    their shaft lines — so every line of payment ref 65704 counted as August,
    including the four that arrived on 27 July. Selecting the lines directly and
    filtering on each line's own ETA is what makes the tile agree with the list
    it opens.
    """
    value = sum((Decimal(str(row.value)) for row in rows if row.value is not None),
                Decimal("0"))
    unpriced = sum(1 for row in rows if row.value is None)

    return {
        "value": value,
        "lines": len(rows),
        "consignments": len({row.consignment_id for row in rows}),
        # Lines with no price or no booked rate cannot be valued; counted rather
        # than silently treated as zero.
        "unpriced_lines": unpriced,
        "references": line_references(rows),
    }


def period_value_from_lines(rows):
    """The screen's headline money, summed over LINES and dated by them.

    Same basis and same rows as the Overview's imports period value, so the two
    screens cannot report different money for the same window. `consignments` is
    the distinct consignments having a line in the window — a consignment that
    delivered into two months is counted in both, because it did.
    """
    value = sum((Decimal(str(r.value)) for r in rows if r.value is not None),
                Decimal("0"))

    return {
        "value": value,
        "consignments": len({r.consignment_id for r in rows}),
        "lines": len(rows),
        "unpriced_lines": sum(1 for r in rows if r.value is None),
        "basis": "line ETA at works",
        "references": line_references(rows),
    }


def population_from_lines(rows):
    """In Process / Arrived / Cancelled, on the SAME line-dated money.

    Built from the period's LINES, not from the consignment headers, so this
    screen carries ONE basis for money rather than two: the population tiles
    used to sum consignment-level values (Rs 29.27bn) while the headline summed
    in-window lines (Rs 29.07bn), and two totals on one screen differing only by
    basis is the bug this whole pass exists to remove.

    A consignment is counted in a bucket if it has a line in the window; its
    VALUE in that bucket is only the lines that actually arrived in it.
    """
    buckets = {"in_process": [], "arrived": [], "cancelled": []}

    for row in rows:
        if row.current_status == CLOSED_STATUS:
            buckets["arrived"].append(row)
        elif row.current_status in TERMINAL_STATUSES:
            buckets["cancelled"].append(row)
        else:
            buckets["in_process"].append(row)

    def block(lines, total_value=None):
        value = sum((Decimal(str(r.value)) for r in lines if r.value is not None),
                    Decimal("0"))
        return {
            "count": len({r.consignment_id for r in lines}),
            "lines": len(lines),
            "value": value,
            "value_pct": _pct(float(value), float(total_value)) if total_value else None,
        }

    total = sum((Decimal(str(r.value)) for r in rows if r.value is not None),
                Decimal("0"))

    return {
        "total": block(rows),
        **{name: block(lines, total) for name, lines in buckets.items()},
        "references": {
            "total": line_references(rows),
            **{name: line_references(lines) for name, lines in buckets.items()},
        },
    }
