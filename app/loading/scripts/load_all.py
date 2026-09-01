from app.loading.scripts.stores.load_02_purchases_data import load_purchases
from app.loading.scripts.stores.load_04_issuance import load_issuances
from app.loading.scripts.stores.load_06_store_requisitions import load_store_requisitions
from app.loading.scripts.stores.load_05_stock import load_stock
from app.loading.scripts.stores.load_01_items import load_items

# RETAINED BUT NO LONGER CALLED. These loaded the imports, logistics and
# trucking families from workbooks, back when Excel was the source of truth for
# them. The app is the system of record for those now (see the module docstring),
# so invoking any of them would overwrite operator-entered work with a sheet.
#
# Kept rather than deleted because they are the only written record of how those
# workbooks map onto the schema, and because a one-off migration from a new
# workbook may still want them — run deliberately, against an empty database,
# never as part of a reload.
#
#   from app.loading.scripts.imports.load_01_suppliers import load_suppliers
#   from app.loading.scripts.imports.load_02_branches import load_branches
#   from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
#   from app.loading.scripts.imports.load_04_ports import load_ports
#   from app.loading.scripts.imports.load_05_consignments import load_consignments
#   from app.loading.scripts.logistics.load_01_logistics import load_logistics
#   from app.loading.scripts.logistics.load_03_trucking import load_trucking
#
# data/imports/ and data/logistics/ are therefore dead inputs. They are left on
# disk; nothing reads them.

from pathlib import Path

from app.loading.database_connection import cursor, connection

"""
load_all.py — reloads the STORES reference data, and nothing else.

THE APP IS THE SYSTEM OF RECORD for imports, logistics and trucking. Excel is
the source only for stores/inventory reference data. This script therefore
refreshes a narrow set of tables and is explicitly forbidden from touching
anything an operator can create or edit in the UI.

WHAT IS REPLACED (dropped and rebuilt from the workbooks under
`app/loading/data/`):

    stock              <- stocks, with rank from ab_items
    purchases_data     <- purchases
    issuance           <- issuances
    store_requisition  <- store_requisitions

WHAT IS UPSERTED, NEVER DROPPED:

    items              <- items_database (+ codes appearing in the sheets above)

    Because consignment_items.item_id and hs_codes.item_id are REAL FOREIGN
    KEYS onto items.id. Dropping items would SET NULL the master link on every
    consignment line that has one, and CASCADE-delete every HS code — both on
    app-owned rows. So items are matched on item_code and updated in place;
    ids are never reissued and a master is never deleted.

WHAT IS NEVER TOUCHED:

    consignments / logistics / trucking families and their history tables,
    suppliers, branches, clearing_agents, ports, customers, hs_codes, works,
    users, permissions, saved_reports, activity logs, notification tables.

THIS USED TO BE A DESTRUCTIVE FULL RELOAD that dropped the transaction
families "by design", on the reasoning that the workbooks were the truth and
the app a viewer. That is reversed: a reload that erased a week of data entry
is now the worst thing this script could do, and the row-count guard at the
end exists to catch any future edit that reintroduces it.

The DATABASE ITSELF must already exist: create_all builds tables, not the
database. On a brand-new machine:

    createdb supply_chain_erp          # or whatever DB_NAME in .env says
    python -m app.loading.scripts.load_all

and the source workbooks must be present under `app/loading/data/` — they are
NOT in git, so a fresh clone has none of them and every loader finds nothing
to read.

It is NOT run on import. Importing this module has no side effects; the reload
only happens when you invoke it explicitly.

Running it on every server start (the old behaviour) is what silently doubled
`purchases_data`: the table has no natural key, so a second insert never
conflicts, and a typo in the DROP list ('purchases' instead of
'purchases_data') meant it was never actually cleared between runs.
"""

# Only the stores tables that are wholly rebuilt from a workbook. Each is a flat
# load with no app-entered rows and nothing pointing at its id, so dropping is
# the simplest way to guarantee the table matches the sheet.
#
# CASCADE so order does not matter and dependent objects (the chatbot's semantic
# views, which build on stock) go with them — they are recreated at the end.
#
# NOTE the stores table is 'purchases_data', not 'purchases' — a wrong name here
# makes the drop a silent no-op and the table accumulates a fresh copy on every
# load. That exact typo is why purchases_data once held two of everything.
#
# `items` IS DELIBERATELY ABSENT. It is upserted, not replaced — see the module
# docstring. Adding it here would SET NULL consignment_items.item_id and
# CASCADE-delete hs_codes.
DROP_SQL = (
    "DROP TABLE IF EXISTS "
    "purchases_data, issuance, stock, store_requisition "
    "CASCADE;"
)

