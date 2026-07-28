from loading.scripts.stores.load_02_purchases_data import load_purchases
from loading.scripts.stores.load_04_issuance import load_issuances
from loading.scripts.stores.load_06_store_requisitions import load_store_requisitions
from loading.scripts.stores.load_05_stock import load_stock
from loading.scripts.stores.load_01_items import load_items
from loading.schemas.stores_schemas import stores_schemas_queries
from loading.schemas.create_schemas import execute_queries
from loading.database_connection import cursor, connection

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

cursor.execute('DROP TABLE IF EXISTS export_documents,export_shipments,exports,import_details,import_item,issuance,items,suppliers,store_requisition,stock,shipment_details,shipment_containers,shifting_movements,purchase_order,payment_history,packing_details, purchases_data, ab_items CASCADE;')

connection.commit()

print("Old data deleted succcessfully...\n")
# ---------------------------------------------------------------------------
# Creating schemas
# --------------------------------------------------------------------------
execute_queries(stores_schemas_queries, "Stores", "schemas")


def truncate_transaction_tables():
    """Clean slate for a repeatable full load. CASCADE clears the child tables;
    masters are left intact (they are upserted idempotently)."""
    print("Truncating transaction tables for a clean reload....")
    with connection.cursor() as cur:
        cur.execute("TRUNCATE exports CASCADE")          # logistics + its children
        cur.execute("TRUNCATE import_details CASCADE")   # imports + its children
    connection.commit()


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
    load_data("Purchases", load_purchases)
    load_data("Issuances", load_issuances)
    load_data("Stocks", load_stock)
    load_data("Store Requisitions", load_store_requisitions)
    
    print("\nAll load steps complete.")
