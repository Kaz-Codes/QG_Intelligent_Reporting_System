from app.dashboard.whole import calculations as calc
from app.dashboard.whole import helpers
from app.dashboard.whole import references as refs
from app.dashboard.logistics import helpers as logistics_helpers
from app.dashboard.data_quality import coverage_note, note, collect, WARNING
from app.dashboard.period import serialize_period, resolve_period

#-------------------------------------
# THE OVERVIEW PAYLOAD
#
# Four sections, one per area of the business, each assembled from its own
# aggregate queries. Like the other dashboards this returns aggregates only —
# no row lists.
#
# EACH SECTION CARRIES ITS OWN WINDOW. There is no single date that means the
# same thing to imports, procurement and logistics — a consignment's arrival, a
# PO's date and a truck's run are different events — so one shared filter was
# comparing unlike things. Sections that genuinely have two candidate dates let
# the caller choose between them.
#
# EACH SECTION ALSO CARRIES ITS `references`. A cross-module rollup is the
# figure a reader can least easily check, so every tile that stands for a set of
# records can list them. These are bounded LIMIT queries (see references.py) —
# the no-row-lists rule still holds for the figures themselves.
#
# EACH SECTION ALSO CARRIES ITS DATA NOTES. Where a figure rests on a partly
# filled column, the note says so beside the number instead of leaving the
# reader to assume full coverage.
#-------------------------------------


def serialize_imports(db, date_from, date_to, date_field, period_kind,
                      shafts_only=False):
    total, rows, lines = helpers.imports_period_value(
        db, date_from, date_to, date_field, shafts_only)
    undated_rows, undated_value = helpers.imports_value_undated(db, date_field, shafts_only)

    population = helpers.imports_population(db, date_from, date_to, date_field, shafts_only)
    delay = helpers.imports_delay(db, date_from, date_to, date_field, shafts_only)

    live_total = undated_rows + rows if undated_rows else None
    dated, all_live = helpers.imports_date_coverage(db, date_field, shafts_only)

    field_label = "an ETA at works" if date_field != "required_date" else "a required date"

    notes = collect(
        coverage_note(
            dated, all_live, "live consignments", field_label,
            "Those consignments fall in no period at all.",
        ),
    )

    return {
        "period": serialize_period(date_from, date_to, period_kind),
        "date_field": date_field,
        # What the source holds against what the window caught — so an empty
        # month reads as "latest data is January" with a jump, not as Rs 0.
        "coverage": helpers.imports_coverage(db, date_from, date_to, date_field, shafts_only),
        "data_notes": notes,
        # Echoed back so the section can label its tiles as the shaft subset.
        "shafts_only": shafts_only,
        # Period
        "period_value": calc.imports_period_value(
            total, rows, undated_rows, undated_value, lines, date_field
        ),
        # Lifetime (a pipeline is a snapshot, not a window). Each of the three
        # carries count AND value, in the same shape, so the tiles in one row
        # can be read against each other — In Process used to show a count
        # alone, which said 30 consignments were moving without saying whether
        # that was Rs 4m or Rs 400m.
        "in_process": {
            **calc.imports_in_process(helpers.imports_in_process_by_stage(db, date_from, date_to, date_field, shafts_only)),
            "value": population["in_process"]["value"],
            "value_pct": calc.share(population["in_process"]["value"], population["total"]["value"]),
        },
        "arrived": {
            **population["arrived"],
            "value_pct": calc.share(population["arrived"]["value"], population["total"]["value"]),
        },
        "cancelled": {
            **population["cancelled"],
            "value_pct": calc.share(population["cancelled"]["value"], population["total"]["value"]),
        },
        "delayed": delay,
        "references": {
            "period_value": refs.imports_value_references(
                db, date_from, date_to, date_field, shafts_only),
            "in_process": refs.imports_in_process_references(
                db, date_from, date_to, date_field, shafts_only),
            "arrived": refs.imports_status_references(
                db, "arrived", date_from, date_to, date_field, shafts_only),
            "cancelled": refs.imports_status_references(
                db, "cancelled", date_from, date_to, date_field, shafts_only),
            "delayed": refs.imports_delayed_references(
                db, date_from, date_to, date_field, shafts_only),
        },
    }


