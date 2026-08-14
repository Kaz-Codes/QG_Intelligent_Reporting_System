from app.dashboard.purchases.calculations import (
    kpis, value_trend, status_split, value_by_branch, value_by_supplier,
    overdue_buckets, derive_status, days_overdue, procurement_kpis,
    group_orders, delayed_line_references, delayed_references,
    order_references, orders_with_status,
    supplier_orders, STATUS_COMPLETED,
)


#-------------------------------------
# ONE PURCHASE ROW (for the table)
#
# Shaped to match the frontend PurchaseRow. Status and days_overdue are
# derived here. `items` is the single Item master (the relationship is a
# many-to-one despite its plural name), used only for the category.
#-------------------------------------

def serialize_row(row):
    item = row.item
    return {
        "ref_no": row.ref_no,
        "po_number": row.po_number,
        "bill_no": row.bill_no,
        "item": row.item_name,
        "item_code": row.item_code,
        "supplier": row.supplier,
        "branch": row.branch,
        "category": item.category if item else None,
        "mop": row.mop,
        "sourcing_officer": row.sourcing_o,
        "quantity": row.qty,
        "amount": row.amount,
        "po_date": row.po_date,
        "purchase_date": row.purchase,
        "required_date": row.required_d,
        "ppc_store": row.ppc_store,
        "status": derive_status(row.purchase, row.required_d),
        "days_overdue": days_overdue(row.purchase, row.required_d),
    }


def serialize_rows(rows):
    return [serialize_row(row) for row in rows]


#-------------------------------------
# THE AGGREGATES
#-------------------------------------

def serialize_purchases_dashboard(rows, period_from, period_to, date_field=None):
    """Every count on this screen is an ORDER, not an item line.

    The rows are grouped ONCE here and the grouping passed down, so each figure
    is derived from the same set of orders and no two can disagree about how
    many there are.
    """
    orders = group_orders(rows)
    kpi_values = kpis(rows, orders)

    return {
        "kpis": kpi_values,
        # total_value and on_time_pct are already in `kpis`; this adds the
        # delay figures.
        "procurement_kpis": procurement_kpis(rows),
        "status_split": status_split(orders),
        "value_by_supplier": value_by_supplier(orders),
        "value_by_branch": value_by_branch(orders),
        "overdue_buckets": overdue_buckets(orders),
        # What is behind each headline, so no figure is a dead end.
        # Delay tiles drill to LINES (an order is late because a line was);
        # everything else drills to the ORDERS it counts.
        "delayed_line_references": delayed_line_references(orders),
        "references": {
            "orders": order_references(orders),
            # ORDER-level, so its total is `kpis.delayed_orders` exactly. The
            # line-level breakdown is `delayed_line_references` above.
            "delayed": delayed_references(orders),
            "on_time": order_references(orders_with_status(orders, STATUS_COMPLETED)),
            "top_supplier": order_references(
                supplier_orders(orders, kpi_values["top_supplier"])
            ),
        },
        # Bucketed to fit the window — 3-day steps inside a month, not one bar.
        "value_trend": value_trend(orders, period_from, period_to, date_field=date_field),
    }
