"""Load the Main Purchases table"""

import pandas as pd
pd.set_option("display.max_columns", None)
from app.loading.scripts.etl_common import (
    read_and_concat, read_sheet, list_excel_files, clean_text, clean_int,
    clean_date, bulk_insert,
)
from app.loading.scripts.stores.item_registry import register_missing_items
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parents[2]
directory = CURRENT_DIR / "data" / "purchases"

# directory = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\purchases")

# Every workbook in the folder is loaded, not just the first.
files = list_excel_files(directory)

#--------------------------------------
# THE WORKBOOK SPILLS ONTO A SECOND SHEET
#
# The export is an old-format .xls, which holds at most 65,536 rows per sheet.
# Sheet1 fills to 65,520 data rows and the rest continues on Sheet2 — with NO
# header of its own, because it is a continuation rather than a new table. Its
# first data row (Record No 65521, straight after Sheet1's 65520) was being
# read AS the header.
#
# Loading only Sheet1 quietly lost 13,411 purchase lines, and worse: Sheet1
# stops at 2026-01-23 while Sheet2 runs to 2026-08-07. The purchases dashboard
# reporting "no data this month, latest is 23 Jan" was not a data-entry gap at
# all — it was seven months of purchases sitting on a sheet nothing read.
#
# So every sheet is loaded, and a sheet whose header does not look like Sheet1's
# is treated as a headerless continuation and given Sheet1's column names.
#--------------------------------------

# How many of the first sheet's column names a later sheet must repeat before
# it counts as having a header of its own. Well below 30 so a renamed column
# cannot flip the decision, well above 0 so a continuation never matches.
HEADER_MATCH_THRESHOLD = 5


def read_purchases_frames(workbooks):
    """Every sheet of every purchases workbook, as one frame.

    The first sheet defines the columns. A later sheet is read headerless and
    given those names UNLESS its own first row genuinely looks like a header —
    so this keeps working if the export ever starts writing one.
    """
    frames = []

    for workbook in workbooks:
        sheet_names = pd.ExcelFile(workbook).sheet_names
        if not sheet_names:
            continue

        first = read_sheet(sheet_names[0], workbook)
        columns = list(first.columns)
        frames.append(first)

        for name in sheet_names[1:]:
            headed = read_sheet(name, workbook)
            repeated = sum(1 for c in headed.columns if str(c).strip() in columns)

            if repeated >= HEADER_MATCH_THRESHOLD:
                frames.append(headed)
                continue

            # A continuation: re-read it with no header and borrow the first
            # sheet's names, so the row consumed as a header comes back.
            spill = pd.read_excel(workbook, sheet_name=name, header=None)
            if spill.empty:
                continue
            if len(spill.columns) != len(columns):
                print(f"   ! sheet {name!r} has {len(spill.columns)} columns against "
                      f"{len(columns)} on {sheet_names[0]!r} — skipped, it is not a "
                      f"continuation")
                continue

            spill.columns = columns
            spill = spill.dropna(how="all")
            print(f"   sheet {name!r}: {len(spill)} rows read as a continuation "
                  f"of {sheet_names[0]!r} (no header of its own)")
            frames.append(spill)

    return pd.concat(frames, ignore_index=True)


#--------------------------------------
# IN-HOUSE "SUPPLIERS" ARE NOT SUPPLIERS
#
# Qadbros Engineering is a Qadri company. A purchase booked against it is the
# group buying from itself, not a vendor relationship, so storing it as the
# supplier put an in-house entity at the top of every supplier ranking and made
# "top supplier" describe internal transfers.
#
# It is NULLED AT LOAD, not filtered in the dashboards: the column should not
# claim a supplier that was never one, and a value nulled here cannot be missed
# by a screen that forgets to exclude it. The purchase itself is kept — the
# money is real, only the vendor attribution is not.
#
# Import (IOL) is the same idea handled one layer up, in
# purchases.calculations.NON_SUPPLIERS: it is excluded from supplier figures
# while still counting toward the total.
#--------------------------------------

IN_HOUSE_SUPPLIERS = {"qadbros engineering pvt ltd"}


def map_supplier(value):
    """The vendor, or None where the 'supplier' is one of our own companies."""
    name = clean_text(value)
    if name is None:
        return None
    return None if name.strip().lower() in IN_HOUSE_SUPPLIERS else name


#Order of columns matters here (must be same as order of ROWS list)
PURCHASES_COLUMNS = [
    "ref_no", "qty", "branch", "amount", "ppc_store", "required_d", "purchase", "mop", "dc_no"  ,"bill_no", "sourcing_o", "item_code", "item_name", "specification", "supplier", "po_number", "po_date"
]

def load_purchases(conn):
    df = read_purchases_frames(files)

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
            map_supplier(row.get("Supplier")),
            clean_text(row.get("PO Numbe")),
            clean_date(row.get("PO Date")),
        ))

    bulk_insert(conn, "purchases_data", PURCHASES_COLUMNS, purchases_rows)
    print(f"Purchases : inserted {len(purchases_rows)} rows")
