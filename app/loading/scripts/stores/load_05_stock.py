"""Load the Main Stocks table"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_sheet, clean_text, clean_number, bulk_insert
)

from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "stocks"
# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\stocks")

files = list(directory.iterdir())

EXCEL_FILES = files

#Order of columns matters here (must be same as order of ROWS list)
STOCK_COLUMNS = ["item_code", "item_name", "branch", "hold_qty", "stock_qty", "stock_qty_amount",  "available_qty", "available_amount"]

#--> Order must be same as columns order
STOCK_HEADERS = [
    ("ItemCode", clean_text), ("Item", clean_text),	("Branch", clean_text), ("Hold Qty", clean_number), ("StockQty", clean_number),	("Stock Qty Amou", clean_number), ("Available Qty", clean_number), ("Available Amoun",clean_number),
]

def load_stock(conn):
    dataframes = []
    stock_rows = []
    
    for file in EXCEL_FILES:
        dataframes.append(read_sheet("Sheet1", file))

    for df in dataframes:
        for _, row in df.iterrows():
            row_tuple = ()
            for header, cleaning_function in STOCK_HEADERS:
                row_tuple = row_tuple + (cleaning_function(row.get(header)), )
            stock_rows.append(row_tuple)
    
    bulk_insert(conn, "stock", STOCK_COLUMNS, stock_rows)
    print(f"Stocks : inserted {len(stock_rows)} rows")
