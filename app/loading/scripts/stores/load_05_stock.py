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

# "Main" is the full ranked list. The workbook's other ranked sheets
# ("Re-Order", "Critical") are filtered views OF Main, so reading them too
# would only re-state ranks Main already carries.
AB_SHEET = "Main"

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
        try:
            df = read_sheet(AB_SHEET, file)
        except Exception as exc:
            # A workbook without the expected sheet shouldn't sink the stock
            # load; every row simply falls back to C.
            print(f"  ! AB ranks: could not read {AB_SHEET!r} from {Path(file).name} — {exc}")
            continue

        for _, row in df.iterrows():
            code = clean_text(row.get("Item Code"))
            branch = clean_text(row.get("Branch Name"))
            rank = clean_text(row.get("Rank"))

            if not code or not branch or not rank:
                continue

            rank = rank.strip().upper()
            # Guard the enum: an unexpected value in the sheet becomes C
            # rather than landing a junk rank in the column.
            if rank not in VALID_RANKS:
                continue

            rank_map[(code, branch)] = rank

    return rank_map


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
