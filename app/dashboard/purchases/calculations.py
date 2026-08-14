from decimal import Decimal

from app.dashboard.references import paginate, search_filter

from app.dashboard.period import build_trend

#-----------------------------------------------------
# PURCHASES DASHBOARD CALCULATIONS
#
# Built on the flat PurchasesData table — one row per purchase line, with the
# PO-level fields repeated per row. Every figure here is derived from those
# rows; nothing is stored.
#
# Status is derived, not a column:
#   * no purchase date yet          -> Pending
#   * purchased on/before required  -> On Time
#   * required date < purchase date -> Delayed (purchased late)
# days_overdue is how many days late a Delayed row is.
#-----------------------------------------------------

STATUS_PENDING = "Pending"
STATUS_COMPLETED = "On Time"
STATUS_DELAYED = "Delayed"
PURCHASE_STATUSES = [STATUS_PENDING, STATUS_COMPLETED, STATUS_DELAYED]


def derive_status(purchase, required_d):
    if purchase is None:
        return STATUS_PENDING
    if required_d is not None and required_d < purchase:
        return STATUS_DELAYED
    return STATUS_COMPLETED


def days_overdue(purchase, required_d):
    if purchase is not None and required_d is not None and required_d < purchase:
        return (purchase - required_d).days
    return None


def _amount(row):
    return row.amount or Decimal("0")


def total_value(rows):
    total = Decimal("0")
    for row in rows:
        total += _amount(row)
    return total


#-------------------------------------
# HEADLINE NUMBERS (KPIS)
#-------------------------------------

# "Import (IOL)" is not a supplier — it is the in-house import channel, and at
# Rs 1.59bn it is the largest line in the table by a wide margin. Left in, it
# wins "top supplier" on every screen and crowds the real vendors out of the
# supplier chart, which is a statement about how the data is coded rather than
# about who the business buys from.
#
# It is excluded from SUPPLIER figures only. Its spend still counts in the
# totals, because the money was genuinely spent.
NON_SUPPLIERS = {"import (iol)"}


def is_real_supplier(name):
    return bool(name) and name.strip().lower() not in NON_SUPPLIERS


#-----------------------------------------------------
# ORDERS, NOT LINES
#
# Everything the dashboard counts is an ORDER. The source is one row per item
# line — a PO with five lines is five rows — and counting those rows made every
# figure roughly three times the number of orders actually placed, which is why
# "22,333 orders" sat next to "8,572 delayed" and neither could be compared to
# the other.
#
# So rows are grouped by PO number first, and every count below is over the
# resulting orders. Value still sums across all the lines of an order, because
# an order is worth what its lines cost.
#
# A row with no PO number cannot be grouped and stands as its own order, keyed
# on its id so two such rows never merge by accident.
#-----------------------------------------------------

def group_orders(rows):
    """[[row, ...], ...] — the lines of each purchase order."""
    orders = {}

    for row in rows:
        key = ("po", row.po_number.strip()) if row.po_number else ("row", row.id)
        orders.setdefault(key, []).append(row)

    return list(orders.values())


def order_status(lines):
    """One status for a whole order, from its lines.

    Worst case wins, because an order is not finished while any part of it is
    outstanding:
      * any line not yet purchased  -> Pending
      * else any line bought late   -> Delayed
      * else                        -> On Time
    """
    if any(line.purchase is None for line in lines):
        return STATUS_PENDING

    if any(line.required_d is not None and line.required_d < line.purchase
           for line in lines):
        return STATUS_DELAYED

    return STATUS_COMPLETED


def order_value(lines):
    return sum((_amount(line) for line in lines), Decimal("0"))


def line_days_late(line):
    """How late one purchase line was. None if on time or not comparable."""
    if line.purchase is None or line.required_d is None:
        return None
    days = (line.purchase - line.required_d).days
    return days if days > 0 else None


