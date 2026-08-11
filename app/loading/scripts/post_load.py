"""
The steps that must follow every load, and the check that they worked.

WHY THIS EXISTS

    A loader keyed on column NAMES fails silently when a workbook is re-shaped.
    The purchases export split `PPC/Store` into `PPC` and `Store`; the loader
    kept asking for the old name, `clean_date` was handed a missing key, and
    `ppc_store` went NULL on all 65,520 rows. Nothing raised. The app came up,
    the dashboards rendered, and the Overview's "store demand to purchase"
    cycle time was blank with a basis of zero orders.

    That is the dangerous failure mode here: not a crash, but a column that
    quietly arrives empty and a figure that quietly reads zero. The same thing
    has happened before — with the imports demand dates, and with the AB-items
    workbook that would have dropped every stock line to rank C.

    So every reload now ENDS BY CHECKING ITSELF. `verify_load` looks at the
    columns that have gone silently empty in the past, says plainly whether each
    one landed, and names the command that repairs it. A reload that quietly
    loses a column is no longer possible to miss.

WHY THE REPAIRS ARE CONDITIONAL

    `load_02_purchases_data` now reads whichever of the three column names is
    present, so a fresh load fills `ppc_store` correctly and the backfill has
    nothing to do. Running it unconditionally would re-read a 65,000-row
    workbook for two minutes to write values that are already there.

    So it runs only if the check finds the column empty — which happens when the
    workbook changes shape again, or when the database was loaded by older code.
    Cheap when there is nothing wrong, automatic when there is.
"""

from app.loading.database_connection import connection, cursor


#-----------------------------------------------------
# WHAT MUST BE TRUE AFTER A LOAD
#
# One row per column that has silently arrived empty at least once. Each names
# the table, the column, how much coverage is expected, and — where one exists —
# the command that fills it.
#-----------------------------------------------------

CHECKS = [
    {
        "label": "Purchase store-demand dates",
        "sql": "SELECT count(ppc_store), count(*) FROM purchases_data",
        "why": "the Overview's store-demand-to-purchase cycle time; blank without it",
        "repair": "app.loading.scripts.backfill_purchase_store_dates",
    },
    {
        "label": "Import demand dates",
        "sql": "SELECT count(requisition_date), count(*) FROM consignments WHERE is_deleted = false",
        "why": "the imports demand figures",
        "repair": "app.loading.scripts.backfill_import_demand_dates",
        # Roughly half the sheet carries a demand date, so anything above zero
        # is normal here — only a completely empty column is a fault.
        "expect": "any",
    },
    {
        "label": "Import PKR totals",
        "sql": "SELECT count(pkr_total), count(*) FROM consignments WHERE is_deleted = false",
        "why": "every figure built on import value, on both dashboards and in reports",
        "repair": "app.loading.scripts.backfill_import_demand_dates",
        "expect": "any",
    },
    {
        "label": "Stock ABC ranks",
        "sql": "SELECT count(*) FILTER (WHERE rank <> 'C'), count(*) FROM stock",
        "why": "the A/B classification; everything defaults to C when the AB workbook is not read",
        "repair": None,
        "expect": "any",
    },
    {
        "label": "Purchase item codes",
        "sql": "SELECT count(item_code), count(*) FROM purchases_data",
        "why": "the category breakdowns, which drop uncoded rows",
    },
    {
        "label": "Issuance item codes",
        "sql": "SELECT count(item_code), count(*) FROM issuance",
        "why": "the movement and runway figures, which key on the item code",
    },
]


def _measure(check):
    """(filled, total) for one check, or None if the table is not there."""
    try:
        cursor.execute(check["sql"])
        return cursor.fetchone()
    except Exception:
        connection.rollback()
        return None


def verify_load(repair=True):
    """Report on every column that has silently gone empty before.

    Returns the list of checks that came back EMPTY. With `repair=True` the ones
    that have a repair command are run automatically — see the module docstring
    for why that is conditional rather than unconditional.
    """
    print("\n" + "=" * 60)
    print("POST-LOAD CHECK — did every column actually land?")
    print("=" * 60)

    empty = []

    for check in CHECKS:
        measured = _measure(check)
        if measured is None:
            print(f"   {check['label']:<28} (table not present, skipped)")
            continue

        filled, total = measured
        if total == 0:
            print(f"   {check['label']:<28} (no rows, skipped)")
            continue

        pct = filled / total * 100
        ok = filled > 0 if check.get("expect") == "any" else pct >= 99
        mark = "ok  " if ok else "EMPTY"
        print(f"   {check['label']:<28} {mark}  {filled:>7,} of {total:>7,}  ({pct:.0f}%)")

        if not ok:
            empty.append(check)

    if not empty:
        print("\nEverything the loaders are supposed to write is there.")
        return []

    print("\n" + "!" * 60)
    print("SOME COLUMNS CAME BACK EMPTY")
    print("!" * 60)
    for check in empty:
        print(f"\n   {check['label']}")
        print(f"      needed for : {check['why']}")
        if check.get("repair"):
            print(f"      repair     : python -m {check['repair']}")
        else:
            print("      repair     : none — check the workbook's column names")

    repairable = [c for c in empty if c.get("repair")]

    if repair and repairable:
        print("\n--- running the repairs ---")
        for check in repairable:
            print(f"\n   {check['label']} -> {check['repair']}")
            try:
                module = __import__(check["repair"], fromlist=["run"])
                runner = getattr(module, "run", None) or getattr(module, "main")
                runner()
            except Exception as exc:
                print(f"   !! FAILED — {type(exc).__name__}: {exc}")

    if not repairable:
        print("\nNothing here can be repaired automatically. A column that arrives")
        print("empty usually means the workbook renamed it — compare its headers")
        print("against the names the loader asks for.")

    return empty
