from app.dashboard.inventory.calculations import (
    kpis, items_by_branch, lowest_days_of_stock,
    stock_health_split, derive_stock_status, derive_reorder_status, days_of_stock,
    derive_movement, movement_kpis, movement_split, movement_by_branch, stock_days,
    group_by_item, item_references, items_where, movement_references,
    MOVE_FAST, MOVE_DEAD, OUT_OF_STOCK, BELOW_REORDER,
)


#-------------------------------------
# ONE STOCK ROW (for the table)
#
# Shaped to match the frontend StockRow. Status, reorder status and runway are
# derived here. `item` is the single Item master, used for category and specs.
# `consumption` is the {(item_code, branch): avg daily issued} map.
#-------------------------------------

def serialize_row(stock, consumption, reorder_levels, issuance=None,
                  purchase_map=None, from_12m=None):
    item = stock.item
    key = (stock.item_code, stock.branch)
    avg_daily = consumption.get(key)
    issued = (issuance or {}).get(key) or {"v12": None, "v3": None}

    # Reorder level derived from requisitions drives every row; the stored
    # column is only a fallback for items with no requisition demand.
    reorder_level = reorder_levels.get(key)
    if reorder_level is None:
        reorder_level = stock.reorder_level

    # See derive_movement / helpers.latest_purchase_map: an item bought within
    # the last 12 months has not necessarily had the chance to be issued yet,
    # so it is not held to the same "nothing moved" standard as older stock.
    # Same (item_code, branch) key as consumption/reorder_level above —
    # purchase_map only ever holds entries for branches purchases_data's own
    # codes could be confidently matched to stock/issuance's branch names.
    last_purchase = (purchase_map or {}).get(key)
    recently_purchased = (
        from_12m is not None
        and last_purchase is not None
        and last_purchase >= from_12m
    )

    return {
        "item_code": stock.item_code,
        "item": stock.item_name,
        "branch": stock.branch,
        "item_category": item.category if item else None,
        "specs": item.default_specification if item else None,
        "available_qty": stock.available_qty,
        "stock_qty": stock.stock_qty,
        "hold_qty": stock.hold_qty,
        "reorder_level": reorder_level,
        "stock_qty_amount": stock.stock_qty_amount,
        "available_amount": stock.available_amount,
        "stock_status": derive_stock_status(stock.available_qty, reorder_level),
        "reorder_status": derive_reorder_status(stock.available_qty, reorder_level),
        "days_of_stock": days_of_stock(stock.available_qty, avg_daily),
        # Issued VALUE over the two reporting windows, and the movement class
        # derived from them. Every movement figure on the screen reads these, so
        # the issuance KPIs, the fast/slow/dead split and dead stock cannot
        # disagree — they are literally the same numbers.
        "issued_value_12m": issued["v12"],
        "issued_value_3m": issued["v3"],
        "movement": derive_movement(
            issued["v3"], issued["v12"], stock.available_qty, recently_purchased
        ),
    }


def serialize_rows(stocks, consumption, reorder_levels, issuance=None,
                   purchase_map=None, from_12m=None):
    issuance = issuance or {}
    return [
        serialize_row(stock, consumption, reorder_levels, issuance,
                      purchase_map, from_12m)
        for stock in stocks
    ]


#-------------------------------------
# THE AGGREGATES (computed from the serialized rows)
#-------------------------------------

def serialize_inventory_dashboard(rows, windows, issuance=None,
                                  issuance_references=None, purchase_map=None,
                                  item_issuance=None):
    """One screen, one set of numbers.

    TWO groupings, each used where it belongs:
      * `items` — stock folded onto item_code, summed across the branches that
        hold it. Every KPI and the movement split count these, because the
        question is how many ITEMS the business holds, not how many stock
        records it keeps. An item still moving at one factory is not dead
        because it sat still at another.
      * `rows` — the per-(item, branch) records, used only for the BRANCH
        breakdowns, which need the branch to exist.

    `top_items` is gone: it ranked items by stock QUANTITY, summing kg against
    pcs, and answered the same question as the movement split with a worse
    measure. `lowest_days_of_stock` stays — it is per item, where the runway is
    actionable, while `stock_days` is the branch/overall roll-up.
    """
    items = group_by_item(rows, purchase_map, windows["from_12m"], item_issuance)

    return {
        "kpis": kpis(items),
        # What went out in the chosen window (the current month by default).
        # Replaces the fixed 12m/3m issuance tiles — see helpers.issuance_in_period.
        "issuance": issuance,
        # What is behind each headline. Every tile counts ITEMS, so every list
        # is items — with the figure that put them there as the badge.
        "references": {
            "items": item_references(items),
            "dead": item_references(
                items_where(items, lambda i: i["movement"] == MOVE_DEAD)
            ),
            "fast": item_references(
                items_where(items, lambda i: i["movement"] == MOVE_FAST)
            ),
            "issued_12m": item_references(
                items_where(items, lambda i: i["issued_value_12m"]),
                badge_key="issued_value_12m",
            ),
            "issued_3m": item_references(
                items_where(items, lambda i: i["issued_value_3m"]),
                badge_key="issued_value_3m",
            ),
            "out_of_stock": item_references(
                items_where(items, lambda i: i["stock_status"] == OUT_OF_STOCK)
            ),
            "below_reorder": item_references(
                items_where(items, lambda i: i["stock_status"] == BELOW_REORDER)
            ),
            "issuance": issuance_references,
            # One list per movement class, keyed by the class name the chart
            # shows, so its bars drill straight through.
            "movement": movement_references(items),
        },
        "movement_kpis": movement_kpis(items, windows["days_12m"], windows["days_3m"]),
        "stock_days": stock_days(rows, windows["days_12m"]),
        "stock_health": stock_health_split(items),
        "movement_split": movement_split(items),
        "movement_by_branch": movement_by_branch(rows),
        "items_by_branch": items_by_branch(rows),
        "lowest_days_of_stock": lowest_days_of_stock(rows),
        # The dates the movement windows actually cover, so "last 12 months" is
        # never taken to mean "ending today" when the issuance data stops sooner.
        "issuance_windows": {
            "latest_issuance": windows["latest"],
            "from_12m": windows["from_12m"],
            "from_3m": windows["from_3m"],
        },
    }
