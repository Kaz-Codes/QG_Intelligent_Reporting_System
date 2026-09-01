"""Reload ONLY the sources that changed: purchases and issuance.

THE APP IS THE SYSTEM OF RECORD for imports, logistics and trucking — see the
docstring in load_all.py. This script used to drop and rebuild the whole
consignment family plus the masters the imports sheet feeds, which made it the
fastest way in the repo to destroy a week of data entry. It no longer touches
any of them.

WHY NOT load_all
    load_all rebuilds stock, items and store_requisition as well. When only the
    purchases and issuance workbooks are new, that is pure churn: re-reading two
    large sheets to write back what is already there.

WHAT IT TOUCHES
    dropped + reloaded : purchases_data, issuance
    left alone         : EVERYTHING else — items, stock, store_requisition,
                         the consignments / logistics / trucking families, all
                         masters, users and permissions

AFTERWARDS
      * resync_sequences — the loaders insert explicit ids through raw psycopg2,
        which does not advance a sequence; without this the first row the APP
        inserts reuses an id and dies on the primary key
      * backfill_import_demand_dates is NO LONGER RUN. It filled columns on
        freshly-loaded consignments, and consignments are not loaded any more.
        It also maps sheet groups onto consignment ids POSITIONALLY, which stops
        being true the moment operators create or delete records. See the note
        in load_all.run_post_load_steps.

    Then `post_load.verify_load` checks that every column the loaders are
    supposed to write actually arrived, and repairs the ones it can. That is
    the safety net for a re-shaped workbook: a renamed column does not raise,
    it just lands NULL, and the figure built on it quietly reads zero.

USAGE
    python -m app.loading.scripts.reload_changed
    python -m app.loading.scripts.reload_changed --check   # report only
"""

import sys

from app.loading.database_connection import connection, cursor

from app.loading.scripts.stores.load_02_purchases_data import load_purchases
from app.loading.scripts.stores.load_04_issuance import load_issuances

# The imports loaders are deliberately NOT imported — see the docstring. They
# still exist under scripts/imports/ as the record of how that workbook maps
# onto the schema; nothing here invokes them.
# from app.loading.scripts.imports.load_01_suppliers import load_suppliers
# from app.loading.scripts.imports.load_02_branches import load_branches
# from app.loading.scripts.imports.load_03_clearing_agent import load_clearing_agent
# from app.loading.scripts.imports.load_04_ports import load_ports
# from app.loading.scripts.imports.load_05_consignments import load_consignments

# The same guard load_all uses, imported rather than copied so the two scripts
# cannot drift about what "app-owned" means.
from app.loading.scripts.load_all import (
    snapshot_protected_counts, report_protected_counts,
)

# CASCADE so dependent constraints go with them. The consignment family is
# dropped whole: create_all only creates MISSING tables, so a child left behind
# would keep stale rows pointing at parents that no longer exist.
# THE CONSIGNMENT FAMILY AND THE IMPORTS MASTERS USED TO BE IN THIS LIST. They
# are not any more: the app owns those rows, and dropping them here destroyed
# operator work every time somebody ran the "safe, targeted" reload.
#
# NOTE 'purchases_data', not 'purchases' — a wrong name makes the drop a silent
# no-op and the table accumulates a second copy on every run.
DROP_SQL = (
    "DROP TABLE IF EXISTS "
    "purchases_data, issuance "
    "CASCADE;"
)

PRESERVED = [
    ("items", "app-owned master; FKs point at items.id"),
    ("stock", "no new workbook"),
    ("store_requisition", "no new workbook"),
    ("consignments family", "APP-OWNED - entered through the UI"),
    ("logistics family", "APP-OWNED - entered through the UI"),
    ("trucking family", "APP-OWNED - entered through the UI"),
    ("suppliers / branches / ports", "app-managed masters"),
    ("clearing_agents / customers", "app-managed masters"),
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

    protected_before = snapshot_protected_counts()
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
    ]:
        print(f"\n--- {label} ---")
        try:
            fn(connection)
        except Exception as exc:
            connection.rollback()
            print(f"!! {label} FAILED — {type(exc).__name__}: {exc}")
            raise

    counts("\nAFTER:")

    # backfill_import_demand_dates is deliberately absent — see the docstring:
    # consignments are no longer loaded, and its positional sheet-to-id mapping
    # stops holding once operators create or delete records.
    print("")
    print("--- sequence resync ---")
    from app.loading.scripts.resync_sequences import main as resync
    resync()

    # The same before/after check load_all runs. If a future edit puts a
    # transaction table back into DROP_SQL, this is what says so.
    if not report_protected_counts(protected_before, snapshot_protected_counts()):
        sys.exit(1)


if __name__ == "__main__":
    main()
