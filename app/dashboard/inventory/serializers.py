from app.dashboard.inventory.calculations import (
    kpis, items_by_branch, at_risk_by_branch, top_items, lowest_days_of_stock,
    stock_health_split, derive_stock_status, derive_reorder_status, days_of_stock,
)


#-------------------------------------
# ONE STOCK ROW (for the table)
#
# Shaped to match the frontend StockRow. Status, reorder status and runway are
# derived here. `item` is the single Item master, used for category and specs.
# `consumption` is the {(item_code, branch): avg daily issued} map.
#-------------------------------------

def serialize_row(stock, consumption, reorder_levels):
    item = stock.item
    key = (stock.item_code, stock.branch)
    avg_daily = consumption.get(key)

    # Reorder level derived from requisitions drives every row; the stored
    # column is only a fallback for items with no requisition demand.
    reorder_level = reorder_levels.get(key)
    if reorder_level is None:
        reorder_level = stock.reorder_level

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
    }


def serialize_rows(stocks, consumption, reorder_levels):
    return [serialize_row(stock, consumption, reorder_levels) for stock in stocks]


#-------------------------------------
# THE AGGREGATES (computed from the serialized rows)
#-------------------------------------

def serialize_inventory_dashboard(rows):
    return {
        "kpis": kpis(rows),
        "stock_health": stock_health_split(rows),
        "items_by_branch": items_by_branch(rows),
        "at_risk_by_branch": at_risk_by_branch(rows),
        "top_items": top_items(rows),
        "lowest_days_of_stock": lowest_days_of_stock(rows),
    }
