from decimal import Decimal

from app.enums import LogisticsStatus, OrderType

#-------------------------------------
# THE NUMBERS THE LOGISTICS DASHBOARD SHOWS
#
# All worked out from the live orders, nothing stored. The
# total logistics cost of an order is the sum of its named
# expenditure figures, and the cost per kg divides that by
# the gross weight.
#-------------------------------------

DELIVERED_STATUS = LogisticsStatus.DELIVERED.value

# The twelve expenditure columns that make up an order's
# total logistics cost. Listed once so adding a cost later
# is a one line change.
EXPENDITURE_FIELDS = [
    "packing_cost",
    "transportation_charges",
    "insurance",
    "trucking_lhr_to_khi",
    "fumigation_cost",
    "lashing",
    "qfl_charges",
    "qfl_container_movement",
    "custom_clearance_charges",
    "port_charges",
    "dhl_charges",
    "sea_air_freight",
]


#-------------------------------------
# THE TOTAL COST OF ONE ORDER
#-------------------------------------

def order_total_cost(consignment):
    total = Decimal("0")

    for field in EXPENDITURE_FIELDS:
        value = getattr(consignment, field)

        if value is not None:
            total = total + value

    return total


#-------------------------------------
# THE COST PER KG OF ONE ORDER
#
# Nothing to divide by when the gross weight is missing or
# zero, so it has no cost per kg rather than a wrong one.
#-------------------------------------

def order_cost_per_kg(consignment):
    if not consignment.gross_weight:
        return None

    return order_total_cost(consignment) / consignment.gross_weight


#-------------------------------------
# THE HEADLINE NUMBERS (KPIS)
#-------------------------------------

def kpis(consignments):
    total_cost = Decimal("0")
    delivered = 0
    exports = 0
    local = 0
    countries = set()

    per_kg_sum = Decimal("0")
    per_kg_count = 0

    for consignment in consignments:
        total_cost = total_cost + order_total_cost(consignment)

        if consignment.current_status == DELIVERED_STATUS:
            delivered = delivered + 1

        if consignment.order_type == OrderType.EXPORT.value:
            exports = exports + 1
        elif consignment.order_type == OrderType.LOCAL.value:
            local = local + 1

        if consignment.origin_country:
            countries.add(consignment.origin_country)

        per_kg = order_cost_per_kg(consignment)

        if per_kg is not None:
            per_kg_sum = per_kg_sum + per_kg
            per_kg_count = per_kg_count + 1

    avg_cost_per_kg = (per_kg_sum / per_kg_count) if per_kg_count else None

    return {
        "orders_shown": len(consignments),
        "delivered": delivered,
        "open": len(consignments) - delivered,
        "exports": exports,
        "local": local,
        "total_logistics_cost": total_cost,
        "avg_cost_per_kg": avg_cost_per_kg,
        "countries": len(countries)
    }


#-------------------------------------
# HOW MANY ORDERS SIT AT EACH STATUS
#
# In the order the stages actually happen in, and only
# statuses that are present.
#-------------------------------------

def status_split(consignments):
    counts = {}

    for consignment in consignments:
        status = consignment.current_status
        counts[status] = counts.get(status, 0) + 1

    ordered = []

    for status in [s.value for s in LogisticsStatus]:
        if counts.get(status):
            ordered.append({"label": status, "value": counts[status]})

    return ordered


#-------------------------------------
# HOW MANY ORDERS GROUPED BY SOMETHING
#
# Used for orders by country and orders by port of
# discharge. key_fn pulls the label off an order.
#-------------------------------------

def count_by(consignments, key_fn, limit=None):
    counts = {}

    for consignment in consignments:
        label = key_fn(consignment)

        if not label:
            continue

        counts[label] = counts.get(label, 0) + 1

    rows = [
        {"label": label, "value": value}
        for label, value in counts.items()
    ]

    rows.sort(key=lambda row: row["value"], reverse=True)

    if limit is not None:
        rows = rows[:limit]

    return rows


def orders_by_country(consignments, limit=8):
    return count_by(consignments, lambda c: c.origin_country, limit)


def orders_by_pod(consignments, limit=8):
    return count_by(consignments, lambda c: c.pod, limit)


def orders_by_shipping_line(consignments, limit=8):
    return count_by(consignments, lambda c: c.shipping_line, limit)


#-------------------------------------
# AVERAGE COST PER KG BY COUNTRY
#
# The average of each order's cost per kg, grouped by origin
# country, most expensive first. Orders with no weight are
# left out because they have no cost per kg.
#-------------------------------------

def cost_per_kg_by_country(consignments, limit=8):
    totals = {}

    for consignment in consignments:
        country = consignment.origin_country
        per_kg = order_cost_per_kg(consignment)

        if not country or per_kg is None:
            continue

        entry = totals.setdefault(country, {"sum": Decimal("0"), "count": 0})
        entry["sum"] = entry["sum"] + per_kg
        entry["count"] = entry["count"] + 1

    rows = [
        {"label": country, "value": entry["sum"] / entry["count"]}
        for country, entry in totals.items()
    ]

    rows.sort(key=lambda row: row["value"], reverse=True)

    return rows[:limit]


#-------------------------------------
# COST OVER TIME, MONTH BY MONTH
#
# Grouped by the port in date, falling back to when the
# order was created. Oldest month first.
#-------------------------------------

def monthly_cost_trend(consignments):
    totals = {}

    for consignment in consignments:
        day = consignment.port_in_date or (
            consignment.created_at.date() if consignment.created_at else None
        )

        if day is None:
            continue

        month = day.strftime("%Y-%m")
        totals[month] = totals.get(month, Decimal("0")) + order_total_cost(consignment)

    trend = [
        {"month": month, "value": totals[month]}
        for month in sorted(totals.keys())
    ]

    return trend
