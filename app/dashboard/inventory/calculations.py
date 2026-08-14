from decimal import Decimal

from app.dashboard.references import paginate, search_filter

from app.dashboard.stock_runway import (
    days_of_stock as value_days_of_stock, BASIS as RUNWAY_BASIS,
)
from app.dashboard.inventory.helpers import PURCHASES_BRANCH_TO_STOCK_BRANCH

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

#-----------------------------------------------------
# ITEMS, NOT STOCK LINES
#
# The stock table holds one row per (item, BRANCH) — the same bolt stocked at
# four factories is four rows. Counting those rows answered "how many stock
# records do we keep", which nobody asked; the question is how many ITEMS the
# business holds, and how many of those are dead.
#
# So rows are folded together on item_code before anything is counted. Value and
# quantity add up across branches, and movement is judged on the item's TOTAL
# issuance — an item still moving at one factory is not dead just because it sat
# still at another.
#
# Branch breakdowns keep using the per-branch rows: those are legitimate
# aggregates, not line-level KPIs.
#
# A row with no item_code cannot be folded and stands alone, keyed on its
# identity so two unrelated ones never merge.
#-----------------------------------------------------

def group_by_item(rows, purchase_map=None, from_12m=None, item_issuance=None):
    """One row per item, summed across the branches that stock it.

    `purchase_map` ({item_code: most recent purchase date}) and `from_12m`
    (the same 365-day boundary the issuance windows use) are optional so
    existing callers that do not have them yet keep their old behaviour —
    see derive_movement.

    `item_issuance` ({item_code: {"v12", "v3"}}, from
    helpers.issuance_totals_by_item) OVERRIDES the issued_value_12m/3m folded
    from `rows` below when given. The per-row fold only ever sums issuance
    for branches present in the STOCK table — an item issued at a branch with
    no remaining stock row is invisible to it — so the authoritative,
    whole-company total is substituted in once it's available.
    """
    items = {}

    for row in rows:
        key = row["item_code"] or f'~{row["item"]}|{row["branch"]}'
        entry = items.get(key)

        if entry is None:
            items[key] = {
                "item_code": row["item_code"],
                "item": row["item"],
                "item_category": row["item_category"],
                "branches": {row["branch"]} if row["branch"] else set(),
                "stock_qty_amount": _num(row["stock_qty_amount"]),
                "available_amount": _num(row["available_amount"]),
                "available_qty": _num(row["available_qty"]),
                "stock_qty": _num(row["stock_qty"]),
                "reorder_level": row["reorder_level"],
                "issued_value_12m": _num(row["issued_value_12m"]),
                "issued_value_3m": _num(row["issued_value_3m"]),
            }
            continue

        if row["branch"]:
            entry["branches"].add(row["branch"])
        for field in ("stock_qty_amount", "available_amount",
                      "available_qty", "stock_qty",
                      "issued_value_12m", "issued_value_3m"):
            entry[field] += _num(row[field])

        # Reorder levels add up too: the item needs cover at every branch that
        # stocks it, so the business-wide threshold is their sum.
        if row["reorder_level"] is not None:
            entry["reorder_level"] = (entry["reorder_level"] or Decimal("0")) + row["reorder_level"]

    for entry in items.values():
        entry["branch_count"] = len(entry["branches"])
        entry["branches"] = sorted(entry["branches"])
        entry["stock_status"] = derive_stock_status(
            entry["available_qty"], entry["reorder_level"]
        )

        if item_issuance is not None:
            totals = item_issuance.get(entry["item_code"])
            if totals is not None:
                entry["issued_value_12m"] = totals["v12"]
                entry["issued_value_3m"] = totals["v3"]

        # purchase_map is keyed (item_code, branch) — checked against every
        # branch purchases_data can be matched to at all (not just the ones
        # THIS stock snapshot happens to list for the item): the same "an item
        # still moving at one factory is not dead because it sat still at
        # another" reasoning applies to a recent purchase, and restricting
        # this to entry["branches"] undercounted it the same way the
        # issued_value fold above once did — a purchase can arrive before the
        # next stock snapshot reflects it there.
        last_purchases = [
            (purchase_map or {}).get((entry["item_code"], b))
            for b in PURCHASES_BRANCH_TO_STOCK_BRANCH.values()
        ]
        recently_purchased = (
            from_12m is not None
            and any(lp is not None and lp >= from_12m for lp in last_purchases)
        )

        entry["movement"] = derive_movement(
            entry["issued_value_3m"], entry["issued_value_12m"],
            entry["available_qty"], recently_purchased,
        )

    return list(items.values())


