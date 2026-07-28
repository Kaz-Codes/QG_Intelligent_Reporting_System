"""Load the Main Items table"""

from loading.scripts.etl_common import (
    read_sheet, clean_text, bulk_insert
)

from pathlib import Path
directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\loading\data\items")

files = list(directory.iterdir())

EXCEL_FILES = files

#Order of columns matters here (must be same as order of ROWS list)
ITEM_COLUMNS = ["item_code", "name", "default_specification", "default_unit_of_measurement", "category"]

#--> Order must be same as columns order
ITEM_HEADERS = [
    ("ItemCode", clean_text),	("Item", clean_text), ("Specification", clean_text), ("Unit", clean_text),	("Item Sub Group", clean_text)
]

def load_items(conn):
    dataframes = []
    item_rows = []
    
    for file in EXCEL_FILES:
        dataframes.append(read_sheet("Sheet1", file))

    for df in dataframes:
        for _, row in df.iterrows():
            row_tuple = ()
            for header, cleaning_function in ITEM_HEADERS:
                row_tuple = row_tuple + (cleaning_function(row.get(header)), )
            item_rows.append(row_tuple)
    
    bulk_insert(conn, "items", ITEM_COLUMNS, item_rows)
    print(f"Items : inserted {len(item_rows)} rows")
