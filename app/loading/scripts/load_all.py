from app.loading.scripts.stores.load_02_purchases_data import load_purchases
from app.loading.scripts.stores.load_04_issuance import load_issuances
from app.loading.scripts.stores.load_06_store_requisitions import load_store_requisitions
from app.loading.scripts.stores.load_05_stock import load_stock
from app.loading.scripts.stores.load_01_items import load_items
from app.loading.scripts.imports.load_01_suppliers import load_suppliers
from app.loading.scripts.imports.load_02_branches import load_branches
from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
from app.loading.scripts.imports.load_04_ports import load_ports
from app.loading.scripts.imports.load_05_consignments import load_consignments
from app.loading.scripts.logistics.load_01_logistics import load_logistics
from app.loading.scripts.logistics.load_03_trucking import load_trucking

from app.loading.database_connection import cursor, connection

"""
load_all.py — the one-shot loader for the whole database (stores + imports +
logistics).

This is a DESTRUCTIVE full reload: it drops the loaded tables, recreates the
schema, and repopulates everything from the source workbooks under
`app/loading/data/`.

It is NOT run on import any more. Importing this module has no side effects — the
drop/reload only happens when you invoke it explicitly:

    python -m app.loading.scripts.load_all

Running it on every server start (the old behaviour) is what silently doubled
`purchases_data`: the table has no natural key, so a second insert never
conflicts, and a typo in the DROP list ('purchases' instead of 'purchases_data')
meant it was never actually cleared between runs.
"""

# Every table the loaders (re)populate, each loaded header dropped TOGETHER with
# its child / history tables. Two reasons the full family has to go, not just the
# header:
#   * create_all only creates MISSING tables — it never re-adds a foreign key to
#     a table that survived, so a child left behind would keep old rows and lose
#     its FK. Dropping the whole family lets create_all rebuild it cleanly.
#   * a reload assigns fresh ids, so any surviving child rows would point at the
#     wrong (or no) parent.
#
# CASCADE so order does not matter and dependent FK constraints go too. NOTE the
# stores table is 'purchases_data', not 'purchases' — a wrong name here makes the
# drop a silent no-op and the table accumulates a fresh copy on every load.
#
# NOT dropped: users / roles / permissions (the admin the loaders book against),
# saved_reports, activity logs, and the app-managed `works` master. These
# transaction tables (consignments / logistics / trucking families) also hold any
# rows entered through the app — a reload clears those too, by design.
DROP_SQL = (
    "DROP TABLE IF EXISTS "
    # masters + their children
    "suppliers, branches, clearing_agents, ports, items, hs_codes, "
    # stores
    "purchases_data, issuance, stock, store_requisition, "
    # imports (consignment) family
    "consignments, consignment_items, payments, eta_revision_history, "
    "status_update_history, consignment_change_history, "
    # logistics family
    "logistics_consignments, logistics_items, logistics_packages, "
    "logistics_containers, logistics_status_history, logistics_change_history, "
    # trucking family
    "trucking_consignments, trucking_vehicles, trucking_change_history "
    "CASCADE;"
)


def drop_transaction_tables():
    print("Deleting old data...\n")
    cursor.execute(DROP_SQL)
    connection.commit()
    print("Old data deleted successfully...\n")


def load_data(table_name, load_function):
    print("Populating " + table_name + "....")
    try:
        load_function(connection)
        print(table_name + " populated successfully....")
    except Exception as exc:
        connection.rollback()
        print(f"!! {table_name} FAILED — {type(exc).__name__}: {exc}")


def call_load():
    """Run every loader against tables that already exist. Does NOT drop or
    create anything — reset_and_load() handles that."""
    load_data("Items", load_items)
    load_data("Purchases", load_purchases)
    load_data("Issuances", load_issuances)
    load_data("Stocks", load_stock)
    load_data("Store Requisitions", load_store_requisitions)
    load_data("Suppliers", load_suppliers)
    load_data("Branches", load_branches)
    load_data("Clearing Agents", load_clearing_agent)
    load_data("Ports", load_ports)
    load_data("Consignments", load_consignments)
    load_data("Logistics", load_logistics)
    load_data("Trucking", load_trucking)

    print("\nAll load steps complete.")


def reset_and_load():
    """The destructive full reload, run from the command line.

    Order matters: the schema and the seeded admin must exist first (the
    logistics loaders book rows against the admin), then the loaded tables are
    dropped, recreated empty, and refilled.
    """
    # Importing the app creates every table and seeds the roles + admin. It no
    # longer triggers a data load, so this is a safe, side-effect-light way to
    # reuse that setup without duplicating it here.
    import app.main as main_app

    drop_transaction_tables()
    main_app.create_tables()   # recreate the tables just dropped
    call_load()


if __name__ == "__main__":
    reset_and_load()
