"""Load the Main Issuances table"""

import pandas as pd
pd.set_option("display.max_columns", None)
from app.loading.scripts.etl_common import (
    read_sheet, list_excel_files, clean_text, clean_int, clean_date, clean_number, bulk_insert
)

from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "issuances"

# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\issuances")

EXCEL_FILES = list_excel_files(directory)

#Order of columns matters here (must be same as order of ROWS list)
ISSUANCE_COLUMNS = ["issuance_code", "item_code", "item_name", "Specification", "department", "branch", "issue_to_others",  "authorized_by", "issued_by", "received_by", "description", "ref_no", "demand_ref_no",       "quantity", "status", "from_date", "unit_price", "total_price", "job_number"]

#--> Order must be same as columns order
ISSUANCE_HEADERS = [
    ("IssuanceCode", clean_text),	("ItemCode", clean_text), ("Item", clean_text),("Specification", clean_text),("Department", clean_text), ("Branch", clean_text),	("IssueToOthers", clean_text), ("AuthorizedBy", clean_text), ("IssuedBy",clean_text),	("ReceivedBy", clean_text), ("Description", clean_text), ("RefNo", clean_text), ("Demand RefN", clean_text), ("Quantity", clean_int), ("Status", clean_text), ("FromDate", clean_date),	("UnitPrice", clean_number), ("TotalPric",clean_number), ("JobNumber", clean_text)
]

def load_issuances(conn):
    dataframes = []
    issuances_rows = []

    for file in EXCEL_FILES:
        dataframes.append(read_sheet("Sheet1", file))

    df = pd.concat(dataframes, ignore_index=True)
    df = df.drop_duplicates(keep="first")

    for _, row in df.iterrows():
        row_tuple = ()
        for header, cleaning_function in ISSUANCE_HEADERS:
            row_tuple = row_tuple + (cleaning_function(row.get(header)), )
        issuances_rows.append(row_tuple)
    
    bulk_insert(conn, "issuance", ISSUANCE_COLUMNS, issuances_rows)
    print(f"Issuances : inserted {len(issuances_rows)} rows")
