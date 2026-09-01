"""Load the items table which is the master table that 
   is being referanced from almost all other store and
   imports related tables. Some items are also loaded from 
   purchases that are not in item database"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_sheet, list_excel_files, clean_text, bulk_insert
)

from pathlib import Path

# Every folder contributes ALL of its workbooks — items are harvested from the
# item database plus whatever item codes appear in purchases, stocks and store
# requisitions but are missing from it.
folders = ["items_database", "purchases", "stocks", "store_requisitions"]
file_names = {}
for folder in folders:
    CURRENT_DIR = Path(__file__).resolve().parents[2]
    directory = CURRENT_DIR / "data" / folder

    # directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data") /folder

    file_names[folder] = list_excel_files(directory)


#Order of columns matters here (must be same as order of columns in sheet)
ITEMS_COLUMNS = ["item_code", "name", "default_specification", "default_unit_of_measurement", "category", "is_active", "is_verified"]

def load_items(conn):
    df_list = [read_sheet("Sheet1", file) for file in file_names["items_database"]]
    df = pd.concat(df_list, ignore_index=True)

    purchases_df_list = [read_sheet("Sheet1", file) for file in file_names["purchases"]]
    purchases_df = pd.concat(purchases_df_list, ignore_index=True)

    stock_df_list = [read_sheet("Sheet1", file) for file in file_names["stocks"]]
    stock_df = pd.concat(stock_df_list, ignore_index=True)

    store_req_df_list = [read_sheet("Sheet1", file) for file in file_names["store_requisitions"]]
    store_req_df = pd.concat(store_req_df_list, ignore_index=True)

    # DE-DUPE WITHIN THIS BATCH ONLY — deliberately NOT pre-seeded from the
    # database any more.
    #
    # It used to start from the codes already stored, which made this loader
    # insert-if-new and nothing else: an item whose name or category changed in
    # the workbook was silently ignored for ever. That was tolerable when the
    # table was dropped and rebuilt on every load. It is not now — items is
    # UPSERTED instead of replaced (consignment_items.item_id and hs_codes.item_id
    # are real foreign keys onto items.id, so dropping it would SET NULL and
    # CASCADE across app-owned rows), so this is the only path by which a
    # corrected master reaches the database.
    #
    # Still de-duped in-batch, and that ordering matters: items_database is read
    # FIRST, so a code it defines wins over the same code appearing later in
    # purchases / stocks / store_requisitions, which carry no spec or UoM and
    # fill those columns with "-". ON CONFLICT cannot touch the same row twice
    # in one statement either, so a duplicate here would be a hard error.
    item_codes_history = []
    items_rows = []

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

    # UPSERT, NEVER REPLACE. Matched on item_code (UNIQUE), so an existing row
    # keeps its id and everything pointing at it survives.
    #
    # Only the DESCRIPTIVE columns are refreshed. is_active and is_verified are
    # deliberately excluded: those are operator decisions made in the Masters
    # screen — deactivating a line, verifying one created inline mid-entry — and
    # a workbook has no opinion about either. Overwriting them would silently
    # re-verify everything sitting in the review queue.
    #
    # NULLIF guards the placeholder: purchases / stocks / store_requisitions
    # supply "-" for spec and UoM because their sheets carry neither, and
    # without this a code that has dropped out of items_database would have a
    # real specification overwritten with a dash.
    print("Upserting items")
    bulk_insert(
        conn, "items", ITEMS_COLUMNS, items_rows,
        conflict_clause=(
            "ON CONFLICT (item_code) DO UPDATE SET "
            "name = COALESCE(NULLIF(EXCLUDED.name, ''), items.name), "
            "default_specification = COALESCE("
            "NULLIF(NULLIF(EXCLUDED.default_specification, '-'), ''), "
            "items.default_specification), "
            "default_unit_of_measurement = COALESCE("
            "NULLIF(NULLIF(EXCLUDED.default_unit_of_measurement, '-'), ''), "
            "items.default_unit_of_measurement), "
            "category = COALESCE(NULLIF(EXCLUDED.category, ''), items.category)"
        ),
    )
    print(f"Items : upserted {len(items_rows)} rows")
