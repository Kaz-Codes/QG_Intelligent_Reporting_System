from app.dashboard.purchases.calculations import (
    kpis, monthly_value_trend, status_split, value_by_branch, value_by_supplier,
    derive_status, days_overdue,
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

def serialize_purchases_dashboard(rows):
    return {
        "kpis": kpis(rows),
        "status_split": status_split(rows),
        "value_by_supplier": value_by_supplier(rows),
        "value_by_branch": value_by_branch(rows),
        "monthly_value_trend": monthly_value_trend(rows),
    }
