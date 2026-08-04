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
BRANCH_COLUMNS = ["id", "name", "code", "city", "address","is_active", "is_verified"]

#--> Order must be same as columns order
BRANCH_HEADERS = [
    ("works_id", clean_int), ("Works", clean_text),	("-", clean_text), ("-", clean_text), ("-", clean_text)
]

def load_branches(conn):
    df = read_and_concat("Sheet1", files)
    df = df.drop_duplicates(subset=["works_id"])
    branch_rows = []

    for _, row in df.iterrows():
        branch_id = row["works_id"]

        if pd.isna(branch_id):
            continue
        
        row_tuple = ()
        for header, cleaning_function in BRANCH_HEADERS:
            if header != "-":
                row_value = cleaning_function(row.get(header))
                row_tuple = row_tuple + (row_value, )
            else:
                row_value = cleaning_function(header)
                row_tuple = row_tuple + (row_value, )

        row_tuple = row_tuple + (True, ) + (True, )
        branch_rows.append(row_tuple)
    
    bulk_insert(conn, "branches", BRANCH_COLUMNS, branch_rows)
    print(f"Branches : inserted {len(branch_rows)} rows")