#-------------------------------------
# WHAT IS BEHIND AN INVENTORY FIGURE
#
# Every headline here counts ITEMS, folded across the branches that stock them.
# "2,387 dead items" is not actionable on its own — which items, worth what, and
# at which stores, is. So each tile can open the items it counted.
#
# `badge` carries the figure that put the item in the list, so a dead-stock list
# shows value while an issuance list shows what was issued.
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


def item_references(items, badge_key="stock_qty_amount", page=None, page_size=None, search=None):
    """The items behind a figure, biggest first."""
    rows = []

    for item in items:
        branches = item.get("branches") or []
        rows.append({
            "id": item["item_code"] or item["item"],
            "reference": item["item_code"] or "(no code)",
            "detail": item["item"],
            "meta": " · ".join(p for p in (
                item.get("item_category"),
                f"{len(branches)} store{'' if len(branches) == 1 else 's'}"
                if branches else None,
            ) if p) or None,
            "badge": _money(item.get(badge_key)),
            "sort": float(_num(item.get(badge_key))),
        })

    rows.sort(key=lambda r: r["sort"], reverse=True)
    for row in rows:
        row.pop("sort")

    return paginate(search_filter(rows, search), page, page_size)


def items_where(items, predicate):
    return [i for i in items if predicate(i)]


def movement_references(items):
    """One list per movement class, so the fast/slow/dead chart drills down.

    The chart states how many items and how much value sit in each class; these
    say WHICH items, which is the only form in which the number is actionable —
    "2,387 dead items" cannot be worked on, a list of them can.
    """
    return {
        movement: item_references(
            items_where(items, lambda i, m=movement: i["movement"] == m)
        )
        for movement in MOVEMENT_CLASSES
    }


def kpis(rows):
    """The headline stock figures, counted over ITEMS.

    Deliberately NOT here any more, by request:
      * available_units / total_stock_qty — quantities summed across
        incomparable units (kg + pcs + litres), so the totals were arithmetic
        without a meaning. Value is the comparable measure and is kept.
      * on_hold — replaced by dead stock, which is the question people were
        actually asking of it.
      * at_risk_pct — superseded by the movement split (fast / slow / dead),
        which says the same thing with a reason attached.

    Takes an already-grouped list (see group_by_item), so every count is a
    distinct ITEM rather than an item-at-a-branch record.
    """
    out_of_stock = sum(1 for r in rows if r["stock_status"] == OUT_OF_STOCK)
    below_reorder = sum(1 for r in rows if r["stock_status"] == BELOW_REORDER)

    # Items that actually have stock available — an item with 0 available is not
    # something you have, it is an Out-of-Stock item.
    items_shown = sum(1 for r in rows if _num(r["available_qty"]) > 0)

    total_stock_value = sum((_num(r["stock_qty_amount"]) for r in rows), Decimal("0"))
    available_value = sum((_num(r["available_amount"]) for r in rows), Decimal("0"))

    return {
        "items_total": len(rows),
        "items_shown": items_shown,
        "out_of_stock": out_of_stock,
        "below_reorder": below_reorder,
        "total_stock_value": total_stock_value,
        "available_value": available_value,
    }


#-------------------------------------
# MOVEMENT: FAST / SLOW / DEAD
#
# Replaces the "at risk" split. Risk was derived from the reorder level alone,
# which said an item was in trouble without saying whether anybody actually
# wants it. Movement answers that directly, from real issuance:
#
#   Dead  — nothing issued in the last 12 months, stock actually AVAILABLE, AND
#           more than 12 months since it was last PURCHASED. Stock that is not
#           moving at all, which is the money worth arguing about — an item
#           with nothing available (fully on hold, or simply depleted) has
#           nothing sitting idle, and an item bought recently has not been
#           issued yet for the obvious reason that nobody has had the chance —
#           neither is the same thing as stock nobody wants. Both are left
#           unclassified (movement=None) rather than counted as Dead. It shows
#           up in none of the three classes.
#             * Checked against `available_qty`, the same "do we actually have
#               it" field kpis() uses for out-of-stock, not the raw
#               `stock_qty` (which counts held/reserved units too).
#             * The purchase-recency check uses the SAME 365-day boundary as
#               the issuance windows below (see helpers.latest_purchase_map).
#   Slow  — issued in the last 12 months but NOT in the last 3.
#   Fast  — issued within the last 3 months.
#
# The windows are the ones asked for, and both are reported per line so the two
# issuance KPIs and this split can never disagree — they are the same numbers.
#-------------------------------------

