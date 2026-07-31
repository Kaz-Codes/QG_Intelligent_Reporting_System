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

from app.loading.database_connection import cursor, connection

"""
load_all.py — one-shot loader for the whole database (logistics + imports).

It performs a CLEAN reload: the transaction tables are truncated first, then
repopulated from the source workbooks in the `Project Files/` folder. The
master tables (items / suppliers / purchase_order) are upserted idempotently,
so they are not truncated.

Source paths are resolved here (from `Project Files/`) and injected into the
loader modules, so the modules keep their own placeholder paths untouched.

Usage:  python -m database.scripts.load_all
"""

# ---------------------------------------------------------------------------
# Deleting old data
# ---------------------------------------------------------------------------
print("Deleting old data...\n")

cursor.execute('DROP TABLE IF EXISTS branches, clearing_agents,issuance,items,suppliers,store_requisition,stock, purchases, ports, consignments, eta_revision_history CASCADE;')

connection.commit()

print("Old data deleted succcessfully...\n")


def load_data(table_name, load_function):
    print("Populating " + table_name + "....")
    try:
        load_function(connection)
        print(table_name + " populated successfully....")
    except Exception as exc:
        connection.rollback()
        print(f"!! {table_name} FAILED — {type(exc).__name__}: {exc}")


# load_data("Items", load_items)
def call_load():
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

    print("\nAll load steps complete.")