def order_days_late(lines):
    """How late the order was: the AVERAGE across its late lines.

    Averaged rather than taking the worst line. The worst line answers "when did
    this order finally complete", which is a real question but a harsh one — a
    six-line order with five lines on time and one 90 days late read as 90 days
    late, and the headline average was then an average of worst cases.

    The average says how late the order ran overall, which is what a figure
    labelled "average delay" should mean. The per-line detail is one click away
    on the tile, so nothing is lost — the outlier line is still visible, it just
    no longer speaks for the whole order.

    None when no line was late.
    """
    late = [d for d in (line_days_late(line) for line in lines) if d is not None]
    return (sum(late) / len(late)) if late else None


def kpis(rows, orders=None):
    """Headline figures, every count over ORDERS rather than item lines."""
    orders = orders if orders is not None else group_orders(rows)

    orders_count = len(orders)
    value = total_value(rows)
    avg_order_value = (value / orders_count) if orders_count else Decimal("0")

    pending = completed = delayed = 0

    for lines in orders:
        status = order_status(lines)
        if status == STATUS_PENDING:
            pending += 1
        elif status == STATUS_DELAYED:
            delayed += 1
        else:
            completed += 1

    # Supplier spend is still summed over lines — an order's money is its
    # lines' money — but Import (IOL) is left out; see NON_SUPPLIERS.
    supplier_totals = {}
    excluded_value = Decimal("0")
    unattributed_value = Decimal("0")
    unattributed_lines = 0

    for row in rows:
        if is_real_supplier(row.supplier):
            supplier_totals[row.supplier] = supplier_totals.get(row.supplier, Decimal("0")) + _amount(row)
        elif row.supplier:
            excluded_value += _amount(row)
        else:
            # NO SUPPLIER AT ALL. Mostly in-house companies, whose supplier is
            # nulled at load because the group buying from itself is not a
            # vendor relationship (see load_02_purchases_data). This money is
            # real and is inside Total Value, but it belongs to no supplier —
            # so it is reported rather than left to vanish from every supplier
            # figure without explanation.
            unattributed_value += _amount(row)
            unattributed_lines += 1

    top_supplier = None
    top_supplier_amount = Decimal("0")
    if supplier_totals:
        top_supplier, top_supplier_amount = max(supplier_totals.items(), key=lambda kv: kv[1])

    # Of the orders actually purchased, how many landed on time.
    purchased = completed + delayed
    # ONE DECIMAL PLACE, matching the Overview's delay rate. Rounding the same
    # 64-of-180 to a whole number here and to a decimal there put "36%" beside
    # "35.6%" for one figure — a trivial-looking difference that still makes a
    # reader check whether the two screens are counting the same thing.
    on_time_pct = round((completed / purchased) * 100, 1) if purchased else 0
    # Stated as a percentage on the SAME denominator as on-time, so the two
    # tiles are directly comparable and sum to 100. The count is still
    # published as `delayed_orders` and shown by the tile's drill-down.
    delayed_pct = round((delayed / purchased) * 100, 1) if purchased else 0

    return {
        "orders_count": orders_count,
        "total_value": value,
        "avg_order_value": avg_order_value,
        "pending_orders": pending,
        "completed_orders": completed,
        "delayed_orders": delayed,
        "on_time_pct": on_time_pct,
        "delayed_pct": delayed_pct,
        # The denominator both percentages rest on: orders actually purchased.
        # Pending orders are in neither, which is why the two do not describe
        # `orders_count`.
        "purchased_orders": purchased,
        "top_supplier": top_supplier,
        "top_supplier_amount": top_supplier_amount,
        # Named so the screen can say WHY the supplier figures and the total do
        # not reconcile, instead of leaving the gap to be discovered.
        "excluded_from_supplier_figures": sorted(NON_SUPPLIERS),
        "excluded_supplier_value": excluded_value,
        # Money on lines carrying no supplier at all — in-house purchases,
        # nulled at load. In Total Value, in no supplier bucket.
        "unattributed_value": unattributed_value,
        "unattributed_lines": unattributed_lines,
    }


