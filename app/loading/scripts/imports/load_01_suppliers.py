"""Load Suppliers master table"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, bulk_insert, clean_int
)
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "imports"

# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

# Every workbook in the folder is loaded, not just the first.
files = list_excel_files(directory)

#Order of columns matters here (must be same as order of ROWS list)
SUPPLIER_COLUMNS = ["id", "name", "country", "city", "contact_name", "phone", "email", "default_currency",  "default_payment_terms", "is_active", "is_verified"]

#--> Order must be same as columns order
SUPPLIER_HEADERS = [
    ("supplier_id", clean_int), ("Supplier", clean_text),	("Country", clean_text), ("City", clean_text), ("-", clean_text),
    ("-", clean_text), ("-", clean_text), ("-", clean_text), ("-", clean_text)
]

def load_suppliers(conn):
    df = read_and_concat("Sheet1", files)
    df = df.drop_duplicates(subset=["supplier_id"])
    supplier_rows = []

    for _, row in df.iterrows():
        supplier_id = row["supplier_id"]

        if pd.isna(supplier_id):
            continue
        
        row_tuple = ()
        for header, cleaning_function in SUPPLIER_HEADERS:
            if header != "-":
                row_value = cleaning_function(row.get(header))
                row_tuple = row_tuple + (row_value, )
            else:
                row_value = cleaning_function(header)
                row_tuple = row_tuple + (row_value, )

        row_tuple = row_tuple + (True, ) + (True, )
        supplier_rows.append(row_tuple)
    
    bulk_insert(conn, "suppliers", SUPPLIER_COLUMNS, supplier_rows)
    print(f"Suppliers : inserted {len(supplier_rows)} rows")
