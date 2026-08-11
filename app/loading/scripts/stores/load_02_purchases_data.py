"""Load the Main Purchases table"""

import pandas as pd
pd.set_option("display.max_columns", None)
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_int, clean_date, bulk_insert
)
from app.loading.scripts.stores.item_registry import register_missing_items
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "purchases"

# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\purchases")

# Every workbook in the folder is loaded, not just the first.
files = list_excel_files(directory)

#Order of columns matters here (must be same as order of ROWS list)
PURCHASES_COLUMNS = [
    "ref_no", "qty", "branch", "amount", "ppc_store", "required_d", "purchase", "mop", "dc_no"  ,"bill_no", "sourcing_o", "item_code", "item_name", "specification", "supplier", "po_number", "po_date"
]

def load_purchases(conn):
    df = read_and_concat("Sheet1", files)

    # item_code is a foreign key onto `items`, and the catalogue export lags
    # behind the transactional sheets — an unknown code fails the constraint and
    # takes the whole load down. See item_registry for why the gap is filled
    # rather than the code being nulled.
    register_missing_items(
        conn, df,
        code_column="Item Code",
        name_column="Item Name",
        spec_column="Specificati",
        category_column="Item Categ",
        label="Purchases",
    )

    purchases_rows = []

    for _, row in df.iterrows():
        purchases_rows.append((
            clean_text(row.get("Ref No")),
            clean_int(row.get("Qty")),
            clean_text(row.get("Branch")),
            clean_text(row.get("Amount")),
            # The workbook SPLIT "PPC/Store" into two columns: `PPC` (the store
            # demand date, as text) and `Store` (the same event as a timestamp).
            # The loader kept asking for the old combined name, which no longer
            # exists, so ppc_store came back NULL on all 65,520 rows and the
            # Overview's "store demand to purchase" cycle time had no basis at
            # all and rendered blank. PPC is preferred because it is the date
            # the business writes; Store is the system's own stamp of it.
            clean_date(row.get("PPC/Store") or row.get("PPC") or row.get("Store")),
            clean_date(row.get("Required D")),
            clean_date(row.get("Purchase")),
            clean_text(row.get("MOP")),
            clean_text(row.get("DC No")),
            clean_text(row.get("Bill No")),
            clean_text(row.get("Sourcing O")),
            clean_text(row.get("Item Code")),
            clean_text(row.get("Item Name")),
            clean_text(row.get("Specificati")),
            clean_text(row.get("Supplier")),
            clean_text(row.get("PO Numbe")),
            clean_date(row.get("PO Date")),
        ))

    bulk_insert(conn, "purchases_data", PURCHASES_COLUMNS, purchases_rows)
    print(f"Purchases : inserted {len(purchases_rows)} rows")