def serialize_procurement(db, date_from, date_to, date_field, period_kind):
    total, orders, quantity = helpers.procurement_period_totals(db, date_from, date_to, date_field)
    late, comparable = helpers.procurement_delay(db, date_from, date_to, date_field)
    store_days, store_rows, po_days, po_rows = helpers.procurement_cycle_times(
        db, date_from, date_to, date_field
    )

    # Both candidate columns are populated on every row, so there is nothing to
    # warn about on coverage. The cycle-time basis is worth stating because rows whose demand
    # date sits after the purchase are excluded as data errors.
    notes = collect(
        note(WARNING, (
            "Cycle time excludes orders whose store-demand date falls after the "
            "purchase date — those are data errors, and counting them would "
            "report negative lead time."
        )) if store_rows and store_rows < orders else None,
    )

    # Every procurement figure is bounded by the window, on the PO date.
    return {
        "period": serialize_period(date_from, date_to, period_kind),
        "date_field": date_field,
        "coverage": helpers.purchases_coverage(db, date_from, date_to, date_field),
        "data_notes": notes,
        "period_value": calc.procurement_period_value(total, orders, quantity),
        "category_split": calc.procurement_category_split(
            helpers.procurement_category_totals(db, date_from, date_to, date_field)
        ),
        "delay": calc.procurement_delay(late, comparable),
        "cycle_time": calc.procurement_cycle_time(
            store_days, store_rows, po_days, po_rows
        ),
        # Grouped by PO, like every procurement figure above them — listing the
        # raw table would show one order once per line.
        "references": {
            "period_value": refs.procurement_value_references(db, date_from, date_to, date_field),
            "delay": refs.procurement_delay_references(db, date_from, date_to, date_field),
        },
    }


def serialize_logistics(db, date_from, date_to, date_field, period_kind):
    counts = helpers.shipments_handled(db, date_from, date_to, date_field)
    trucking = helpers.trucking_cost_by_movement(db, date_from, date_to, date_field)

    truck_dated, truck_total = helpers.trucking_date_coverage(db, date_field)

    field_label = "an ETD" if date_field != "eta" else "an arrival date"

    # This is the section the coverage problem actually bites: most logistics
    # orders carry neither an ETD nor an arrival date, so a windowed export
    # count is small for reasons that have nothing to do with activity.
    notes = collect(
        coverage_note(
            counts["export_datable"], counts["export_total"],
            "logistics orders", field_label,
            "Export shipments in a period therefore cover only the dated ones.",
        ),
        coverage_note(
            counts["import_datable"], counts["import_total"],
            "import consignments", field_label,
        ),
        coverage_note(
            truck_dated, truck_total, "trucking jobs", field_label,
        ),
    )

    return {
        "period": serialize_period(date_from, date_to, period_kind),
        "date_field": date_field,
        "coverage": helpers.logistics_coverage(db, date_from, date_to, date_field),
        "data_notes": notes,
        "trucking_cost": calc.logistics_trucking_cost(trucking),
        "shipments_handled": calc.logistics_shipments_handled(counts),
        # One figure from each of the section's three areas, so "logistics"
        # stops meaning "trucking". Each carries its own basis — see the
        # helpers for why these three and not the more obvious ones.
        "packed_tonnage": helpers.logistics_packed_tonnage(db, date_from, date_to),
        "freight_per_kg": helpers.logistics_freight_per_kg(
            db, date_from, date_to, date_field),
        "transit_time": helpers.logistics_transit_time(
            db, date_from, date_to, date_field),
        # Export against local, counted IN THE WINDOW like everything else
        # here, with the orders no window can reach reported alongside — not
        # one local order carries a business date.
        "order_types": logistics_helpers.order_type_counts(
            db, date_from, date_to, date_field),
        # One list per movement bucket as well as the total, because each
        # bucket is its own tile. Keyed by movement type, with the NULL group
        # under "Unclassified" — the same name the tile shows.
        "references": {
            "trucking_cost": refs.trucking_cost_references(db, date_from, date_to, date_field),
            "by_movement": {
                (movement or "Unclassified"): refs.trucking_cost_references(
                    db, date_from, date_to, date_field, movement=movement or "Unclassified"
                )
                for movement, *_ in trucking
            },
            "shipments_handled": refs.shipments_handled_references(
                db, date_from, date_to, date_field
            ),
            "export_orders": refs.order_type_references(
                db, "Export", date_from, date_to, date_field),
            # ALL TIME — see order_type_counts for why local cannot be windowed.
            "local_orders": refs.order_type_references(
                db, "Local", date_from, date_to, date_field, all_time=True),
        },
    }


