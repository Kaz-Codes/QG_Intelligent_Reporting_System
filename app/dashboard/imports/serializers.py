from app.dashboard.imports.calculations import (
    kpis, monthly_value_trend, status_split, value_by_branch,
    value_by_country, value_by_supplier,
)

#-------------------------------------
# ASSEMBLE THE IMPORTS DASHBOARD
#
# One dictionary carrying the headline numbers and every
# chart the imports dashboard draws, so the front end gets
# the whole screen in a single call.
#-------------------------------------

def serialize_imports_dashboard(consignments):
    return {
        "kpis": kpis(consignments),
        "status_split": status_split(consignments),
        "value_by_country": value_by_country(consignments),
        "value_by_supplier": value_by_supplier(consignments),
        "value_by_branch": value_by_branch(consignments),
        "monthly_value_trend": monthly_value_trend(consignments)
    }
