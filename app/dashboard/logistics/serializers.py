from app.dashboard.logistics.calculations import (
    cost_per_kg_by_country, kpis, monthly_cost_trend, orders_by_country,
    orders_by_pod, orders_by_shipping_line, status_split,
)

#-------------------------------------
# ASSEMBLE THE LOGISTICS DASHBOARD
#
# One dictionary with the headline numbers and every chart
# the logistics dashboard draws, so the front end gets the
# whole screen in a single call.
#-------------------------------------

def serialize_logistics_dashboard(consignments):
    return {
        "kpis": kpis(consignments),
        "status_split": status_split(consignments),
        "orders_by_country": orders_by_country(consignments),
        "orders_by_pod": orders_by_pod(consignments),
        "orders_by_shipping_line": orders_by_shipping_line(consignments),
        "cost_per_kg_by_country": cost_per_kg_by_country(consignments),
        "monthly_cost_trend": monthly_cost_trend(consignments)
    }