MOVE_FAST = "Fast moving"
MOVE_SLOW = "Slow moving"
MOVE_DEAD = "Dead"
MOVEMENT_CLASSES = [MOVE_FAST, MOVE_SLOW, MOVE_DEAD]


def derive_movement(issued_3m, issued_12m, available_qty=None, recently_purchased=False):
    if issued_3m and issued_3m > 0:
        return MOVE_FAST
    if issued_12m and issued_12m > 0:
        return MOVE_SLOW

    # Dead stock is stock sitting unused — an item with nothing AVAILABLE has
    # no stock to be dead, whether that is because it is fully depleted or
    # fully on hold. Left unclassified (None) rather than folded into Dead, so
    # the dead count and value only ever describe money actually sitting on a
    # shelf. `available_qty` is optional so existing callers that do not have
    # it yet keep their old behaviour.
    if available_qty is not None and available_qty <= 0:
        return None

    # Same reasoning, for stock that simply has not had TIME to move yet — an
    # item purchased within the last 12 months gets the same benefit of the
    # doubt as one with a legitimate reason to be sitting still.
    if recently_purchased:
        return None

    return MOVE_DEAD


def movement_split(rows):
    """Item counts AND value per movement class — both, because they disagree.

    A count alone would rank a thousand dead washers above one dead machine;
    value alone hides how much of the catalogue is standing still. Dead stock is
    currently about half the items but a seventh of the money, and neither
    number tells that story on its own.
    """
    stats = {c: {"items": 0, "value": Decimal("0")} for c in MOVEMENT_CLASSES}

    for row in rows:
        # Unclassified (see derive_movement) — a never-issued item with nothing
        # AVAILABLE is neither fast, slow nor dead, so it sits in none of the
        # three.
        if row["movement"] is None:
            continue
        entry = stats[row["movement"]]
        entry["items"] += 1
        entry["value"] += _num(row["stock_qty_amount"])

    total_value = sum((e["value"] for e in stats.values()), Decimal("0"))
    total_items = sum(e["items"] for e in stats.values())

    return [
        {
            "movement": name,
            "items": stats[name]["items"],
            "count": stats[name]["items"],
            "value": stats[name]["value"],
            "items_pct": round(stats[name]["items"] / total_items * 100, 1) if total_items else None,
            "value_pct": round(float(stats[name]["value"] / total_value * 100), 1) if total_value else None,
        }
        for name in MOVEMENT_CLASSES
    ]


def movement_kpis(rows, window_12m, window_3m):
    """The issuance + dead-stock tiles, all from the same per-item numbers."""
    issued_12m = sum((_num(r["issued_value_12m"]) for r in rows), Decimal("0"))
    issued_3m = sum((_num(r["issued_value_3m"]) for r in rows), Decimal("0"))

    dead = [r for r in rows if r["movement"] == MOVE_DEAD]
    dead_value = sum((_num(r["stock_qty_amount"]) for r in dead), Decimal("0"))
    total_value = sum((_num(r["stock_qty_amount"]) for r in rows), Decimal("0"))

    return {
        "issued_value_12m": issued_12m,
        "issued_value_3m": issued_3m,
        "dead_items": len(dead),
        "dead_value": dead_value,
        "dead_value_pct": round(float(dead_value / total_value * 100), 1) if total_value else None,
        # Named windows, so "last 12 months" is never assumed to end today when
        # the issuance data stops earlier.
        "window_12m": window_12m,
        "window_3m": window_3m,
    }


#-------------------------------------
# CHARTS
#-------------------------------------

