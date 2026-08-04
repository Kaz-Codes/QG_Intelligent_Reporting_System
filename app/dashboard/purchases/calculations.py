from decimal import Decimal

#-----------------------------------------------------
# PURCHASES DASHBOARD CALCULATIONS
#
# Built on the flat PurchasesData table — one row per purchase line, with the
# PO-level fields repeated per row. Every figure here is derived from those
# rows; nothing is stored.
#
# Status is derived, not a column:
#   * no purchase date yet          -> Pending
#   * purchased on/before required  -> Completed
#   * required date < purchase date -> Delayed (purchased late)
# days_overdue is how many days late a Delayed row is.
#-----------------------------------------------------

STATUS_PENDING = "Pending"
STATUS_COMPLETED = "Completed"
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

def kpis(rows):
    orders_count = len(rows)
    value = total_value(rows)
    avg_order_value = (value / orders_count) if orders_count else Decimal("0")

    pending = completed = delayed = 0
    supplier_totals = {}

    for row in rows:
        status = derive_status(row.purchase, row.required_d)
        if status == STATUS_PENDING:
            pending += 1
        elif status == STATUS_DELAYED:
            delayed += 1
        else:
            completed += 1

        if row.supplier:
            supplier_totals[row.supplier] = supplier_totals.get(row.supplier, Decimal("0")) + _amount(row)

    top_supplier = None
    top_supplier_amount = Decimal("0")
    if supplier_totals:
        top_supplier, top_supplier_amount = max(supplier_totals.items(), key=lambda kv: kv[1])

    # Of the orders that have actually been purchased, how many were on time.
    purchased = completed + delayed
    on_time_pct = round((completed / purchased) * 100) if purchased else 0

    return {
        "orders_count": orders_count,
        "total_value": value,
        "avg_order_value": avg_order_value,
        "pending_orders": pending,
        "completed_orders": completed,
        "delayed_orders": delayed,
        "on_time_pct": on_time_pct,
        "top_supplier": top_supplier,
        "top_supplier_amount": top_supplier_amount,
    }


#-------------------------------------
# BREAKDOWNS
#-------------------------------------

def value_by(rows, key_fn, limit=None):
    totals = {}

    for row in rows:
        label = key_fn(row)
        if not label:
            continue
        totals[label] = totals.get(label, Decimal("0")) + _amount(row)

    result = [{"label": label, "value": value} for label, value in totals.items()]
    result.sort(key=lambda r: r["value"], reverse=True)

    if limit is not None:
        result = result[:limit]

    return result


def value_by_supplier(rows, limit=8):
    return value_by(rows, lambda r: r.supplier, limit)


def value_by_branch(rows, limit=8):
    return value_by(rows, lambda r: r.branch, limit)


def status_split(rows):
    counts = {}
    for row in rows:
        status = derive_status(row.purchase, row.required_d)
        counts[status] = counts.get(status, 0) + 1

    return [
        {"label": status, "value": counts[status]}
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


def overdue_buckets(rows):
    counts = {tier: 0 for tier in AGING_TIERS}
    for row in rows:
        overdue = days_overdue(row.purchase, row.required_d)
        if overdue is None:
            continue
        counts[_aging_tier(overdue)] += 1

    return [{"bucket": tier, "orders": counts[tier]} for tier in AGING_TIERS]


def monthly_value_trend(rows):
    totals = {}

    for row in rows:
        day = row.purchase or row.po_date
        if day is None:
            continue
        month = day.strftime("%Y-%m")
        totals[month] = totals.get(month, Decimal("0")) + _amount(row)

    return [{"month": month, "value": totals[month]} for month in sorted(totals)]
