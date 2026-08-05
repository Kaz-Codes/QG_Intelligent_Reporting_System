"""
Shared ground for the logistics loaders.

The logistics workbook keeps ONE order spread across three sheets — the
shipment sheet holds the shipping leg, the packing sheet holds the jobs and
packages, and the export-documentation sheet holds the paperwork. They are
tied together by the export number and batch number, which is why the order
identity is worked out here once rather than three times.

Why not the sheet's own 'Primary Key' column: it is a text formula
(Exp # & "-" & Batch # & "-"), so it inherits the ordinal suffixes the export
numbers are typed with — '2360th' on one sheet and '2360' on another are the
same order but never match as text. Joining on the raw column finds 88 of 163
export rows; normalising with clean_key (which strips the ordinal) finds 114,
and lifts packing from 13 matches to 139.

Ids are assigned deterministically from the sorted key list, so every loader
that calls build_order_index() gets the SAME id for the same order without
needing to read the previous loader's rows back out of the database.
"""

from pathlib import Path

import pandas as pd

from app.loading.scripts.etl_common import (
    clean_key, clean_text, read_sheet, list_excel_files,
)

CURRENT_DIR = Path(__file__).resolve().parents[2]
DIRECTORY = CURRENT_DIR / "data" / "logistics"

# Every workbook in the folder is loaded, not just the first. list_excel_files
# is sorted, so read_logistics_sheet stacks the sheets in the SAME order every
# time — which the packing sheet's position-based order ids depend on.
WORKBOOKS = list_excel_files(DIRECTORY)

# The sheets, and the column each one spells the export/batch number with.
SHEET_SHIPMENT = "Shipment Master Database"
SHEET_PACKING = "Master Packing Database"
SHEET_EXPORT_DOCS = "Export Documentation Database"
SHEET_SHIFTING = "Inbound & Outbound Shifting"

KEY_COLUMNS = {
    SHEET_SHIPMENT: ("Exp #", "B. #"),
    SHEET_PACKING: ("Exp #", "Batch #"),
    SHEET_EXPORT_DOCS: ("Exp. #", "Batch #"),
}


def order_key(exp_value, batch_value):
    """The identity of one logistics order, or None when it has no export no.

    ('2360th', '-') -> ('2360', '')   ;   (NaN, NaN) -> None
    """
    exp = clean_key(exp_value)
    if not exp:
        return None
    return (exp, clean_key(batch_value) or "")


def row_key(row, sheet_name):
    exp_col, batch_col = KEY_COLUMNS[sheet_name]
    return order_key(row.get(exp_col), row.get(batch_col))


def read_logistics_sheet(sheet_name):
    # One sheet stacked across every workbook, in the fixed WORKBOOKS order, with
    # a clean 0..N index. build_order_index() and the loaders both read through
    # here, so the packing rows they see (and the positions the local order ids
    # are keyed by) are always identical.
    frames = [read_sheet(sheet_name, workbook) for workbook in WORKBOOKS]
    return pd.concat(frames, ignore_index=True)


def build_order_index():
    """{order_key: consignment_id} plus the unkeyed packing rows.

    Returns (keyed, local) where:

      keyed  {(exp, batch): id}          orders that carry an export number
      local  {packing row index: id}     packing rows with no export number

    Roughly half the packing sheet is local sugar and cement work that never
    gets an export number. Those rows are still real orders, so each one
    becomes an order of its own — there is no key to group them by, and
    grouping them on customer alone would merge unrelated jobs into one
    shipment.
    """
    keys = set()

    for sheet in (SHEET_SHIPMENT, SHEET_PACKING, SHEET_EXPORT_DOCS):
        df = read_logistics_sheet(sheet)
        for _, row in df.iterrows():
            key = row_key(row, sheet)
            if key:
                keys.add(key)

    keyed = {key: index + 1 for index, key in enumerate(sorted(keys))}

    packing = read_logistics_sheet(SHEET_PACKING)
    local = {}
    next_id = len(keyed) + 1

    for index, row in packing.iterrows():
        if row_key(row, SHEET_PACKING) is not None:
            continue
        # A row with neither a key nor anything identifying on it is a spacer,
        # not an order.
        if not (clean_text(row.get("Customer")) or clean_text(row.get("Jobs #"))):
            continue
        local[index] = next_id
        next_id += 1

    return keyed, local


def admin_id(conn):
    """The user every loaded row is booked against.

    created_by_id is NOT NULL on all three consignment tables, so the admin
    seeded at startup has to exist before any of this runs.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "No admin user found — seed the admin before loading logistics"
        )
    return row[0]


def bump_sequence(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table}))"
        )
    conn.commit()
