from app.dashboard.imports.calculations import (
    kpis, monthly_value_trend, status_split, value_by_branch,
    value_by_country, value_by_supplier,
    total_import_spend, demand_counts, delay_stats,
    supplier_spend_pareto, category_delays,
)

#-------------------------------------
# ASSEMBLE THE IMPORTS DASHBOARD
#
# One dictionary carrying the headline numbers and every
# chart the imports dashboard draws, so the front end gets
# the whole screen in a single call.
#
# `kpis` and the four value_by_* charts are the original screen. The block
# below it is the KPI document's figures, added alongside rather than replacing
# anything. Both are computed over the same filtered list.
#-------------------------------------

def serialize_imports_dashboard(consignments):
    return {
        "kpis": kpis(consignments),
        "status_split": status_split(consignments),
        "value_by_country": value_by_country(consignments),
        "value_by_supplier": value_by_supplier(consignments),
        "value_by_branch": value_by_branch(consignments),
        "monthly_value_trend": monthly_value_trend(consignments),

        # KPI document
        "import_spend": total_import_spend(consignments),
        "demands": demand_counts(consignments),
        "delay": delay_stats(consignments),
        "supplier_pareto": supplier_spend_pareto(consignments),
        "category_delays": category_delays(consignments),
    }
