from app.dashboard.imports.calculations import (
    kpis, value_trend, status_split, value_by_branch,
    value_by_country, value_by_supplier,
    shafts_value, efs_split, demand_counts, delivery_delay, references,
    value_data_notes, population_split,
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
#
# THE POPULATION IS EVERY CONSIGNMENT IN THE WINDOW, ARRIVED ONES INCLUDED.
# It used to exclude "Arrived at Works" because this is an operational screen,
# but the Overview counted them, so the two disagreed by Rs 52.7m over the same
# window under the same label. One screen now answers one question: `population`
# below splits the set into In Process / Arrived / Cancelled, each carrying its
# own count AND value, so "what is still moving" is a tile rather than a hidden
# filter nobody could see.
#-------------------------------------

def serialize_imports_dashboard(consignments, period_from, period_to,
                                shafts_only=False, shafts=None,
                                period_value=None, population=None):
    """One screen, no figure stated twice.

    Two removals to keep it that way:
      * `import_spend` — it was the stored total of the same consignments
        `kpis.total_value_pkr` already totals, so two spend figures sat side by
        side differing only by basis. Shafts value replaces it.
      * `value_by_supplier` — `supplier_pareto` is the same breakdown with the
        cumulative line added, so the plain chart was a strictly worse copy.

    `shafts_only` does not filter anything here — the caller has already
    narrowed the list — it is echoed back so the screen can label its tiles as
    the shaft subset, and so the category-delay chart can be withheld (with the
    set restricted to shafts, "delay by item category" is one category).
    """
    return {
        "kpis": kpis(consignments),
        # The headline money, summed over the LINES arriving in the window and
        # dated by them — the same basis and the same rows as the Overview's,
        # so the two screens cannot report different money for one window.
        "period_value": period_value,
        # In Process / Arrived / Cancelled, each with count, value and the
        # records behind it. Replaces the old hidden status filter.
        # Line-dated, on the same money as `period_value` — one basis per
        # screen. The consignment-level fallback is only for callers with no db
        # handle and reports a different total; see population_from_lines.
        "population": population if population is not None else population_split(consignments),
        "status_split": status_split(consignments),
        "value_by_country": value_by_country(consignments),
        "value_by_branch": value_by_branch(consignments),
        "value_trend": value_trend(consignments, period_from, period_to),

        # Every consignment on the screen, so the headline count can list them.
        "references": references(consignments),
        # How the money was arrived at, and what it misses.
        "data_notes": value_data_notes(consignments),
        # Computed from the LINES and dated by them — see shafts_from_lines.
        # The consignment-level fallback exists only for callers that have no db
        # handle; it over-counts a consignment whose lines span two months.
        "shafts": shafts if shafts is not None else shafts_value(consignments),
        "shafts_only": shafts_only,
        "efs_split": efs_split(consignments),
        "demands": demand_counts(consignments),
        "delivery_delay": delivery_delay(consignments),
        "supplier_pareto": supplier_spend_pareto(consignments),
        # Withheld on the shafts tab: every row is a shaft there, so a chart of
        # "delay by item category" would be a single bar pretending to be a
        # comparison.
        "category_delays": None if shafts_only else category_delays(consignments),
    }