def items_by_branch(rows):
    """Items stocked per branch, with their value for the tooltip.

    Per-branch rows on purpose — one row per (item, branch) means counting them
    within a branch IS counting that branch's items.
    """
    counts = {}
    values = {}
    for row in rows:
        branch = row["branch"]
        if not branch:
            continue
        counts[branch] = counts.get(branch, 0) + 1
        values[branch] = values.get(branch, Decimal("0")) + _num(row["stock_qty_amount"])

    result = [
        {"branch": branch, "label": branch, "items": count,
         "count": count, "value": values[branch]}
        for branch, count in counts.items()
    ]
    result.sort(key=lambda r: r["value"], reverse=True)
    return result


def movement_by_branch(rows):
    """Fast / slow / dead per branch — replaces the at-risk-by-branch chart.

    Takes the PER-BRANCH rows, because a branch breakdown needs the branch. An
    item stocked at three factories is counted at each of them, which is the
    only sensible reading of "how much dead stock does this store hold".
    """
    totals = {}

    for row in rows:
        branch = row["branch"]
        if not branch:
            continue
        # Unclassified (see derive_movement) — a zero-stock, never-issued item
        # is neither fast, slow nor dead.
        if row["movement"] is None:
            continue
        entry = totals.setdefault(
            branch, {c: 0 for c in MOVEMENT_CLASSES} | {"dead_value": Decimal("0")}
        )
        entry[row["movement"]] += 1
        if row["movement"] == MOVE_DEAD:
            entry["dead_value"] += _num(row["stock_qty_amount"])

    result = []
    for branch, entry in totals.items():
        lines = sum(entry[c] for c in MOVEMENT_CLASSES)
        result.append({
            "branch": branch,
            "label": branch,
            "fast": entry[MOVE_FAST],
            "slow": entry[MOVE_SLOW],
            "dead": entry[MOVE_DEAD],
            # `count`/`value` so the chart plots DEAD LINES on the axis and
            # shows the money on hover, like every other breakdown.
            "count": entry[MOVE_DEAD],
            "value": entry["dead_value"],
            "dead_value": entry["dead_value"],
            "dead_pct": round(entry[MOVE_DEAD] / lines * 100, 1) if lines else None,
        })

    result.sort(key=lambda r: r["value"], reverse=True)
    return result


#-------------------------------------
# STOCK DAYS (the runway), per branch and overall
#
# How long the stock on hand lasts at the rate it is actually being consumed.
# Measured in RUPEES, not units: a store holds many units of incomparable
# things, so summing bolts and shafts is meaningless while summing their value
# is not.
#
# The consumption rate comes from the 12-month issuance window, which is the
# same number the issuance KPI shows — one source, so the two cannot drift.
#-------------------------------------

# Days of stock is defined once, in app/dashboard/stock_runway — the Overview's
# Stores section reads the same function, so the two screens cannot report
# different runways for the same warehouse (they used to: 81 days against 54).
stock_days_from_value = value_days_of_stock


def stock_days(rows, window_days):
    """Overall runway + the per-branch split, from one set of numbers."""
    by_branch = {}

    for row in rows:
        branch = row["branch"] or "(no branch)"
        entry = by_branch.setdefault(branch, {"stock": Decimal("0"), "issued": Decimal("0")})
        entry["stock"] += _num(row["stock_qty_amount"])
        entry["issued"] += _num(row["issued_value_12m"])

    branches = [
        {
            "branch": branch,
            "stock_value": entry["stock"],
            "issued_value": entry["issued"],
            "days_of_stock": stock_days_from_value(entry["stock"], entry["issued"], window_days),
        }
        for branch, entry in by_branch.items()
    ]

    # A branch with no consumption has no runway; it sorts LAST rather than
    # reading as the healthiest store on the list.
    branches.sort(key=lambda b: (b["days_of_stock"] is None, b["days_of_stock"]))

    total_stock = sum((b["stock_value"] for b in branches), Decimal("0"))
    total_issued = sum((b["issued_value"] for b in branches), Decimal("0"))

    return {
        "total_days_of_stock": stock_days_from_value(total_stock, total_issued, window_days),
        "by_branch": branches,
        "window_days": window_days,
        "basis": RUNWAY_BASIS,
    }


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
    values = {}
    for row in rows:
        status = row["stock_status"]
        counts[status] = counts.get(status, 0) + 1
        values[status] = values.get(status, Decimal("0")) + _num(row["stock_qty_amount"])

    return [
        {"label": status, "count": counts[status], "value": values[status]}
        for status in [OK, BELOW_REORDER, OUT_OF_STOCK]
        if counts.get(status)
    ]
