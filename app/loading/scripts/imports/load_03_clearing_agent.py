"""Load Suppliers master table"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_sheet, clean_text, bulk_insert, clean_int
)
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "imports"

# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

files = list(directory.iterdir())

EXCEL_FILE = files[0]

#Order of columns matters here (must be same as order of ROWS list)
CLEARING_AGENT_COLUMNS = ["id", "name", "licence_no", "phone", "primary_port_id","is_active", "is_verified"]

#--> Order must be same as columns order
CLEARING_AGENT_HEADERS = [
    ("clearing_agent_id", clean_int), ("C/Agent", clean_text),	("-", clean_text), ("-", clean_text), ("-", clean_text),
]

def load_clearing_agent(conn):
    df = read_sheet("Sheet1", EXCEL_FILE)
    df = df.drop_duplicates(subset=["clearing_agent_id"])
    clearing_agent_rows = []

    for _, row in df.iterrows():
        clearing_agent_id = row["clearing_agent_id"]

        if pd.isna(clearing_agent_id):
            continue
        
        row_tuple = ()
        for header, cleaning_function in CLEARING_AGENT_HEADERS:
            if header != "-":
                row_value = cleaning_function(row.get(header))
                row_tuple = row_tuple + (row_value, )
            else:
                row_value = cleaning_function(header)
                row_tuple = row_tuple + (row_value, )

        row_tuple = row_tuple + (True, ) + (True, )
        clearing_agent_rows.append(row_tuple)
    
    bulk_insert(conn, "clearing_agents", CLEARING_AGENT_COLUMNS, clearing_agent_rows)
    print(f"Clearing agent : inserted {len(clearing_agent_rows)} rows")