#-------------------------------------
# BREAKDOWNS
#-------------------------------------

#-------------------------------------
# CHART ROWS: COUNT ON THE AXIS, VALUE ON HOVER
#
# Every breakdown returns BOTH numbers per bar:
#   count — how many orders, which is what the axis plots
#   value — what they are worth, which the tooltip shows
#
# The axis is a count because that is the question these charts answer ("where
# are the orders?"), and because a rupee axis on this data prints
# 4,622,808,663 against every gridline. The money is not lost — it is one hover
# away, formatted to K/M/B.
#
# Sorted by VALUE, not count: the biggest bar should be the one worth most
# attention, and a supplier with 400 tiny orders is not more important than one
# with 12 large ones.
#-------------------------------------

def breakdown_by(orders, key_fn, limit=None):
    stats = {}

    for lines in orders:
        label = key_fn(lines[0])
        if not label:
            continue
        entry = stats.setdefault(label, {"count": 0, "value": Decimal("0")})
        entry["count"] += 1
        entry["value"] += order_value(lines)

    result = [
        {"label": label, "count": entry["count"], "value": entry["value"]}
        for label, entry in stats.items()
    ]
    result.sort(key=lambda r: r["value"], reverse=True)

    return result[:limit] if limit is not None else result


def value_by_supplier(orders, limit=8):
    # Real vendors only — see NON_SUPPLIERS.
    return breakdown_by(
        orders, lambda r: r.supplier if is_real_supplier(r.supplier) else None, limit
    )


def value_by_branch(orders, limit=8):
    return breakdown_by(orders, lambda r: r.branch, limit)


def status_split(orders):
    """Orders per status — the same roll-up the KPI tiles count."""
    counts = {}
    values = {}

    for lines in orders:
        status = order_status(lines)
        counts[status] = counts.get(status, 0) + 1
        values[status] = values.get(status, Decimal("0")) + order_value(lines)

    return [
        {"label": status, "count": counts[status], "value": values[status]}
        for status in PURCHASE_STATUSES
        if counts.get(status)
    ]


#-------------------------------------
# DELAYED ORDERS — DAYS OVERDUE (aging buckets)
#
# The "Days Overdue" bar chart on the purchases dashboard. Every Delayed row is
# bucketed by how many days late it was purchased, into the four standard aging
# tiers the front end uses across the app. Returned in a fixed order (empty tiers
# kept, so the bars stay in place), shaped to match the AgingBuckets component:
# [{"bucket": "0-30 days", "orders": N}, ...].
#-------------------------------------

AGING_TIERS = ["0-30 days", "31-60 days", "61-90 days", "90+ days"]


def _aging_tier(days):
    if days <= 30:
        return "0-30 days"
    if days <= 60:
        return "31-60 days"
    if days <= 90:
        return "61-90 days"
    return "90+ days"


def overdue_buckets(orders):
    """Delayed ORDERS by how late they were, with their value for the tooltip."""
    counts = {tier: 0 for tier in AGING_TIERS}
    values = {tier: Decimal("0") for tier in AGING_TIERS}

    for lines in orders:
        overdue = order_days_late(lines)
        if overdue is None:
            continue
        tier = _aging_tier(overdue)
        counts[tier] += 1
        values[tier] += order_value(lines)

    return [
        {"bucket": tier, "orders": counts[tier], "count": counts[tier], "value": values[tier]}
        for tier in AGING_TIERS
    ]


