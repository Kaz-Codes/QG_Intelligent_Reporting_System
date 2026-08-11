"""
Backfill `consignment_items.eta_works` — the LINE's own arrival date.

WHY THE LINE NEEDS ITS OWN DATE

    A consignment is every sheet row sharing a Payment Ref No. Those rows do NOT
    all arrive together: 19 of the 175 consignments carry lines with different
    ETAs, and one spans seven distinct dates. The loader kept only the FIRST
    line's ETA on the header, so every period figure dated the whole consignment
    by it.

    Payment ref 65704 is the worked example: seven shaft lines worth Rs 10.64m,
    of which three (Rs 8.98m) land on 6 August and four (Rs 1.66m) landed on
    27 July. Filtered to August it reported the full Rs 10.64m — money credited
    to a month it did not arrive in, and a reference list that could not show
    why because the lines were invisible.

    `load_05_consignments` now stores the per-row ETA. This fills it in on a
    database already loaded, without the destructive reload.

HOW THE ROWS ARE MATCHED

    NOT by position. The loader writes one item row per sheet row, in order,
    within each consignment group — but a group's rows are only ordered
    relative to each other, so a global position map is fragile. Instead each
    consignment's lines are matched to its sheet rows by
    (item_code, quantity, unit_price), which is what actually identifies a line,
    and only rows that match exactly once are written. Anything ambiguous is
    counted and reported rather than guessed at: a wrong date here would move
    money between months, which is precisely the bug being fixed.

USAGE
    python -m app.loading.scripts.backfill_line_eta_works
    python -m app.loading.scripts.backfill_line_eta_works --dry-run
"""

import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.loading.scripts.imports.item_codes import assign_item_codes
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_date, clean_number,
)
from sqlalchemy import text

DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "imports"


def _key(item_code, quantity, unit_price):
    """What identifies a line within its consignment.

    Quantities and prices are compared as Decimals quantized to the precision
    the columns actually store (3 and 4 places), so 6.264 from the sheet matches
    6.264000 from the database.

    ROUND_HALF_UP, not Python's default. Postgres rounds 1.2945 to 1.295 storing
    it in Numeric(14,3); Python's banker's rounding gives 1.294, and that one
    digit was enough to leave the line unmatched and its ETA NULL — which is how
    a July shaft line kept being counted as August money.
    """
    def number(value, places):
        if value is None:
            return None
        try:
            return Decimal(str(value)).quantize(
                Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, ValueError):
            return None

    return (
        (clean_text(item_code) or "").strip().lower(),
        number(quantity, 3),
        number(unit_price, 4),
    )


def run(dry_run=False):
    files = list_excel_files(DIRECTORY)
    if not files:
        print(f"no workbooks in {DIRECTORY}")
        return

    df = read_and_concat("Sheet1", files)

    db = SessionLocal()
    try:
        # The same Item Code assignment the loader applies before grouping —
        # without it the sheet's uncoded rows key differently from the stored
        # ones and nothing matches.
        assign_item_codes(df, db.connection().connection)

        # sheet: payment ref -> [(key, eta), ...]
        by_ref = defaultdict(list)
        for _, row in df.iterrows():
            ref = clean_text(row.get("Payment Ref No"))
            if ref is None:
                continue
            eta = clean_date(row.get("ETA Works"))
            if eta is None:
                continue
            by_ref[str(ref).strip()].append((
                _key(row.get("Item Code"), clean_number(row.get("Qty.")),
                     clean_number(row.get("Unit Price"))),
                eta,
            ))

        stored = db.execute(text("""
            SELECT i.id, c.instrument_number, i.item_code, i.quantity, i.unit_price
            FROM consignment_items i
            JOIN consignments c ON c.id = i.consignment_id
            WHERE i.is_deleted = false AND c.is_deleted = false
        """)).all()

        # database: payment ref -> {key: [line ids]}
        db_by_ref = defaultdict(lambda: defaultdict(list))
        for line_id, ref, item_code, quantity, unit_price in stored:
            if ref is None:
                continue
            db_by_ref[str(ref).strip()][_key(item_code, quantity, unit_price)].append(line_id)

        updates, ambiguous, unmatched = [], 0, 0

        for ref, sheet_lines in by_ref.items():
            candidates = db_by_ref.get(ref)
            if not candidates:
                continue

            # Group the sheet's rows by key too, so a key appearing twice on
            # both sides with ONE eta is still safe to apply.
            sheet_by_key = defaultdict(set)
            for key, eta in sheet_lines:
                sheet_by_key[key].add(eta)

            for key, line_ids in candidates.items():
                etas = sheet_by_key.get(key)
                if not etas:
                    unmatched += len(line_ids)
                    continue
                if len(etas) > 1:
                    # The same item at the same price and quantity, arriving on
                    # two dates — nothing distinguishes which line is which.
                    ambiguous += len(line_ids)
                    continue
                eta = next(iter(etas))
                for line_id in line_ids:
                    updates.append({"id": line_id, "eta": eta})

        print(f"sheet rows with an ETA : {sum(len(v) for v in by_ref.values()):,}")
        print(f"stored lines           : {len(stored):,}")
        print(f"matched unambiguously  : {len(updates):,}")
        print(f"ambiguous (left NULL)  : {ambiguous:,}")
        print(f"no sheet match         : {unmatched:,}")

        if not dry_run and updates:
            db.execute(
                text("UPDATE consignment_items SET eta_works = :eta WHERE id = :id"),
                updates,
            )
            db.commit()

            filled, total, differing = db.execute(text("""
                SELECT count(i.eta_works), count(*),
                       count(*) FILTER (WHERE i.eta_works IS DISTINCT FROM c.eta_works
                                          AND i.eta_works IS NOT NULL)
                FROM consignment_items i
                JOIN consignments c ON c.id = i.consignment_id
                WHERE i.is_deleted = false AND c.is_deleted = false
            """)).one()
            print(f"\nresulting coverage:")
            print(f"   lines with their own ETA        {filled:,} of {total:,}")
            print(f"   lines whose ETA differs from    {differing:,}")
            print(f"   their consignment header        <- these were being mis-dated")
        elif dry_run:
            print("\n--dry-run given, nothing was written.")
    finally:
        db.close()


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
