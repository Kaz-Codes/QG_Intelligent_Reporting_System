"""Load the items table which is the master table that 
   is being referanced from almost all other store and
   imports related tables. Some items are also loaded from 
   purchases that are not in item database"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_sheet, clean_text, bulk_insert
)

from pathlib import Path

folders = ["items_database", "purchases", "stocks", "store_requisitions"]
file_names = {}
for folder in folders:
    CURRENT_DIR = Path(__file__).resolve().parents[2]
    directory = CURRENT_DIR / "data" / folder

    # directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data") /folder
    
    files = list(directory.iterdir())

    if folder == "items_database":
        file_names["items_database"] = files
    
    if folder == "purchases":
        file_names["purchases"] = files
    
    if folder == "stocks":
        file_names["stocks"] = files
    
    if folder == "store_requisitions":
        file_names["store_requisitions"] = files[0]


#Order of columns matters here (must be same as order of columns in sheet)
ITEMS_COLUMNS = ["item_code", "name", "default_specification", "default_unit_of_measurement", "category", "is_active", "is_verified"]

def load_items(conn):
    df_list = [read_sheet("Sheet1", file) for file in file_names["items_database"]]
    df = pd.concat(df_list, ignore_index=True)

    purchases_df_list = [read_sheet("Sheet1", file) for file in file_names["purchases"]]
    purchases_df = pd.concat(purchases_df_list, ignore_index=True)

    stock_df_list = [read_sheet("Sheet1", file) for file in file_names["stocks"]]
    stock_df = pd.concat(stock_df_list, ignore_index=True)

    store_req_df = read_sheet("Sheet1", file_names["store_requisitions"])

    item_codes_history = []
    items_rows = []

    with conn.cursor() as cur:
            cur.execute(
                "SELECT item_code from items" #--> getting already existing item codes
            )
            item_codes_history = [row[0] for row in cur.fetchall()]

    for _, row in df.iterrows():
        if clean_text(row.get("ItemCode")) not in item_codes_history:
            item_codes_history.append(clean_text(row.get("ItemCode")))
            items_rows.append((
                clean_text(row.get("ItemCode")),
                clean_text(row.get("Item")),
                clean_text(row.get("Specification")),
                clean_text(row.get("Unit")),
                clean_text(row.get("Item Sub Group")),
                True,
                True
            ))
    
    for _, row in purchases_df.iterrows():
        if clean_text(row.get("Item Code")) not in item_codes_history:
            item_codes_history.append(clean_text(row.get("Item Code")))
            items_rows.append((
                clean_text(row.get("Item Code")),
                clean_text(row.get("Item Name")),
                clean_text(row.get("Specificati")), #-->
                clean_text(row.get("UOM")), 
                clean_text(row.get("Item Category")),  
                True,
                True
            ))
    
    for _, row in stock_df.iterrows():
        if clean_text(row.get("ItemCode")) not in item_codes_history:
            item_codes_history.append(clean_text(row.get("ItemCode")))
            items_rows.append((
                clean_text(row.get("ItemCode")),
                clean_text(row.get("Item")),
                clean_text("-"), #--> Specs not specified in stocks
                clean_text("-"),   #--> UOM not specified in stocks
                clean_text(row.get("Category")), 
                True,
                True
            ))
                
    for _, row in store_req_df.iterrows():
        if clean_text(row.get("Item Code")) not in item_codes_history:
            item_codes_history.append(clean_text(row.get("Item Code")))
            items_rows.append((
                clean_text(row.get("Item Code")),
                clean_text(row.get("Item Name")),
                clean_text("-"), #--> Specs not specified in store req
                clean_text("-"),   #--> UOM not specified in store req
                clean_text(row.get("ItemCategory")), 
                True,
                True
            ))

    print("Inserting items")
    bulk_insert(conn, "items", ITEMS_COLUMNS, items_rows)
    print(f"Items : inserted {len(items_rows)} rows")
