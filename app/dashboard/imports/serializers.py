from app.dashboard.imports.calculations import (
    kpis, value_trend, status_split, value_by_branch,
    value_by_country, value_by_supplier,
    shafts_value, efs_split, demand_counts, delivery_delay, references,
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

def serialize_imports_dashboard(consignments, period_from, period_to):
    """One screen, no figure stated twice.

    Two removals to keep it that way:
      * `import_spend` — it was the stored total of the same consignments
        `kpis.total_value_pkr` already totals, so two spend figures sat side by
        side differing only by basis. Shafts value replaces it.
      * `value_by_supplier` — `supplier_pareto` is the same breakdown with the
        cumulative line added, so the plain chart was a strictly worse copy.
    """
    return {
        "kpis": kpis(consignments),
        "status_split": status_split(consignments),
        "value_by_country": value_by_country(consignments),
        "value_by_branch": value_by_branch(consignments),
        "value_trend": value_trend(consignments, period_from, period_to),

        # Every consignment on the screen, so the headline count can list them.
        "references": references(consignments),
        "shafts": shafts_value(consignments),
        "efs_split": efs_split(consignments),
        "demands": demand_counts(consignments),
        "delivery_delay": delivery_delay(consignments),
        "supplier_pareto": supplier_spend_pareto(consignments),
        "category_delays": category_delays(consignments),
    }
