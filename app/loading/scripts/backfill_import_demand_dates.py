"""
Backfill the imports columns the loader never mapped.

The sheet has always carried these; `load_05_consignments` simply did not read
them, which is why the Imports KPIs (spend, demands, supplier Pareto) had
nothing to compute from:

    Demand Dt.        -> requisition_date   (~51% of consignments)
    Req. Dt.          -> required_date      (~100%)
    Total Value(PKR)  -> pkr_total          (~98%)
    Total Value(FC)   -> foreign_total      (~97%)
    S/Terms           -> incoterm           (~95%)  -- OPT-IN, see below

Deliberately NOT loaded: `Lead Time` and `Actual Lead Time`.

WHY A BACKFILL AND NOT A RELOAD. `load_all` is destructive — it drops and
refills every transaction table, taking anything entered through the app with
it. This only fills columns that are currently empty, so it is safe on a live
database and can be re-run.

WHY THE SHEET'S OWN TOTALS. `pkr_total` / `foreign_total` are normally computed
by helpers.recompute_derived on save. Loaded rows never went through that, and
the workbook already carries the figures finance actually used — so those are
taken verbatim rather than reconstructed from qty x price x rate, which would
disagree with the printed reports (see rule 4 in CLAUDE.md: never restate a
booked figure at a different rate).

INCOTERM IS OPT-IN (`--incoterm`). It is the one column here that changes
BEHAVIOUR rather than just adding numbers: `incoterm == 'FOB'` is what makes a
consignment eligible to be sent to Logistics/Trucking, so loading it turns ~46
historical consignments into sendable work. Values are messy in the sheet
("FOB SHANGHAI", "FOB-LCL", "CFR KARACHI"), so they are normalised onto the
leading Incoterm token and anything unrecognised is skipped rather than stored
raw.

Run with:
    python -m app.loading.scripts.backfill_import_demand_dates
    python -m app.loading.scripts.backfill_import_demand_dates --incoterm
    python -m app.loading.scripts.backfill_import_demand_dates --dry-run
"""

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.enums import Incoterm
from app.loading.scripts.imports.item_codes import assign_item_codes
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_date,
)
from sqlalchemy import text

CURRENT_DIR = Path(__file__).resolve().parents[1]
DIRECTORY = CURRENT_DIR / "data" / "imports"

VALID_INCOTERMS = [i.value for i in Incoterm]


def clean_money(value):
    """Sheet money -> Decimal. Handles thousands separators and stray text;
    returns None rather than raising, so one bad cell can't sink the run."""
    text_value = clean_text(value)
    if text_value is None:
        return None
    cleaned = str(text_value).replace(",", "").replace("Rs", "").strip()
    try:
        number = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    # A zero total is indistinguishable from "not recorded" here, and writing
    # 0 over NULL would make an unknown look like a real figure.
    return number if number != 0 else None


def map_incoterm(value):
    """'FOB SHANGHAI' / 'FOB-LCL' / 'CFR KARACHI' -> the canonical enum value.

    Matches the LONGEST canonical term that the cell starts with, so 'CFR' is
    not mistaken for 'CFR - FCL' handling and 'FOB' is found inside 'FOB-LCL'.
    Anything unrecognised returns None and is skipped — the same
    default-rather-than-store-junk rule the logistics loader uses for statuses.
    """
    raw = clean_text(value)
    if raw is None:
        return None
    token = str(raw).upper().replace("-", " ").replace("/", " ").strip()
    for term in sorted(VALID_INCOTERMS, key=len, reverse=True):
        if token == term or token.startswith(term + " "):
            return term
    return None


