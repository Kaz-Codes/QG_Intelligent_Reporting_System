from decimal import Decimal

#-----------------------------------------------------
# INVENTORY (STOCKS) DASHBOARD CALCULATIONS
#
# Built on the flat Stock table — one row per (item, branch) stock position.
# Inventory is a snapshot, not a time series; every figure here is derived
# from the current stock rows (plus issuance history for the runway).
#
# Status is derived from the available quantity against the reorder level:
#   * available <= 0            -> Out of Stock
#   * available < reorder_level -> Below Reorder
#   * otherwise                 -> OK
# reorder_status is the same threshold split two ways (Reorder Needed / Adequate).
# Both need reorder_level; where it is missing a row can only be Out of Stock
# or OK.
#-----------------------------------------------------

OUT_OF_STOCK = "Out of Stock"
BELOW_REORDER = "Below Reorder"
OK = "OK"
STOCK_STATUSES = [OUT_OF_STOCK, BELOW_REORDER, OK]

REORDER_NEEDED = "Reorder Needed"
ADEQUATE = "Adequate"
REORDER_STATUSES = [REORDER_NEEDED, ADEQUATE]

RISK_STATUSES = (OUT_OF_STOCK, BELOW_REORDER)


def _num(value):
    return value if value is not None else Decimal("0")


def derive_stock_status(available_qty, reorder_level):
    available = _num(available_qty)
    if available <= 0:
        return OUT_OF_STOCK
    if reorder_level is not None and available < reorder_level:
        return BELOW_REORDER
    return OK


def derive_reorder_status(available_qty, reorder_level):
    available = _num(available_qty)
    if reorder_level is not None and available < reorder_level:
        return REORDER_NEEDED
    return ADEQUATE


def days_of_stock(available_qty, avg_daily_issue):
    # Runway = how many days the available stock lasts at the average daily
    # consumption rate. None when:
    #   * there is no issuance history to estimate a consumption rate from, or
    #   * the item is already out of stock (available <= 0) — "days remaining" is
    #     meaningless once you have run out, and those items would otherwise fill
    #     the whole "lowest days of stock" chart with zeros and hide the items
    #     that still have stock but little runway (they are the Out-of-Stock KPI).
    #
    # Rounded to one decimal, NOT floored with int(): an item that lasts half a
    # day (available 3, using 5.5/day) is the most urgent of all, and int() would
    # truncate it to 0 — throwing away exactly the signal this figure exists for.
    if (avg_daily_issue and avg_daily_issue > 0
            and available_qty is not None and available_qty > 0):
        return round(float(available_qty / avg_daily_issue), 1)
    return None


#-------------------------------------
# HEADLINE NUMBERS (KPIS)
#
# All aggregates below operate on the serialized row dicts, so the derived
# status / runway are computed exactly once (in the serializer).
#-------------------------------------

def kpis(rows):
    available_units = sum((_num(r["available_qty"]) for r in rows), Decimal("0"))
    total_stock = sum((_num(r["stock_qty"]) for r in rows), Decimal("0"))
    on_hold = sum((_num(r["hold_qty"]) for r in rows), Decimal("0"))

    out_of_stock = sum(1 for r in rows if r["stock_status"] == OUT_OF_STOCK)
    below_reorder = sum(1 for r in rows if r["stock_status"] == BELOW_REORDER)

    # "Items Shown" counts only items that actually have stock available — an
    # item with 0 available is not something you have, it is an Out-of-Stock
    # line. The out-of-stock rows still feed the risk figures below (that is what
    # the % At Risk is about), so at_risk_pct keeps the FULL row count as its
    # denominator, not the available-only count.
    total_items = len(rows)
    items_shown = sum(1 for r in rows if _num(r["available_qty"]) > 0)
    at_risk_pct = round(((out_of_stock + below_reorder) / total_items) * 100) if total_items else 0

    total_stock_value = sum((_num(r["stock_qty_amount"]) for r in rows), Decimal("0"))
    available_value = sum((_num(r["available_amount"]) for r in rows), Decimal("0"))

    return {
        "available_units": available_units,
        "total_stock_qty": total_stock,
        "on_hold": on_hold,
        "items_shown": items_shown,
        "out_of_stock": out_of_stock,
        "below_reorder": below_reorder,
        "at_risk_pct": at_risk_pct,
        "total_stock_value": total_stock_value,
        "available_value": available_value,
    }


#-------------------------------------
# CHARTS
#-------------------------------------

def items_by_branch(rows):
    counts = {}
    for row in rows:
        branch = row["branch"]
        if not branch:
            continue
        counts[branch] = counts.get(branch, 0) + 1

    result = [{"branch": branch, "items": count} for branch, count in counts.items()]
    result.sort(key=lambda r: r["items"], reverse=True)
    return result


def at_risk_by_branch(rows):
    totals = {}
    for row in rows:
        branch = row["branch"]
        if not branch:
            continue
        entry = totals.setdefault(branch, {"total": 0, "risk": 0})
        entry["total"] += 1
        if row["stock_status"] in RISK_STATUSES:
            entry["risk"] += 1

    result = [
        {"branch": branch, "at_risk": round((entry["risk"] / entry["total"]) * 100)}
        for branch, entry in totals.items()
        if entry["total"]
    ]
    result.sort(key=lambda r: r["at_risk"], reverse=True)
    return result


def top_items(rows, limit=8):
    totals = {}
    for row in rows:
        item = row["item"]
        if not item:
            continue
        totals[item] = totals.get(item, Decimal("0")) + _num(row["stock_qty"])

    result = [{"item": item, "stock_qty": qty} for item, qty in totals.items()]
    result.sort(key=lambda r: r["stock_qty"], reverse=True)
    return result[:limit]


def lowest_days_of_stock(rows, limit=8):
    with_runway = [row for row in rows if row["days_of_stock"] is not None and row["days_of_stock"] > 0]
    with_runway.sort(key=lambda r: r["days_of_stock"])
    return [
        {"item": f'{row["item"]} ({row["branch"]})', "days_of_stock": row["days_of_stock"]}
        for row in with_runway[:limit]
    ]


def stock_health_split(rows):
    counts = {}
    for row in rows:
        counts[row["stock_status"]] = counts.get(row["stock_status"], 0) + 1

    return [
        {"label": status, "value": counts[status]}
        for status in [OK, BELOW_REORDER, OUT_OF_STOCK]
        if counts.get(status)
    ]
