"""
Reload the logistics workbook — orders, packing, shipments and trucking.

WHY THIS IS NOT PART OF `reload_changed`

    `reload_changed` deliberately leaves logistics alone, because reloading it
    drops `logistics_consignments` and with it the customer_id link on all
    1,424 orders — and the customers master is seeded FROM those orders, so it
    has to be rebuilt in the same breath or the Masters screen comes back with
    a customer list that no order points at.

    That is exactly why this script exists rather than a note telling somebody
    to remember two commands. The rebuild is a STEP HERE, not homework:

        drop -> create_all -> load logistics -> load trucking
             -> rebuild customer master + links -> resync sequences -> verify

WHAT IT TOUCHES

    dropped + reloaded : logistics_consignments (+ items / packages /
                         containers / status + change history),
                         trucking_consignments (+ vehicles / change history)
    rebuilt            : customers, and every order's customer_id
    left alone         : imports, purchases, issuance, stock, store
                         requisitions, items, users/permissions

WHAT IS LOST

    Anything entered through the APP in these two modules. That is inherent to
    a reload of loaded tables and is the same trade `load_all` makes; there is
    no key that would let app rows be told apart from sheet rows and preserved.

USAGE
    python -m app.loading.scripts.reload_logistics
    python -m app.loading.scripts.reload_logistics --check   # report only
"""

import sys

from app.loading.database_connection import connection, cursor

from app.loading.scripts.logistics.load_01_logistics import load_logistics
from app.loading.scripts.logistics.load_03_trucking import load_trucking

# CASCADE, and the whole family together: create_all only creates MISSING
# tables, so a child left behind would keep rows pointing at parents that no
# longer exist, and a reload assigns fresh ids so those pointers would be wrong
# anyway.
DROP_SQL = (
    "DROP TABLE IF EXISTS "
    "logistics_consignments, logistics_items, logistics_packages, "
    "logistics_containers, logistics_status_history, logistics_change_history, "
    "trucking_consignments, trucking_vehicles, trucking_change_history "
    "CASCADE;"
)

COUNTED = [
    ("logistics_consignments", ""),
    ("logistics_items", ""),
    ("logistics_packages", ""),
    ("logistics_containers", ""),
    ("trucking_consignments", ""),
    ("trucking_vehicles", ""),
    ("customers", "rebuilt from the orders"),
    ("consignments", "PRESERVED — imports is not touched"),
    ("purchases_data", "PRESERVED"),
    ("stock", "PRESERVED"),
]


def counts(label):
    print(f"\n{label}")
    for table, note in COUNTED:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            print(f"   {table:<26} {cursor.fetchone()[0]:>9,}  {note}")
        except Exception:
            connection.rollback()
            print(f"   {table:<26} {'(missing)':>9}")


def linked_orders():
    try:
        cursor.execute(
            "SELECT count(*), count(customer_id) FROM logistics_consignments"
        )
        return cursor.fetchone()
    except Exception:
        connection.rollback()
        return (0, 0)


def main():
    if "--check" in sys.argv:
        counts("current row counts:")
        total, linked = linked_orders()
        print(f"\ncustomer links: {linked:,} of {total:,} orders")
        print("\n--check given, nothing was changed.")
        return

    counts("BEFORE:")
    before_total, before_linked = linked_orders()
    print(f"\ncustomer links before: {before_linked:,} of {before_total:,} orders")

    print("\ndropping the logistics + trucking families...")
    cursor.execute(DROP_SQL)
    connection.commit()

    # Recreate exactly the tables just dropped; everything else is untouched.
    import app.main as main_app
    main_app.create_tables()

    for label, fn in [
        ("Logistics orders", load_logistics),
        ("Trucking jobs", load_trucking),
    ]:
        print(f"\n--- {label} ---")
        try:
            fn(connection)
        except Exception as exc:
            connection.rollback()
            print(f"!! {label} FAILED — {type(exc).__name__}: {exc}")
            raise

    # THE STEP THAT MUST NOT BE FORGOTTEN. The orders were just replaced, so
    # every customer_id went with them; the master is seeded from those names.
    print("\n--- Customer master + order links (a reload wipes these) ---")
    for label, step in [
        ("Customer master", _rebuild_customers),
        ("Sequence resync", _resync),
    ]:
        print(f"\n--- {label} ---")
        try:
            step()
        except Exception as exc:
            print(f"!! {label} FAILED — {type(exc).__name__}: {exc}")

    counts("\nAFTER:")
    total, linked = linked_orders()
    print(f"\ncustomer links after: {linked:,} of {total:,} orders")
    if total and linked < total:
        print(f"   !! {total - linked:,} orders have no customer link — "
              f"check add_customer_master's report above")

    # Did every column the loaders write actually arrive?
    from app.loading.scripts.post_load import verify_load
    verify_load()


def _rebuild_customers():
    from app.loading.scripts.add_customer_master import main
    main()


def _resync():
    from app.loading.scripts.resync_sequences import main
    main()


if __name__ == "__main__":
    main()