def group_sheet_rows(df):
    """Reproduce load_05_consignments._group exactly: rows sharing a Payment
    Ref No are ONE consignment; a row without one stands alone; rows with no
    Item Code are skipped. Returns the groups in the loader's own order, which
    is what makes position -> id recoverable.

    IMPORTANT: the loader now FILLS IN the missing Item Codes before it groups
    (see imports/item_codes.py), so this must too. Grouping the raw sheet would
    skip the 294 uncoded rows, produce a different set of groups in a different
    order, and map every value onto the wrong consignment. The caller assigns
    the codes first; the skip below then only drops rows with no item name at
    all, exactly as the loader does.
    """
    order, by_ref, singleton = [], {}, 0

    for _, row in df.iterrows():
        if not clean_text(row.get("Item Code")):
            continue
        ref = clean_text(row.get("Payment Ref No"))
        if ref is None:
            key = ("noref", singleton)
            singleton += 1
            by_ref[key] = [row]
            order.append(key)
        else:
            key = ("ref", ref)
            if key not in by_ref:
                by_ref[key] = []
                order.append(key)
            by_ref[key].append(row)

    return [by_ref[k] for k in order]


def first_value(rows, column, cleaner):
    """The first non-null value across a consignment's rows.

    Right for a HEADER attribute — every row of a group repeats the same
    demand date, required date and incoterm, so the first one is the value.
    """
    for row in rows:
        value = cleaner(row.get(column))
        if value is not None:
            return value
    return None


def summed_value(rows, column, cleaner):
    """The SUM across a consignment's rows.

    Right for a MONEY column, and the distinction matters: the sheet is one row
    per item line, and "Total Value(PKR)" is that LINE's value, not the
    consignment's. Taking the first row's figure — which is what this used to do
    — silently stored one line's money as the whole import.

    It went unnoticed because it is invisible on a single-line consignment: 80
    of 80 of those matched, while 0 of 67 multi-line ones did, understating them
    by everything after the first line.

    ONE EXCEPTION. In 5 of the 72 multi-row groups the identical figure is
    repeated on every line — a header value copied down rather than a per-line
    one. Summing those multiplies the consignment by its line count (ref 2582
    became 37.5m instead of 18.75m). So when every line of a group reports
    exactly the same number, it is taken ONCE.

    That is a heuristic, and it is wrong if two lines genuinely cost the same to
    the paisa. Across a whole multi-line import that is vanishingly unlikely,
    and being out by one line beats being out by a factor of the line count.

    Returns None when no row carries a value, so "nothing to say" stays distinct
    from a genuine zero.
    """
    values = [cleaner(row.get(column)) for row in rows]
    values = [v for v in values if v is not None]

    if not values:
        return None

    if len(values) > 1 and len(set(values)) == 1:
        return values[0]

    return sum(values[1:], values[0])


