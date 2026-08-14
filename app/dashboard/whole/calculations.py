from datetime import date
from decimal import Decimal

from app.dashboard.stock_runway import (
    days_of_stock as value_days_of_stock, BASIS as RUNWAY_BASIS,
)

#-----------------------------------------------------
# OVERVIEW DASHBOARD CALCULATIONS
#
# The overview spans every module, so unlike the per-module dashboards it never
# materializes rows — helpers.py returns aggregates straight out of SQL and the
# functions here only shape them (percentages, splits, ordering).
#
# Two conventions run through the whole module:
#
#   * Every ratio is returned alongside the row count it was computed over
#     (`*_basis`). Several of these figures rest on a small slice of the book —
#     import delay has both dates on ~20% of consignments — so a bare percentage
#     would read as a fact about the whole table. The front end is expected to
#     show the basis next to the number.
#
#   * A period figure is NEVER silently zero. Where the window holds no rows the
#     payload says so (`rows` = 0), because the loaded data currently ends before
#     the current month and an unqualified "Rs 0" reads as a broken tile rather
#     than an empty window.
#-----------------------------------------------------

ZERO = Decimal("0")


def _num(value):
    return value if value is not None else ZERO


def pct(part, whole, digits=1):
    # Percentage of `part` in `whole`, or None when there is nothing to divide
    # by. None (not 0) because "no rows to measure" and "measured, and it is 0%"
    # are different statements and the tile renders them differently.
    if not whole:
        return None
    return round((part / whole) * 100, digits)


#-------------------------------------
# THE REPORTING WINDOW
#
# Every "month to date" figure resolves through here. Callers may pass an
# explicit range; with neither bound given the window is the 1st of the current
# month to today.
#-------------------------------------

def resolve_period(date_from, date_to, today=None):
    today = today or date.today()

    if date_from is None and date_to is None:
        return today.replace(day=1), today, "month_to_date"

    return (
        date_from or date.min,
        date_to or today,
        "custom",
    )


#-------------------------------------
# IMPORTS
#-------------------------------------

def imports_period_value(total, rows, undated_rows=0, undated_value=None,
                         lines=None, date_field=None):
    """Value of the WHOLE consignments dated inside the window.

    Dated and valued exactly as the Imports module's own "Total Value" hero
    and trend chart are (header field, full consignment value) — see
    helpers.imports_period_value for why this is no longer per-line.
    `consignments` is every consignment whose header date falls in the
    window; `lines` is every item line belonging to one of them (not only the
    ones individually dated inside it) — the reference list shows exactly
    those lines, so the two reconcile.

    `undated` is the money no window can reach: consignments carrying a value
    but no date at all. Reported beside the period figure so the gap is visible
    instead of being quietly dropped from every period at once.
    """
    return {
        "value": _num(total),
        "consignments": rows,
        "lines": lines,
        "basis": "consignment required date" if date_field == "required_date"
                 else "consignment ETA at works",
        "undated": {
            "consignments": undated_rows,
            "value": _num(undated_value),
        },
    }


def imports_in_process(stage_counts):
    # Everything not in a terminal state, split across the six-stage pipeline
    # the imports list already uses, so the overview and the module agree.
    total = sum(stage_counts.values())
    return {
        # `count` — the same key Arrived, Cancelled and Delayed use, because
        # they are the same kind of figure and the front end renders them with
        # one component. `total` is kept as its alias for the stage chart's own
        # denominator.
        "count": total,
        "total": total,
        "by_stage": [
            {"stage": stage, "consignments": count}
            for stage, count in stage_counts.items()
        ],
    }


def imports_shafts(in_process, arrived):
    total = in_process + arrived
    return {
        "in_process": in_process,
        "arrived": arrived,
        "total": total,
        "arrived_pct": pct(arrived, total),
    }


#-------------------------------------
# LOCAL PROCUREMENT
#-------------------------------------

def procurement_period_value(total, orders, quantity):
    """Value + ORDER count (distinct POs), never item lines."""
    return {
        "value": _num(total),
        "orders": orders,
        "quantity": _num(quantity),
        "basis": "purchase_date",
    }


def procurement_category_split(category_totals, top=4):
    # The top N categories by value plus a single "Other" bucket, each carrying
    # its share of the period total. Other is appended (not sorted in) so it
    # always reads last however large it is.
    total = sum(category_totals.values(), ZERO)

    ordered = sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)
    leaders, rest = ordered[:top], ordered[top:]

    split = [
        {"category": name, "value": value, "share_pct": pct(value, total)}
        for name, value in leaders
    ]

    if rest:
        other = sum((value for _, value in rest), ZERO)
        split.append({
            "category": "Other",
            "value": other,
            "share_pct": pct(other, total),
            "categories": len(rest),
        })

    return {
        "total": total,
        "split": split,
        "categories_total": len(category_totals),
    }


def procurement_delay(late, comparable):
    return {
        "delay_pct": pct(late, comparable),
        "late_orders": late,
        "basis": comparable,
    }