def serialize_stores(db, dead_stock_days, issuance_from=None, issuance_to=None):
    # Both bounds omitted -> the current month, exactly like every other window
    # on the system. Resolved here rather than by the caller so the Stores
    # section cannot drift from the shared definition.
    issuance_from, issuance_to, issuance_kind = resolve_period(issuance_from, issuance_to)

    total_value, available_value, items = helpers.stock_totals(db)
    by_branch = helpers.stock_by_branch(db)
    consumption, window_days = helpers.consumption_by_branch(db)
    dead_items, dead_value, history_days = helpers.dead_stock(db, dead_stock_days)

    dead = calc.stores_dead_stock(
        dead_items, dead_value, dead_stock_days, items, total_value, history_days
    )

    # Stores has no date column at all — it is a snapshot — so the note here is
    # about the ISSUANCE history the movement figures lean on, not about stock.
    notes = collect(
        note(WARNING, (
            f"The {dead_stock_days}-day dead-stock threshold reaches further back "
            f"than the {history_days} days of issuance history held, so it really "
            f"means “never issued in the data we have” and will not respond "
            f"to a longer threshold."
        )) if dead.get("exceeds_history") else None,
    )

    # Stock is a snapshot, so the stock figures are not period-bounded; the
    # runway and the dead-stock cutoff carry their own windows instead. ISSUANCE
    # is the one thing here that genuinely happens in a period, so it carries
    # the section's window — its own, separate from the other sections'.
    return {
        "period": serialize_period(issuance_from, issuance_to, issuance_kind),
        "date_field": "issuance_date",
        "coverage": helpers.issuance_coverage(db, issuance_from, issuance_to),
        "data_notes": notes,
        # Replaces the "Stores holding stock" tile — a count of branches, which
        # changes about once a year and said nothing about how the stores run.
        # Items are counted BY ITEM CODE, folded across branches, exactly as
        # Inventory counts them.
        "issuance": helpers.issuance_period(db, issuance_from, issuance_to),
        "stock_value": calc.stores_stock_value(total_value, available_value, items),
        "value_by_store": calc.stores_value_by_store(by_branch),
        "stock_days": calc.stores_stock_days(by_branch, consumption, window_days),
        "dead_stock": dead,
        "references": {
            "stock_value": refs.stock_value_references(db),
            "dead_stock": refs.dead_stock_references(db, dead_stock_days),
            "issuance": refs.issuance_references(db, issuance_from, issuance_to),
        },
    }


def serialize_overview(db, sections, dead_stock_days, shafts_only=False):
    """`sections` carries each area's resolved window and chosen date field."""
    imports = sections["imports"]
    procurement = sections["procurement"]
    logistics = sections["logistics"]
    stores = sections.get("stores", {})

    return {
        "imports": serialize_imports(
            db, imports["from"], imports["to"], imports["field"], imports["kind"],
            shafts_only,
        ),
        "procurement": serialize_procurement(
            db, procurement["from"], procurement["to"],
            procurement["field"], procurement["kind"]
        ),
        "logistics": serialize_logistics(
            db, logistics["from"], logistics["to"], logistics["field"], logistics["kind"]
        ),
        "stores": serialize_stores(
            db, dead_stock_days, stores.get("from"), stores.get("to")
        ),
    }