def run(with_incoterm=False, dry_run=False, recompute_totals=False):
    files = list_excel_files(DIRECTORY)
    if not files:
        print(f"no workbooks in {DIRECTORY}")
        return

    df = read_and_concat("Sheet1", files)

    db = SessionLocal()
    try:
        # Fill the missing Item Codes exactly as the loader does, BEFORE
        # grouping — otherwise the uncoded rows are skipped here but not there,
        # and the groups (and therefore the id mapping) diverge. The alignment
        # check below catches that, but aligning properly is the point.
        assign_item_codes(df, db.connection().connection)

        groups = group_sheet_rows(df)
        print(f"sheet: {len(df)} rows -> {len(groups)} consignment groups\n")

        # The loader gave group N the id N+1. Rather than trust that blindly,
        # verify it against the stored instrument_number (Payment Ref No) —
        # a silent off-by-one here would write every value onto the wrong
        # consignment, which is far worse than not running at all.
        stored = {
            cid: instrument for cid, instrument in db.execute(text(
                "SELECT id, instrument_number FROM consignments WHERE is_deleted = false"
            )).all()
        }

        checked = matched = 0
        for index, rows in enumerate(groups):
            cid = index + 1
            if cid not in stored:
                continue
            sheet_ref = first_value(rows, "Payment Ref No", clean_text)
            if sheet_ref is None or stored[cid] is None:
                continue
            checked += 1
            if str(sheet_ref).strip() == str(stored[cid]).strip():
                matched += 1

        rate = (matched / checked * 100) if checked else 0
        print(f"id alignment check: {matched}/{checked} groups match on Payment Ref No ({rate:.0f}%)")
        if checked and rate < 95:
            print("\nABORTED — the sheet's row order no longer matches the loaded ids.")
            print("Writing now would put values on the wrong consignments.")
            return
        print()

        filled = {c: 0 for c in
                  ("requisition_date", "required_date", "pkr_total", "foreign_total", "incoterm")}
        skipped_incoterm = set()
        touched = 0

        for index, rows in enumerate(groups):
            cid = index + 1
            if cid not in stored:
                continue

            updates = {
                "requisition_date": first_value(rows, "Demand Dt.", clean_date),
                "required_date": first_value(rows, "Req. Dt.", clean_date),
                # SUMMED, not first: these are per-LINE figures in the sheet.
                "pkr_total": summed_value(rows, "Total Value(PKR)", clean_money),
                "foreign_total": summed_value(rows, "Total Value(FC)", clean_money),
            }

            if with_incoterm:
                raw = first_value(rows, "S/Terms", clean_text)
                mapped = map_incoterm(raw)
                if raw is not None and mapped is None:
                    skipped_incoterm.add(str(raw).strip())
                updates["incoterm"] = mapped

            # COALESCE semantics: only ever fill an empty column. Anything a
            # user has since entered through the app wins over the sheet.
            # The money columns can be REPLACED rather than filled, because a
            # value written by the old first-row logic is wrong rather than
            # merely present — COALESCE would leave every multi-line
            # consignment understated for ever. Off by default so a normal run
            # still never overwrites what a user typed.
            overwrite = {"pkr_total", "foreign_total"} if recompute_totals else set()

            sets, params = [], {"id": cid}
            for column, value in updates.items():
                if value is None:
                    continue
                if column in overwrite:
                    sets.append(f"{column} = :{column}")
                else:
                    sets.append(f"{column} = COALESCE({column}, :{column})")
                params[column] = value
                filled[column] += 1

            if not sets:
                continue
            touched += 1
            if not dry_run:
                db.execute(text(
                    f"UPDATE consignments SET {', '.join(sets)} WHERE id = :id"
                ), params)

        if not dry_run:
            db.commit()

        print(f"{'WOULD UPDATE' if dry_run else 'updated'} {touched} consignments")
        for column, n in filled.items():
            if column == "incoterm" and not with_incoterm:
                print(f"   {column:<18} skipped (pass --incoterm to include)")
            else:
                print(f"   {column:<18} value available for {n}")

        if skipped_incoterm:
            print(f"\n   unmapped S/Terms values (left NULL): {sorted(skipped_incoterm)[:10]}")

        if not dry_run:
            print("\nresulting coverage:")
            row = db.execute(text("""
                SELECT count(*),
                       count(requisition_date), count(required_date),
                       count(pkr_total), count(foreign_total),
                       count(*) FILTER (WHERE incoterm = 'FOB')
                FROM consignments WHERE is_deleted = false
            """)).fetchone()
            print(f"   consignments      {row[0]}")
            print(f"   requisition_date  {row[1]}")
            print(f"   required_date     {row[2]}")
            print(f"   pkr_total         {row[3]}")
            print(f"   foreign_total     {row[4]}")
            print(f"   incoterm = FOB    {row[5]}  <- these become sendable to Logistics/Trucking")
    finally:
        db.close()


if __name__ == "__main__":
    run(
        with_incoterm="--incoterm" in sys.argv,
        dry_run="--dry-run" in sys.argv,
        # --recompute-totals REPLACES pkr_total / foreign_total instead of only
        # filling empties. Needed once, to correct consignments stored by the
        # earlier first-row logic; harmless afterwards.
        recompute_totals="--recompute-totals" in sys.argv,
    )
