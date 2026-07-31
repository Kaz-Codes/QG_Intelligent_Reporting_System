from decimal import Decimal

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

def consignment_value_pkr(consignment):
    foreign_total = Decimal("0")
    priced = False

    for item in consignment.items:
        if item.quantity is not None and item.unit_price is not None:
            foreign_total = foreign_total + (item.quantity * item.unit_price)
            priced = True

    if not priced or consignment.exchange_rate is None:
        return Decimal("0")

    return foreign_total * consignment.exchange_rate


#-------------------------------------
# THE HEADLINE NUMBERS (KPIS)
#-------------------------------------

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
    counts = {}

    for consignment in consignments:
        status = consignment.current_status
        counts[status] = counts.get(status, 0) + 1

    ordered = []

    for status in [s.value for s in Status]:
        if counts.get(status):
            ordered.append({"label": status, "value": counts[status]})

    return ordered


#-------------------------------------
# VALUE GROUPED BY SOMETHING, TOP FIRST
#
# Used for value by country and value by supplier. A generic
# helper so both read from one place. key_fn pulls the label
# off a consignment.
#-------------------------------------

def value_by(consignments, key_fn, limit=None):
    totals = {}

    for consignment in consignments:
        label = key_fn(consignment)

        if not label:
            continue

        totals[label] = totals.get(label, Decimal("0")) + consignment_value_pkr(consignment)

    rows = [
        {"label": label, "value": value}
        for label, value in totals.items()
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

def monthly_value_trend(consignments):
    totals = {}

    for consignment in consignments:
        day = (
            consignment.eta_works or consignment.etd
            or consignment.eta or consignment.cargo_readiness_date
        )

        if day is None:
            continue

        month = day.strftime("%Y-%m")
        totals[month] = totals.get(month, Decimal("0")) + consignment_value_pkr(consignment)

    trend = [
        {"month": month, "value": totals[month]}
        for month in sorted(totals.keys())
    ]

    return trend