def value_trend(orders, period_from, period_to, date_field=None):
    """Spend over the window, bucketed to fit it.

    The bucket size comes from the window, not the calendar: a month-long
    window bucketed by month is a single bar, so it splits into 3-day steps
    instead (see period.build_trend). Empty buckets are kept, so the line never
    draws straight across a gap it has no data for.

    One point per ORDER, dated on its earliest date **on the field the window
    itself is filtered on** (falling back to the other field only when the
    primary is missing on a line), so an order spanning several deliveries
    lands once rather than once per line.

    `date_field` matters: `fetch_filtered_consignments` includes a LINE only
    when ITS OWN value of that field falls in the window — so every line
    reaching here already has a non-null, in-window value there. Hardcoding
    "purchase, falling back to po_date" regardless of which field the caller
    actually filtered on used to silently drop an order from the trend
    whenever its (different, real, but not the field being windowed on)
    purchase date happened to fall outside the window — `kpis.orders_count`
    still counted it, since it never applied that filter at all.
    """
    dated = []
    undated = 0

    if date_field == "po_date":
        primary = lambda line: line.po_date
        fallback = lambda line: line.purchase
    else:
        primary = lambda line: line.purchase
        fallback = lambda line: line.po_date

    for lines in orders:
        days = [primary(line) or fallback(line) for line in lines]
        days = [d for d in days if d is not None]

        if not days:
            undated += 1
            continue

        dated.append((min(days), order_value(lines)))

    trend = build_trend(period_from, period_to, dated)
    trend["undated_orders"] = undated
    return trend


#=====================================================
# THE KPI-DOCUMENT FIGURES  (Local Procurement)
#
# The document asks for four: total purchase quantity, total value (PKR),
# purchase delay and on-time rate. Two of them already exist above —
# `kpis.total_value` and `kpis.on_time_pct` — so only the missing two are added
# here, computed over the same filtered rows.
#=====================================================

#-------------------------------------
# WHAT IS BEHIND A DELAY FIGURE
#
# The headline is per ORDER, because that is the unit the screen counts in. But
# an order is late because particular LINES were late, and "order 4471 is 12
# days late" is not actionable — which item, and by how much, is.
#
# So the drill-down is per line: the PO it belongs to, the item, its own
# lateness and what it cost. Sorted worst first, because the reason anybody
# opens this list is to find what to chase.
#-------------------------------------

# Complete lists, one page per request — see app/dashboard/references.



