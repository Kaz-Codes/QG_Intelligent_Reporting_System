"""Load Suppliers master table"""

import pandas as pd
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, bulk_insert, clean_int,
    bump_sequence
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

# Values in the sheet's "Works" column that are NOT branches of the business and
# must never become one. Compared case-insensitively.
NOT_BRANCHES = {"QH"}


def _canonical_names(df):
    """works_id -> the spelling to store.

    The sheet spells one branch two ways — "QBL-II" on 73 lines and "QBl-II" on
    4 — under the SAME works_id. Taking whichever row happens to come first (what
    drop_duplicates does) makes the stored name depend on row order, so the most
    frequently used spelling is chosen instead. Ties break alphabetically so the
    result is deterministic.
    """
    counts = {}

    for _, row in df.iterrows():
        works_id = row.get("works_id")
        name = clean_text(row.get("Works"))

        if pd.isna(works_id) or not name:
            continue

        counts.setdefault(int(works_id), {})
        counts[int(works_id)][name] = counts[int(works_id)].get(name, 0) + 1

    return {
        works_id: max(sorted(spellings), key=lambda n: spellings[n])
        for works_id, spellings in counts.items()
    }


def load_branches(conn):
    df = read_and_concat("Sheet1", files)

    canonical = _canonical_names(df)

    df = df.drop_duplicates(subset=["works_id"])
    branch_rows = []
    skipped = []

    for _, row in df.iterrows():
        branch_id = row["works_id"]

        if pd.isna(branch_id):
            continue

        name = canonical.get(int(branch_id)) or clean_text(row.get("Works"))

        # QH is not a branch of the business, so it is not offered as one. The
        # consignments that reference it keep their rows but end up with no
        # branch — see load_05_consignments — rather than being attributed to a
        # works that does not exist.
        if name and name.strip().upper() in NOT_BRANCHES:
            skipped.append(name)
            continue

        row_tuple = (int(branch_id), name, None, None, None)
        row_tuple = row_tuple + (True, ) + (True, )
        branch_rows.append(row_tuple)

    bulk_insert(conn, "branches", BRANCH_COLUMNS, branch_rows)

    if skipped:
        print(f"  skipped {len(skipped)} non-branch value(s): {sorted(set(skipped))}")

    # ids were set by hand — see bump_sequence.
    bump_sequence(conn, "branches")

    print(f"Branches : inserted {len(branch_rows)} rows")
