"""Load the Main Stocks table"""

import pandas as pd
from app.enums import ItemRank
from app.loading.scripts.etl_common import (
    read_sheet, list_excel_files, clean_text, clean_number, bulk_insert
)

from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "stocks"
# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\stocks")

EXCEL_FILES = list_excel_files(directory)

# The ABC ranking lives in its own workbook, keyed by item code + branch.
AB_DIRECTORY = CURRENT_DIR / "data" / "ab_items"
AB_FILES = list_excel_files(AB_DIRECTORY)

# The AB workbook has had two layouts, and both are read.
#
# OLD ("AB Items"): one "Main" sheet holding every branch, with a Branch Name
# column. The other ranked sheets ("Re-Order", "Critical") are filtered views OF
# Main, so reading them too would only re-state ranks Main already carries.
#
# NEW ("Combined Planning Sheet"): ONE SHEET PER BRANCH, named with the branch
# CODE, and the header on the 5th row (rows 1-4 are a title and summary block).
# There is no Branch Name column — the sheet name is the branch.
#
# Supporting both matters: the layout changed silently, and the loader's old
# behaviour on an unreadable sheet was to warn and carry on, which would have
# dropped EVERY item to rank C without failing.
AB_SHEET = "Main"
AB_NEW_HEADER_ROW = 4

# Branch code (the new workbook's sheet name) -> the branch name stock rows use.
# NOT guessed: derived by matching each sheet's item codes against each branch's
# stock rows, where every sheet covered exactly one branch's codes 100% and the
# next best was 66% or less. Note QEN is Qadri ENGINEERING while QE is QADBROS
# Engineering — the intuitive reading of those two codes is backwards.
AB_BRANCH_BY_CODE = {
    "QCL": "Qadcast (Pvt) Ltd.",
    "QBL2": "Qadri Brothers (Pvt.) Ltd. (Unit-II)",
    "QEN": "Qadri Engineering (Pvt) Ltd.",
    "QE": "Qadbros Engineering (Pvt) Ltd.",
}

#Order of columns matters here (must be same as order of ROWS list)
STOCK_COLUMNS = ["item_code", "item_name", "branch", "hold_qty", "stock_qty", "stock_qty_amount",  "available_qty", "available_amount", "rank"]

#--> Order must be same as columns order
STOCK_HEADERS = [
    ("ItemCode", clean_text), ("Item", clean_text),	("Branch", clean_text), ("Hold Qty", clean_number), ("StockQty", clean_number),	("Stock Qty Amou", clean_number), ("Available Qty", clean_number), ("Available Amoun",clean_number),
]

VALID_RANKS = {r.value for r in ItemRank}


def build_rank_map():
    """(item_code, branch) -> 'A' / 'B', from every AB workbook in the folder.

    Keyed on BOTH code and branch because the ranking is per branch: the same
    item is an A line at one branch and a B line at another (12 codes in the
    current sheet do exactly that). Keying on code alone would silently pick
    whichever row happened to come last.

    Anything not in here is a C line — see load_stock.
    """
    rank_map = {}

    for file in AB_FILES:
        name = Path(file).name
        sheets = pd.ExcelFile(file).sheet_names

        if AB_SHEET in sheets:
            _read_combined_sheet(file, rank_map, name)
        else:
            _read_per_branch_sheets(file, sheets, rank_map, name)

    return rank_map


def _record(rank_map, code, branch, rank):
    """Store one ranking, guarding the enum.

    A value outside A/B/C is IGNORED rather than stored — the new workbook
    carries stray 'Q' and 'D' ranks, and letting those through would put junk in
    a column the dashboards group by. An ignored row keeps the C default, which
    is what "not classified" means here.
    """
    if not code or not branch or not rank:
        return

    rank = rank.strip().upper()
    if rank not in VALID_RANKS:
        return

    rank_map[(code, branch)] = rank


def _read_combined_sheet(file, rank_map, name):
    """OLD layout: a single "Main" sheet carrying its own Branch Name column."""
    try:
        df = read_sheet(AB_SHEET, file)
    except Exception as exc:
        print(f"  ! AB ranks: could not read {AB_SHEET!r} from {name} — {exc}")
        return

    for _, row in df.iterrows():
        _record(
            rank_map,
            clean_text(row.get("Item Code")),
            clean_text(row.get("Branch Name")),
            clean_text(row.get("Rank")),
        )


def _read_per_branch_sheets(file, sheets, rank_map, name):
    """NEW layout: one sheet per branch, named with the branch code."""
    unknown = [s for s in sheets if s.strip().upper() not in AB_BRANCH_BY_CODE]
    if unknown:
        # Loud, because a renamed or added factory sheet would otherwise be
        # skipped in silence and its items would all read as rank C.
        print(f"  ! AB ranks: {name} has sheet(s) with no known branch: {unknown}")

    for sheet in sheets:
        branch = AB_BRANCH_BY_CODE.get(sheet.strip().upper())
        if branch is None:
            continue

        try:
            df = pd.read_excel(file, sheet_name=sheet, header=AB_NEW_HEADER_ROW)
            df.columns = [str(c).strip() for c in df.columns]
        except Exception as exc:
            print(f"  ! AB ranks: could not read {sheet!r} from {name} — {exc}")
            continue

        if "Rank" not in df.columns or "Item Code" not in df.columns:
            print(f"  ! AB ranks: {name}[{sheet}] has no Rank/Item Code column — skipped")
            continue

        for _, row in df.iterrows():
            _record(
                rank_map,
                clean_text(row.get("Item Code")),
                branch,
                clean_text(row.get("Rank")),
            )


def load_stock(conn):
    dataframes = []
    stock_rows = []

    rank_map = build_rank_map()

    for file in EXCEL_FILES:
        dataframes.append(read_sheet("Sheet1", file))

    ranked = 0

    for df in dataframes:
        for _, row in df.iterrows():
            row_tuple = ()
            for header, cleaning_function in STOCK_HEADERS:
                row_tuple = row_tuple + (cleaning_function(row.get(header)), )

            # The AB workbook only lists A and B items, so a stock line it
            # doesn't mention is a C line — the default, not a missing value.
            rank = rank_map.get(
                (clean_text(row.get("ItemCode")), clean_text(row.get("Branch"))),
                ItemRank.C.value,
            )
            if rank != ItemRank.C.value:
                ranked += 1

            stock_rows.append(row_tuple + (rank,))

    bulk_insert(conn, "stock", STOCK_COLUMNS, stock_rows)
    print(f"Stocks : inserted {len(stock_rows)} rows "
          f"({ranked} ranked A/B from {len(rank_map)} AB entries, rest default to C)")