def _money(amount):
    value = float(amount or 0)
    if abs(value) >= 1_000_000_000:
        return f"Rs {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"Rs {value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"Rs {value / 1_000:.0f}K"
    return f"Rs {value:,.0f}"


def order_references(orders, page=None, page_size=None, badge=None, search=None):
    """The ORDERS behind a figure — PO, what it was for, and what it cost.

    `badge` decides what the right-hand figure says; it defaults to the order's
    value, which is what most tiles here are about. Sorted by value so the list
    opens on the orders worth looking at first.
    """
    rows = []

    for lines in orders:
        head = lines[0]
        items = [line.item_name for line in lines if line.item_name]
        detail = ", ".join(items[:2])
        if len(items) > 2:
            detail += f" +{len(items) - 2} more"

        value = order_value(lines)
        rows.append({
            "id": head.id,
            "reference": head.po_number or head.ref_no or f"row-{head.id}",
            "detail": detail or None,
            "meta": " · ".join(p for p in (head.supplier, head.branch) if p) or None,
            "badge": badge(lines) if badge else _money(value),
            "sort": float(value),
        })

    rows.sort(key=lambda r: r["sort"], reverse=True)
    for row in rows:
        row.pop("sort")

    return paginate(search_filter(rows, search), page, page_size)


def orders_with_status(orders, status):
    return [lines for lines in orders if order_status(lines) == status]


def supplier_orders(orders, supplier):
    """Every order placed with one supplier — behind the Top Supplier tile."""
    if not supplier:
        return []
    return [lines for lines in orders if lines[0].supplier == supplier]


#-------------------------------------
# THE THREE ORDER COUNTS, AND WHY THEY ARE NOW ONE
#
# Every KPI on this screen counts ORDERS (see group_orders). The reference list
# behind a KPI must therefore ALSO count orders, or the tile and the list it
# opens contradict each other — which is exactly what happened: the Delayed
# tile read 247 while the list it opened reported 454, because the list was
# built from LINES. 454 was not wrong, it was a different question: 247 orders
# were late, and between them they had 454 late lines.
#
# So:
#   delayed_references       247 ORDERS — what the tile counts, badged with
#                                that order's own average lateness
#   delayed_line_references  454 LINES  — the breakdown WITHIN those orders,
#                                for the line-level drill-down
#
# Both are published, each labelled with its own unit. Nothing is inferred from
# the other.
#-------------------------------------

def _days(value):
    """23.0 -> "23", 23.5 -> "23.5". A whole number of days should read like one."""
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def delayed_references(orders, page=None, page_size=None, search=None):
    """The delayed ORDERS — one row per order, latest first.

    Its total equals `kpis.delayed_orders` by construction: both are
    `order_status(lines) == STATUS_DELAYED` over the same order list.
    """
    rows = []

    for lines in orders:
        if order_status(lines) != STATUS_DELAYED:
            continue

        days = order_days_late(lines)
        head = lines[0]
        late_items = [l.item_name for l in lines
                      if line_days_late(l) is not None and l.item_name]
        detail = ", ".join(late_items[:2])
        if len(late_items) > 2:
            detail += f" +{len(late_items) - 2} more"

        rows.append({
            "id": head.id,
            "reference": head.po_number or head.ref_no or f"row-{head.id}",
            "detail": detail or None,
            "meta": " · ".join(p for p in (head.supplier, head.branch) if p) or None,
            # "avg" is stated because an order's lateness is the average across
            # its late lines, not its worst one.
            "badge": f"{_days(days)} days late (avg)" if days is not None else None,
            "sort": days or 0,
        })

    rows.sort(key=lambda r: r["sort"], reverse=True)
    for row in rows:
        row.pop("sort")

    return paginate(search_filter(rows, search), page, page_size)


def delayed_line_references(orders, page=None, page_size=None, search=None):
    """The late LINES inside the delayed orders — the level below the tile."""
    rows = []

    for lines in orders:
        for line in lines:
            days = line_days_late(line)
            if days is None:
                continue
            rows.append({
                "id": line.id,
                "reference": line.po_number or line.ref_no or f"row-{line.id}",
                "detail": line.item_name,
                "meta": " · ".join(
                    part for part in (line.supplier, line.branch) if part
                ) or None,
                "badge": f"{days} days late",
                "sort": days,
            })

    rows.sort(key=lambda r: r["sort"], reverse=True)
    for row in rows:
        row.pop("sort")

    return paginate(search_filter(rows, search), page, page_size)


def procurement_kpis(rows):
    """Total value + how late purchasing runs.

    Deliberately NOT here any more, by request:
      * total_quantity        — summed across incomparable units (kg, pcs,
                                litres), so the number never meant anything
      * avg_days_vs_required  — a second delay average sitting next to the
                                first, which invited "which one is the delay?"
      * delayed_lines         — the same fact as the Delayed status tile
    `basis` stays: it is the denominator behind avg_delay_days, not a KPI.

    Counted over ORDERS. An order's lateness is its LAST line to arrive, since
    the order is not complete until all of it lands.
    """
    orders = group_orders(rows)
    value = total_value(rows)
    late_days = []
    comparable = 0

    for lines in orders:
        if any(l.purchase is not None and l.required_d is not None for l in lines):
            comparable += 1
            days = order_days_late(lines)
            if days is not None:
                late_days.append(days)

    return {
        "total_value": value,
        # Positive = purchased AFTER the date it was required, which is how a
        # figure labelled "delay" is read. Averaged over the late ORDERS only,
        # and each order's own figure is the average of its late lines — so a
        # single very late line no longer speaks for a whole order. The per-line
        # breakdown is on the tile.
        "avg_delay_days": round(sum(late_days) / len(late_days), 1) if late_days else None,
        "basis": comparable,
    }
