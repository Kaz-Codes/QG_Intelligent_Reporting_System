from app.dashboard.whole import calculations as calc
from app.dashboard.whole import helpers

#-------------------------------------
# THE OVERVIEW PAYLOAD
#
# Four sections, one per area of the business, each assembled from its own
# aggregate queries. Like the other dashboards this returns aggregates only —
# no row lists.
#
# Sections are split into period figures (bounded by the resolved window) and
# lifetime figures (running totals that ignore it). Which is which is stated per
# figure below rather than left to the reader to infer from the name.
#-------------------------------------


def serialize_imports(db, date_from, date_to):
    total, rows = helpers.imports_period_value(db, date_from, date_to)
    undated_rows, undated_value = helpers.imports_value_without_etd(db)
    in_process, arrived = helpers.imports_shaft_counts(db)

    return {
        # Period
        "period_value": calc.imports_period_value(
            total, rows, undated_rows, undated_value
        ),
        # Lifetime (a pipeline is a snapshot, not a window)
        "in_process": calc.imports_in_process(helpers.imports_in_process_by_stage(db)),
        "shafts": calc.imports_shafts(in_process, arrived),
    }


def serialize_procurement(db, date_from, date_to):
    total, rows, quantity = helpers.procurement_period_totals(db, date_from, date_to)
    late, comparable = helpers.procurement_delay(db, date_from, date_to)
    store_days, store_rows, po_days, po_rows = helpers.procurement_cycle_times(
        db, date_from, date_to
    )

    # Every procurement figure is bounded by the window.
    return {
        "period_value": calc.procurement_period_value(total, rows, quantity),
        "category_split": calc.procurement_category_split(
            helpers.procurement_category_totals(db, date_from, date_to)
        ),
        "delay": calc.procurement_delay(late, comparable),
        "cycle_time": calc.procurement_cycle_time(
            store_days, store_rows, po_days, po_rows
        ),
    }


def serialize_logistics(db):
    export_orders, import_consignments = helpers.shipments_handled(db)

    # Both figures are lifetime: "till yet ... handled" is a running total, and
    # freight is reported against jobs that mostly predate the window.
    return {
        "trucking_cost": calc.logistics_trucking_cost(
            helpers.trucking_cost_by_movement(db)
        ),
        "shipments_handled": calc.logistics_shipments_handled(
            export_orders, import_consignments
        ),
    }


def serialize_stores(db, dead_stock_days):
    total_value, available_value, lines = helpers.stock_totals(db)
    by_branch = helpers.stock_by_branch(db)
    consumption, window_days = helpers.consumption_by_branch(db)
    dead_lines, dead_value, history_days = helpers.dead_stock(db, dead_stock_days)

    # Stock is a snapshot, so none of this is period-bounded; the runway and the
    # dead-stock cutoff carry their own windows instead.
    return {
        "stock_value": calc.stores_stock_value(total_value, available_value, lines),
        "value_by_store": calc.stores_value_by_store(by_branch),
        "stock_days": calc.stores_stock_days(by_branch, consumption, window_days),
        "dead_stock": calc.stores_dead_stock(
            dead_lines, dead_value, dead_stock_days, lines, total_value,
            history_days,
        ),
    }


def serialize_overview(db, date_from, date_to, period_kind, dead_stock_days):
    return {
        # The resolved window is echoed back so the front end labels the period
        # figures with the range they were actually computed over, instead of
        # assuming the one it asked for.
        "period": {
            "from": date_from,
            "to": date_to,
            "kind": period_kind,
        },
        "imports": serialize_imports(db, date_from, date_to),
        "procurement": serialize_procurement(db, date_from, date_to),
        "logistics": serialize_logistics(db),
        "stores": serialize_stores(db, dead_stock_days),
    }