def procurement_cycle_time(from_store, from_store_rows, from_po, from_po_rows):
    # Two readings of "demand to purchase", because the source has two candidate
    # demand dates and picking one is a business decision, not a technical one:
    #   * ppc_store -> purchase  (demand raised at the store)
    #   * po_date   -> purchase  (order placed on the supplier)
    # Both are returned so the front end can label whichever the business means
    # without the backend baking in a guess.
    return {
        "store_to_purchase_days": from_store,
        "store_to_purchase_basis": from_store_rows,
        "po_to_purchase_days": from_po,
        "po_to_purchase_basis": from_po_rows,
    }


#-------------------------------------
# LOGISTICS
#-------------------------------------

# Trucking rows carry Inbound / Outbound or nothing at all. There is no "Local"
# movement type in the data and none can be inferred, so unclassified jobs get
# their own bucket instead of being folded into a category they may not belong
# to. Those rows also carry no freight, so they move the count and not the cost.
UNCLASSIFIED = "Unclassified"


def logistics_trucking_cost(rows):
    buckets = []
    total = ZERO

    for movement_type, jobs, actual, quoted in rows:
        cost = _num(actual)
        total += cost
        buckets.append({
            "movement_type": movement_type or UNCLASSIFIED,
            "jobs": jobs,
            "actual_freight": cost,
            "quoted_freight": _num(quoted),
        })

    buckets.sort(key=lambda b: b["actual_freight"], reverse=True)

    for bucket in buckets:
        bucket["share_pct"] = pct(bucket["actual_freight"], total)

    return {"total": total, "by_movement": buckets}


def logistics_shipments_handled(counts):
    """Shipments in the window, with how many could be dated at all.

    The coverage figures are the point: only 13.8% of logistics orders carry an
    ETD, so a windowed export count is small for a reason that has nothing to do
    with activity. Reporting the datable total lets the screen say "197 of 1,424
    orders carry an ETD" instead of showing a number that looks like collapse.
    """
    export = counts["export"]
    imports = counts["import"]

    return {
        "export_shipments": export,
        "import_shipments": imports,
        "total": export + imports,
        "coverage": {
            "export_datable": counts["export_datable"],
            "export_total": counts["export_total"],
            "import_datable": counts["import_datable"],
            "import_total": counts["import_total"],
        },
    }


#-------------------------------------
# STORES
#-------------------------------------

def stores_stock_value(total_value, available_value, items):
    return {
        "stock_value": _num(total_value),
        "available_value": _num(available_value),
        "items": items,
    }


def stores_value_by_store(rows):
    total = sum((_num(value) for _, value, _ in rows), ZERO)

    stores = [
        {
            "branch": branch,
            "stock_value": _num(value),
            "items": items,
            "share_pct": pct(_num(value), total),
        }
        for branch, value, items in rows
    ]
    stores.sort(key=lambda s: s["stock_value"], reverse=True)
    return stores


# Runway is defined once, in app/dashboard/stock_runway, and the Inventory
# dashboard reads the same function — the two screens cannot disagree about the
# same warehouse any more.
def stock_days(available_value, consumed_value, window_days):
    return value_days_of_stock(available_value, consumed_value, window_days)


def stores_stock_days(stock_by_branch, consumption_by_branch, window_days):

    per_branch = []
    total_value = ZERO
    total_consumed = ZERO

    for branch, value, _lines in stock_by_branch:
        value = _num(value)
        consumed = _num(consumption_by_branch.get(branch))

        total_value += value
        total_consumed += consumed

        per_branch.append({
            "branch": branch,
            "stock_value": value,
            "consumed_value": consumed,
            "days_of_stock": stock_days(value, consumed, window_days),
        })

    per_branch.sort(
        # Branches with no consumption history have no runway; they sort last
        # rather than reading as the healthiest store on the list.
        key=lambda b: (b["days_of_stock"] is None, b["days_of_stock"])
    )

    return {
        "by_branch": per_branch,
        "total_days_of_stock": stock_days(total_value, total_consumed, window_days),
        "window_days": window_days,
        # The same sentence the Inventory dashboard prints, from the same source.
        "basis": RUNWAY_BASIS,
    }


def stores_dead_stock(items, value, threshold_days, total_items, total_value,
                      history_days=0):
    # Stock that still has value but has not been issued within the threshold.
    # The threshold is a caller parameter, not a constant here: "dead" is a
    # business judgement and the number belongs in the request, not the code.
    #
    # `exceeds_history` warns that the threshold reaches further back than the
    # issuance data goes, at which point the figure is really "never issued in
    # the data we hold" and raising the threshold cannot change it.
    return {
        "items": items,
        "value": _num(value),
        "threshold_days": threshold_days,
        "items_pct": pct(items, total_items),
        "value_pct": pct(_num(value), _num(total_value)),
        "history_days": history_days,
        "exceeds_history": bool(history_days) and threshold_days >= history_days,
    }


def share(part, whole, digits=1):
    """One figure's percentage of another, or None when there is no whole.

    Used wherever a tile reports "x% of the book" beside its own value, so the
    In Process / Arrived / Cancelled tiles all state their share the same way.
    """
    if not whole:
        return None
    return round(float(part) / float(whole) * 100, digits)
