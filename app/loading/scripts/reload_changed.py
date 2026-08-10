"""Reload ONLY the sources that changed: purchases, issuance and imports.

WHY NOT load_all
    `load_all` is an all-or-nothing destructive reload. It would also drop and
    rebuild stock, store requisitions, logistics and trucking — none of which
    have new source files. Two things would be lost for nothing:

      * the 1,424 logistics orders' customer_id links (and the customers master
        is seeded FROM those orders, so it would have to be rebuilt too), and
      * the stock rows, which would be reloaded from workbooks that have not
        changed — pure churn, with a real chance of collateral damage.

    So this script reloads exactly the three families whose workbooks are new.

WHAT IT TOUCHES
    dropped + reloaded : purchases_data, issuance
                         consignments family + the masters that come from the
                         imports sheet (suppliers, branches, clearing_agents,
                         ports) — the consignment rows reference those by id, so
                         they have to be rebuilt together
    left alone         : items, stock, store_requisition, customers,
                         logistics family, trucking family, users/permissions

AFTERWARDS
    The two standalone backfills are re-run automatically, because a reload
    wipes what they write:
      * backfill_import_demand_dates — the ONLY source of requisition_date,
        required_date, pkr_total and foreign_total on loaded consignments
      * resync_sequences — belt and braces; the loaders bump their own now

USAGE
    python -m app.loading.scripts.reload_changed
    python -m app.loading.scripts.reload_changed --check   # report only
"""

import sys

from app.loading.database_connection import connection, cursor

# Order matters: the imports masters must exist before consignments reference
# them, and items must already be loaded (it is, and is not touched here) for
# the item-code assignment to resolve against the master.
from app.loading.scripts.stores.load_02_purchases_data import load_purchases
from app.loading.scripts.stores.load_04_issuance import load_issuances
from app.loading.scripts.imports.load_01_suppliers import load_suppliers
from app.loading.scripts.imports.load_02_branches import load_branches
from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
from app.loading.scripts.imports.load_04_ports import load_ports
from app.loading.scripts.imports.load_05_consignments import load_consignments

# CASCADE so dependent constraints go with them. The consignment family is
# dropped whole: create_all only creates MISSING tables, so a child left behind
# would keep stale rows pointing at parents that no longer exist.
DROP_SQL = (
    "DROP TABLE IF EXISTS "
    "purchases_data, issuance, "
    "consignments, consignment_items, payments, eta_revision_history, "
    "status_update_history, consignment_change_history, "
    "suppliers, branches, clearing_agents, ports "
    "CASCADE;"
)

PRESERVED = [
    ("stock", "no new workbook"),
    ("store_requisition", "no new workbook"),
    ("items", "no new workbook; needed to resolve item codes"),
    ("customers", "app-managed master"),
    ("logistics_consignments", "holds the customer_id links"),
    ("trucking_consignments", "no new workbook"),
]


def counts(label):
    print(f"\n{label}")
    for table, _why in PRESERVED + [("purchases_data", ""), ("issuance", ""),
                                    ("consignments", ""), ("consignment_items", "")]:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            print(f"   {table:<26} {cursor.fetchone()[0]:>9,}")
        except Exception:
            connection.rollback()
            print(f"   {table:<26} {'(missing)':>9}")


def main():
    if "--check" in sys.argv:
        counts("current row counts:")
        print("\npreserved by this script:")
        for table, why in PRESERVED:
            print(f"   {table:<26} {why}")
        print("\n--check given, nothing was changed.")
        return

    counts("BEFORE:")

    print("\ndropping the tables being reloaded...")
    cursor.execute(DROP_SQL)
    connection.commit()

    # Recreate the schema. create_all adds back exactly the tables just dropped
    # and leaves everything else alone.
    import app.main as main_app
    main_app.create_tables()

    for label, fn in [
        ("Purchases", load_purchases),
        ("Issuances", load_issuances),
        ("Suppliers", load_suppliers),
        ("Branches", load_branches),
        ("Clearing Agents", load_clearing_agent),
        ("Ports", load_ports),
        ("Consignments", load_consignments),
    ]:
        print(f"\n--- {label} ---")
        try:
            fn(connection)
        except Exception as exc:
            connection.rollback()
            print(f"!! {label} FAILED — {type(exc).__name__}: {exc}")
            raise

    counts("\nAFTER:")

    print("\n--- backfills (a reload wipes what these write) ---")
    from app.loading.scripts.backfill_import_demand_dates import run as backfill_dates
    backfill_dates()

    from app.loading.scripts.resync_sequences import main as resync
    resync()


if __name__ == "__main__":
    main()
