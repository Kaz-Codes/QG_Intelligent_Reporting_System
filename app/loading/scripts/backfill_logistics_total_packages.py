"""
Backfill `logistics_consignments.total_packages` on a database already loaded.

WHY THIS EXISTS

    total_packages is a new column (Alembic ec9e445ae48c) — every order loaded
    before it existed has it NULL. load_01_logistics.py now fills it in on a
    FRESH load (summing the packing sheet's "Pkgs." column per order — see its
    own module docstring), but that loader is retired from the normal pipeline:
    the app is the system of record for logistics now, and load_all.py is
    explicitly forbidden from touching logistics_consignments at all (see its
    docstring). Re-running the loader against an existing database is not an
    option — it would re-derive its own ids from the sheet and either collide
    with or duplicate real, operator-entered orders. This script instead
    UPDATEs the total_packages column in place, on rows that already exist.

WHERE THE NUMBER COMES FROM

    Master Packing Database's "Pkgs." column, summed per order — exactly the
    same source and the same rule load_01_logistics.py now uses for a fresh
    load (packing sheet only; the shipment sheet also has a "Pkgs." column but
    the two disagree on some orders, and packing is the more authoritative
    count of what was actually packed).

HOW ORDERS ARE MATCHED — NOT BY POSITION

    A logistics order created through the app has no reproducible position in
    the workbook (it wasn't loaded from a row at all, or it was created since
    the last load and the sheet has moved on). The one thing an order carries
    that the sheet also carries is its (mo_no, batch_label) pair: the ORIGINAL
    loader wrote mo_no as the sheet's own export number and batch_label as its
    batch number, BOTH already run through clean_key() (uppercased, ordinal
    suffix stripped) — see logistics_common.order_key/row_key. So matching here
    re-derives that same normalised key from the sheet and compares it against
    each order's stored (mo_no, batch_label), rather than trusting position.

    Orders with no mo_no at all (the loader's "local" sugar/cement jobs, which
    have no export number and were matched purely by their position in that
    ONE original load — see build_order_index) are NOT touched here: there is
    no natural key for them in the sheet, and guessing by position again would
    be exactly the fragile assumption backfill_line_eta_works's own docstring
    warns against once the app owns the data.

WHAT IS NEVER OVERWRITTEN

    Only rows with total_packages IS NULL are considered, and the UPDATE
    repeats that guard — an operator who has since typed in a real figure
    (or corrected the sheet's) is never silently replaced by this script.

USAGE
    python -m app.loading.scripts.backfill_logistics_total_packages
    python -m app.loading.scripts.backfill_logistics_total_packages --dry-run
"""

import sys
from collections import defaultdict

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.loading.scripts.etl_common import clean_int, clean_key
from app.loading.scripts.logistics.logistics_common import (
    SHEET_PACKING, read_logistics_sheet, row_key,
)
from sqlalchemy import text


def _sheet_totals():
    """{(mo, batch): summed Pkgs.} across every packing-sheet row that has an
    export number — un-keyed (local) rows are skipped, they have nothing an
    existing order could be matched against."""
    packing = read_logistics_sheet(SHEET_PACKING)

    totals = defaultdict(int)
    seen = defaultdict(bool)
    for _, row in packing.iterrows():
        key = row_key(row, SHEET_PACKING)
        if key is None:
            continue
        pkgs = clean_int(row.get("Pkgs."))
        if pkgs is None:
            continue
        totals[key] += pkgs
        seen[key] = True

    # dict(totals) with only keys that actually saw a real Pkgs. value —
    # defaultdict would otherwise report 0 (a real, misleading total) for a
    # key that was only ever touched by the `if pkgs is None: continue` guard.
    return {k: v for k, v in totals.items() if seen[k]}


def run(dry_run=False):
    sheet_totals = _sheet_totals()
    if not sheet_totals:
        print("no packing-sheet workbooks found (or none have a Pkgs. column) — nothing to do")
        return

    db = SessionLocal()
    try:
        candidates = db.execute(text("""
            SELECT id, mo_no, batch_label
            FROM logistics_consignments
            WHERE is_deleted = false
              AND total_packages IS NULL
              AND mo_no IS NOT NULL
        """)).all()

        updates = []
        no_sheet_match = 0

        for order_id, mo_no, batch_label in candidates:
            key = (clean_key(mo_no), clean_key(batch_label) or "")
            if key[0] is None:
                continue
            total = sheet_totals.get(key)
            if total is None:
                no_sheet_match += 1
                continue
            updates.append({"id": order_id, "total_packages": total})

        print(f"orders eligible (no total_packages, has an mo_no) : {len(candidates):,}")
        print(f"matched a packing-sheet order                     : {len(updates):,}")
        print(f"no matching (mo_no, batch) on the packing sheet   : {no_sheet_match:,}")

        if not dry_run and updates:
            db.execute(
                text("""
                    UPDATE logistics_consignments
                    SET total_packages = :total_packages
                    WHERE id = :id AND total_packages IS NULL
                """),
                updates,
            )
            db.commit()

            filled, total = db.execute(text("""
                SELECT count(total_packages), count(*)
                FROM logistics_consignments
                WHERE is_deleted = false
            """)).one()
            print(f"\nresulting coverage:")
            print(f"   orders with total_packages set   {filled:,} of {total:,}")
        elif dry_run:
            print("\n--dry-run given, nothing was written.")
    finally:
        db.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
