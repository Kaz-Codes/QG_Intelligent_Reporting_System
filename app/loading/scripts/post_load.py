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
        "label": "Import per-line ETAs",
        "sql": ("SELECT count(eta_works), count(*) FROM consignment_items "
                "WHERE is_deleted = false"),
        "why": ("dating import money by the LINE rather than by its consignment "
                "header — 46 lines arrive in a different month from their header"),
        "repair": "app.loading.scripts.backfill_line_eta_works",
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
        "label": "Logistics customer links",
        "sql": "SELECT count(customer_id), count(*) FROM logistics_consignments",
        "why": ("the Customer master, which is seeded FROM these orders; a "
                "reload drops them and they must be rebuilt in the same run"),
        "repair": "app.loading.scripts.add_customer_master",
    },
    {
        "label": "Logistics export numbers",
        "sql": ("SELECT count(*) FILTER (WHERE batch_no IS NOT NULL), count(*) "
                "FROM logistics_consignments"),
        "why": ("the export/batch row key that merges the shipment, packing and "
                "documentation sheets — the workbook has renamed it before"),
        "repair": None,
        "expect": "any",
    },
    {
        "label": "Trucking movement types",
        "sql": ("SELECT count(movement_type), count(*) FROM trucking_consignments "
                "WHERE is_deleted = false"),
        "why": "the movement split; unclassified jobs fall into their own bucket",
        "repair": None,
        "expect": "any",
    },
    {
        "label": "Intra-factory movements",
        "sql": ("SELECT count(*) FILTER (WHERE movement_type = 'Intrafactory'), "
                "count(*) FROM trucking_consignments WHERE is_deleted = false"),
        "why": ("the Intra Factory Shifting sheet — a SEPARATE sheet that went "
                "unread entirely for a long time, hiding 875 jobs"),
        "repair": None,
        "expect": "any",
    },
    {
        "label": "Trucking shifting types",
        "sql": ("SELECT count(shifting_type), count(*) FROM trucking_consignments "
                "WHERE movement_type = 'Intrafactory' AND is_deleted = false"),
        "why": "Regular / Special / Others on intra-factory moves",
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


#-----------------------------------------------------
# A COLUMN CAN BE FULL AND STILL BE WRONG
#
# The coverage checks above catch an EMPTY column. They did not catch the
# packing sheet writing bare Excel day-serials, because `pd.to_datetime` read
# 46239 as nanoseconds and produced 1970-01-01 — 570 packing dates, all
# populated, all the Unix epoch, and every packing figure silently describing a
# period 56 years before the business existed.
#
# So dates are also checked for PLAUSIBILITY. Anything at or before 1971 is the
# epoch leaking through, which never means what it says.
#-----------------------------------------------------

DATE_SANITY = [
    ("logistics_packages", "packing_date"),
    ("logistics_packages", "packing_ready_date"),
    ("logistics_consignments", "etd_sailing_date"),
    ("logistics_consignments", "actual_arrival_date"),
    ("logistics_consignments", "gate_out_date"),
    ("trucking_consignments", "execution_date"),
    ("trucking_consignments", "eta_works"),
    ("consignments", "eta_works"),
    ("consignment_items", "eta_works"),
    ("purchases_data", "po_date"),
    ("purchases_data", "purchase"),
    ("issuance", "from_date"),
]


def verify_dates():
    """Report any date column whose values fall in the Excel-epoch trap."""
    print()
    print("=" * 60)
    print("DATE PLAUSIBILITY — is any column secretly the Unix epoch?")
    print("=" * 60)

    bad = []
    for table, column in DATE_SANITY:
        try:
            cursor.execute(
                f"SELECT count(*) FILTER (WHERE {column} <= DATE '1971-01-01'), "
                f"count({column}) FROM {table}"
            )
            epoch, filled = cursor.fetchone()
        except Exception:
            connection.rollback()
            continue

        if not filled:
            continue
        if epoch:
            bad.append((table, column, epoch, filled))
            print(f"   {table}.{column:<24} EPOCH  {epoch:>6,} of {filled:>7,}")

    if not bad:
        print("   every date column holds plausible dates.")
        return []

    print()
    print("!" * 60)
    print("DATES READ AS THE EPOCH — the workbook is storing Excel day-serials")
    print("!" * 60)
    print("   Use clean_date_any (not clean_date) on those columns: it decodes")
    print("   a bare serial, where pd.to_datetime reads it as nanoseconds.")
    return bad


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
