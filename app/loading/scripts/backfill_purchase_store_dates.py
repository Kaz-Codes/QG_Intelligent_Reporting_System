"""
Backfill `purchases_data.ppc_store` — the store demand date.

WHY IT IS EMPTY
    The workbook used to carry one column called "PPC/Store". The current export
    SPLIT it in two: `PPC` (the demand date the business writes, as text) and
    `Store` (the same event as a system timestamp). The loader kept asking for
    the old combined name, which no longer exists, so `clean_date` was handed a
    missing key and returned None — on all 65,520 rows.

    Nothing failed. The column simply went NULL, and the Overview's
    "store demand to purchase" cycle time, whose only input is this column,
    rendered blank with a basis of zero orders. A silent hole, not an error:
    exactly the failure mode a loader keyed on column NAMES has.

    `load_02_purchases_data` now reads whichever of the three names is present,
    so a fresh load is correct. This script fixes a database already loaded,
    without the destructive reload that would otherwise be needed.

WHY POSITION IS SAFE HERE, AND HOW IT IS CHECKED
    The loader inserts one row per sheet row, in sheet order, so the Nth row of
    the concatenated workbook is the Nth id in the table. That is an assumption,
    and a wrong one would write every date onto the wrong purchase — so it is
    VERIFIED first, by comparing the sheet's PO number and purchase date against
    the stored row for the same position. Below 95% agreement the run aborts
    rather than writing.

USAGE
    python -m app.loading.scripts.backfill_purchase_store_dates
    python -m app.loading.scripts.backfill_purchase_store_dates --dry-run
"""

import sys
from pathlib import Path

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_date,
)
from sqlalchemy import text

DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "purchases"

# In preference order — the current export's two columns, and the old combined
# one so this still works against an older workbook.
STORE_DATE_COLUMNS = ("PPC/Store", "PPC", "Store")


def store_date(row):
    for column in STORE_DATE_COLUMNS:
        value = clean_date(row.get(column))
        if value is not None:
            return value
    return None


def run(dry_run=False):
    files = list_excel_files(DIRECTORY)
    if not files:
        print(f"no workbooks in {DIRECTORY}")
        return

    df = read_and_concat("Sheet1", files)
    present = [c for c in STORE_DATE_COLUMNS if c in df.columns]
    print(f"sheet: {len(df)} rows; store-date columns present: {present or 'NONE'}\n")

    if not present:
        print("ABORTED — the workbook carries none of the store-date columns.")
        return

    db = SessionLocal()
    try:
        stored = db.execute(text(
            "SELECT id, po_number, purchase FROM purchases_data ORDER BY id"
        )).all()

        if len(stored) != len(df):
            print(f"ABORTED — {len(stored)} stored rows against {len(df)} sheet rows.")
            print("Position cannot be trusted when the two do not line up.")
            return

        # Verify the position assumption before writing a single value.
        checked = matched = 0
        for (row_id, po, purchase), (_, row) in zip(stored, df.iterrows()):
            sheet_po = clean_text(row.get("PO Numbe"))
            sheet_purchase = clean_date(row.get("Purchase"))
            if sheet_po is None or po is None:
                continue
            checked += 1
            if str(sheet_po).strip() == str(po).strip() and sheet_purchase == purchase:
                matched += 1

        rate = (matched / checked * 100) if checked else 0
        print(f"position check: {matched}/{checked} rows agree on PO + purchase date ({rate:.1f}%)")
        if checked and rate < 95:
            print("\nABORTED — the sheet's row order no longer matches the stored ids.")
            return
        print()

        updates = [
            {"id": row_id, "value": store_date(row)}
            for (row_id, _po, _purchase), (_, row) in zip(stored, df.iterrows())
        ]
        updates = [u for u in updates if u["value"] is not None]

        print(f"{'WOULD SET' if dry_run else 'setting'} ppc_store on {len(updates)} of {len(stored)} rows")

        if not dry_run:
            db.execute(
                text("UPDATE purchases_data SET ppc_store = :value WHERE id = :id"),
                updates,
            )
            db.commit()

            filled, usable = db.execute(text("""
                SELECT count(ppc_store),
                       count(*) FILTER (WHERE ppc_store <= purchase)
                FROM purchases_data
            """)).one()
            print(f"\nresulting coverage:")
            print(f"   ppc_store filled            {filled:,}")
            print(f"   usable for cycle time       {usable:,}  (the rest sit after the purchase)")
    finally:
        db.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