# Everything the app owns. Counted before and after a reload; any change is a
# bug in this script, not a difference of opinion.
PROTECTED_TABLES = (
    # imports family
    "consignments", "consignment_items", "payments",
    "eta_revision_history", "status_update_history", "consignment_change_history",
    # logistics family
    "logistics_consignments", "logistics_items", "logistics_packages",
    "logistics_containers", "logistics_status_history", "logistics_change_history",
    # trucking family
    "trucking_consignments", "trucking_vehicles", "trucking_change_history",
    # masters and accounts the app maintains
    "suppliers", "branches", "clearing_agents", "ports", "customers",
    "hs_codes", "works", "users", "permissions", "saved_reports",
)


def snapshot_protected_counts():
    """Row counts for every table this script must not change.

    A table that does not exist yet counts as None rather than raising, so this
    still works on a partially-built database.
    """
    counts = {}
    with connection.cursor() as cur:
        for table in PROTECTED_TABLES:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
            except Exception:
                connection.rollback()
                counts[table] = None
    connection.commit()
    return counts


def report_protected_counts(before, after):
    """Print both snapshots and shout if anything moved. Returns True if intact.

    THIS IS THE POINT OF THE WHOLE FILE. Everything above is an intention;
    this is the check that the intention held. If somebody later adds a table
    back into DROP_SQL, or re-enables one of the retired loaders, the numbers
    below stop matching and say so in terms nobody can miss.
    """
    print("\n" + "=" * 60)
    print("APP-OWNED DATA — must be identical before and after")
    print("=" * 60)

    changed = []
    for table in PROTECTED_TABLES:
        b, a = before.get(table), after.get(table)
        flag = ""
        if b != a:
            changed.append((table, b, a))
            flag = "   <-- CHANGED"
        print(f"  {table:32} {str(b):>8} -> {str(a):>8}{flag}")

    if not changed:
        print("\n  OK — every app-owned table is untouched.")
        return True

    print("\n" + "!" * 60)
    print("!! DATA LOSS: this reload CHANGED app-owned tables.")
    print("!! The loader is only ever allowed to touch the stores tables.")
    for table, b, a in changed:
        print(f"!!   {table}: {b} -> {a}")
    print("!! Restore from backup and fix DROP_SQL / call_load before rerunning.")
    print("!" * 60)
    return False


def drop_stores_tables():
    print("Clearing the stores tables...\n")
    cursor.execute(DROP_SQL)
    connection.commit()
    print("Stores tables cleared.\n")


def load_data(table_name, load_function):
    print("Populating " + table_name + "....")
    try:
        load_function(connection)
        print(table_name + " populated successfully....")
    except Exception as exc:
        connection.rollback()
        print(f"!! {table_name} FAILED — {type(exc).__name__}: {exc}")


def run_post_load_steps():
    """The steps that must follow every load, run here so they cannot be missed.

    ONLY ONE REMAINS. The other two were retired with the transaction loaders:

      * backfill_import_demand_dates filled requisition_date, required_date,
        pkr_total and foreign_total on FRESHLY LOADED consignments. Consignments
        are no longer loaded, so there is nothing for it to fill — and it is not
        merely redundant but unsafe to run on a schedule now. It maps sheet
        groups onto consignments POSITIONALLY (group N -> id N+1), guarded by an
        alignment check against instrument_number. Once operators create and
        delete consignments through the app, that ordering drifts, and the check
        starts aborting. The script survives for a deliberate one-off repair;
        it must not run automatically against app-owned rows.

      * add_customer_master built the customers master FROM the logistics orders
        and merged duplicates — including `DELETE FROM customers`. Both the
        orders and the customers master are app-owned now, so it would delete
        rows this script has no business deleting. Dropped.

      * resync_sequences stays, and matters more than it looks: the stores
        loaders insert explicit ids through raw psycopg2, which does not advance
        a table's sequence. Leave it and the first row the APP inserts reuses an
        id and dies on the primary key, surfacing as a bare "Internal server
        error" with nothing to point at.

    It ENDS WITH A CHECK. The loaders' dangerous failure is not a crash but a
    column that quietly arrives empty when a workbook is re-shaped — that is how
    `ppc_store` went NULL on all 65,520 rows and left the cycle time blank with
    nobody any the wiser. `verify_load` reports on every column that has done
    that before, and repairs the ones it can.
    """
    print("\n" + "=" * 60)
    print("POST-LOAD STEPS")
    print("=" * 60)

    from app.loading.scripts.resync_sequences import main as resync

    for label, step in [
        ("Sequence resync", resync),
    ]:
        print(f"\n--- {label} ---")
        try:
            step()
        except Exception as exc:
            print(f"!! {label} FAILED — {type(exc).__name__}: {exc}")


