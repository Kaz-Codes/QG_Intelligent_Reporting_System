"""Load the Main Store requisitions table"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_number, clean_date, bulk_insert
)
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "store_requisitions"
# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\store_requisitions")

# Every workbook in the folder is loaded, not just the first.
files = list_excel_files(directory)

#Order of columns matters here (must be same as order of ROWS list)
STORE_REQUISITION_COLUMNS = ["item_code", "item_name", "ref_no", "department", "branch", "prepare_date", "description", "required_by",  "req_quantity", "pur_quantity", "pending_quantity", "last_purchase", "previous_price", "required_date", "status", "sourced_by", "previous_supplier", "original_required_date", "stock_in_date"]

#--> Order must be same as columns order
STORE_REQUISITION_HEADERS = [
    ("Item Code", clean_text), ("Item Name", clean_text),	("Ref #", clean_text), ("Department", clean_text), ("Branch", clean_text),	("Prepare Date", clean_date), ("Description", clean_text), ("RequiredBy",clean_text), ("Req.Quantity", clean_number), ("Pur.Quantity", clean_number), ("Pending Quantity", clean_number), ("LastPurchase", clean_date), ("PreviousPrice", clean_text), ("RequiredDate", clean_date), ("Status", clean_text), ("SourcedBy", clean_text), ("PreviousSupplier", clean_text), ("Original Required", clean_date), ("Stock In Dat", clean_date)
]

def load_store_requisitions(conn):
    df = read_and_concat("Sheet1", files)
    store_requisitions_rows = []

    for _, row in df.iterrows():
        row_tuple = ()
        for header, cleaning_function in STORE_REQUISITION_HEADERS:
            row_tuple = row_tuple + (cleaning_function(row.get(header)), )
        store_requisitions_rows.append(row_tuple)
    
    bulk_insert(conn, "store_requisition", STORE_REQUISITION_COLUMNS, store_requisitions_rows)
    print(f"Store Requisitions : inserted {len(store_requisitions_rows)} rows")