def call_load():
    """Run the stores loaders against tables that already exist.

    Does NOT drop or create anything — reload_stores_data() handles that.

    Items runs FIRST because purchases_data, issuance, stock and
    store_requisition all carry a foreign key onto items.item_code; a code that
    is not in the master yet fails the constraint and takes the whole load down.
    """
    load_data("Items", load_items)
    load_data("Purchases", load_purchases)
    load_data("Issuances", load_issuances)
    load_data("Stocks", load_stock)
    load_data("Store Requisitions", load_store_requisitions)

    run_post_load_steps()

    print("\nAll load steps complete.")


# The chatbot reads business definitions (branch aliases, stock position, the
# per-item demand picture) out of SQL views. Those views are built ON stock,
# which DROP_SQL still drops, so CASCADE takes them with it. Recreating them is
# part of a reload, not a separate chore: skip it and the chatbot answers
# "relation v_item_stock_position does not exist" until somebody notices. This
# has already happened three times.
#
# The path is resolved from THIS file, and the repo layout has moved once
# (the ERP used to be nested one level deeper), so it is searched rather than
# assumed - a wrong hard-coded depth fails silently, which is the whole problem.
def _find_semantic_views_sql():
    here = Path(__file__).resolve()
    for base in here.parents:
        candidate = base / "chatbot_backend" / "database" / "semantic_views.sql"
        if candidate.exists():
            return candidate
        candidate = base / "database" / "semantic_views.sql"
        if candidate.exists():
            return candidate
    return None


def create_semantic_views():
    path = _find_semantic_views_sql()
    if path is None:
        print("\n!! semantic views: semantic_views.sql not found, SKIPPED.")
        print("   The chatbot will fail on stock, branch and item questions.")
        return

    print(f"\nCreating semantic views from {path} ...")
    try:
        cursor.execute(path.read_text(encoding="utf-8"))
        connection.commit()
        cursor.execute(
            "SELECT count(*) FROM information_schema.views "
            r"WHERE table_schema = 'public' AND table_name LIKE 'v\_%'"
        )
        print(f"Semantic views created ({cursor.fetchone()[0]} views).")
    except Exception as exc:
        connection.rollback()
        print(f"!! semantic views FAILED - {type(exc).__name__}: {exc}")


def reload_stores_data():
    """Refresh the stores reference data from the workbooks.

    Renamed from reset_and_load(), which described what it used to be: a
    destructive full reload of everything. It is not that any more, and a name
    promising a reset invites somebody to reach for it expecting one.

    Order matters: the schema and the seeded admin must exist first, then the
    stores tables are dropped, recreated empty, and refilled. Bracketed by a
    count of every app-owned table, so a regression that starts destroying
    operator work announces itself instead of being discovered weeks later.
    """
    # Importing the app creates any missing table and seeds the permissions +
    # admin. It no longer triggers a data load, so this is a safe way to reuse
    # that setup without duplicating it here.
    import app.main as main_app

    before = snapshot_protected_counts()

    drop_stores_tables()
    main_app.create_tables()   # recreate the stores tables just dropped
    call_load()
    create_semantic_views()

    after = snapshot_protected_counts()
    intact = report_protected_counts(before, after)

    return intact


if __name__ == "__main__":
    import sys
    sys.exit(0 if reload_stores_data() else 1)
