"""
Load consignments, their item lines and their ETA revision history from the
imports sheet.

Grouping: rows that share a Payment Ref No are ONE consignment (one import).
Every row of the group is an item line under that consignment. A row with no
payment ref stands on its own as a single line consignment.

The three tables are loaded together because the item lines and the ETA
revisions hang off the consignment id, so the consignment is given an explicit
id here and its children point back at it.

Master ids (supplier_id, clearing_agent_id, works_id) come straight from the
sheet — those masters are already loaded. works_id in the sheet is the BRANCH,
so it fills branch_id. Loading and delivery ports are resolved by name against
the ports table (see load_01_ports for why not by id).

ETA revisions: the sheet keeps the ETA history across the 1st..4th ETA + ETA
columns. Each change from one to the next becomes a revision row, so the first
revision's previous_eta is the originally promised ETA (which is what slippage
is measured from). The revision timestamp is not in the sheet, so created_at
falls to load time.
"""

from pathlib import Path

from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_status, clean_int,
    clean_number, clean_date, bulk_insert,
)

CURRENT_DIR = Path(__file__).resolve().parents[2]
DIRECTORY = CURRENT_DIR / "data" / "imports"

# DIRECTORY = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

# Every workbook in the folder is loaded, not just the first.
FILES = list_excel_files(DIRECTORY)

DEFAULT_STATUS = "TT/LC in Process"

CURRENCY_MAP = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "RMB": "CNY"}

CONSIGNMENT_COLUMNS = [
    "id", "branch_id", "supplier_id", "clearing_agent_id",
    "loading_port_id", "delivery_port_id",
    "origin", "currency", "consignment_type", "mode_of_shipment",
    "cargo_readiness_date", "etd", "eta", "eta_works",
    "payment_instrument", "instrument_number", "opening_or_retirement_date",
    "exchange_rate", "current_status", "remarks",
    "gd_number", "gd_filing_date", "free_days_allowed", "gate_out_date",
    "created_by_id",
    # is_deleted is NOT NULL with only a Python-side default, so a raw insert
    # has to set it — the ORM default never runs here.
    "is_deleted",
]

ITEM_COLUMNS = [
    "consignment_id", "item_id", "item_code", "item_name", "specification",
    "hs_code", "quantity", "unit_price", "unit_of_measurement", "batch_no",
    "job_number", "mo_number",
    "is_deleted",
]

ETA_COLUMNS = [
    "consignment_id", "eta_type", "previous_eta", "new_eta",
    "cause_of_revision", "user_id",
]


#--------------------------------------
# small value mappers
#--------------------------------------

def map_currency(value):
    s = clean_text(value)
    if not s:
        return None
    return CURRENCY_MAP.get(s, s)


def map_consignment_type(value):
    s = clean_text(value)
    if not s:
        return None
    s = s.lower()
    if s in ("yes", "y", "efs"):
        return "EFS"
    if s in ("no", "n", "regular", "regular import"):
        return "Regular import"
    return None


def _first(rows, col, cleaner):
    """First non-null cleaned value of a column across a group of rows."""
    for r in rows:
        v = cleaner(r.get(col))
        if v is not None:
            return v
    return None


def _eta_chain(rows):
    """The ordered list of distinct ETAs across 1st..4th ETA + ETA."""
    chain = []
    for col in ["1st ETA", "2nd ETA", "3rd ETA", "4th ETA", "ETA"]:
        d = _first(rows, col, clean_date)
        if d is not None and (not chain or chain[-1] != d):
            chain.append(d)
    return chain


#--------------------------------------
# grouping rows into consignments
#--------------------------------------

def _group(df):
    """Return an ordered list of groups (each a list of rows), one per import.

    Rows with the same payment ref are one group; a row with no payment ref is
    its own group. Only rows carrying an item code are kept.
    """
    order = []
    by_ref = {}
    singleton = 0

    for _, row in df.iterrows():
        if not clean_text(row.get("Item Code")):
            continue

        ref = clean_text(row.get("Payment Ref No"))

        if ref is None:
            key = ("noref", singleton)
            singleton += 1
            by_ref[key] = [row]
            order.append(key)
        else:
            key = ("ref", ref)
            if key not in by_ref:
                by_ref[key] = []
                order.append(key)
            by_ref[key].append(row)

    return [by_ref[k] for k in order]


#--------------------------------------
# building the rows for all three tables
#--------------------------------------

def build_rows(df, port_map, item_map, created_by_id):
    consignment_rows = []
    item_rows = []
    eta_rows = []

    for index, rows in enumerate(_group(df)):
        consignment_id = index + 1

        pol = _first(rows, "POL", clean_text)
        pod = _first(rows, "POD", clean_text)

        chain = _eta_chain(rows)
        eta = chain[-1] if chain else None

        consignment_rows.append((
            consignment_id,
            _first(rows, "works_id", clean_int),          # branch_id
            _first(rows, "supplier_id", clean_int),
            _first(rows, "clearing_agent_id", clean_int),
            port_map.get(pol) if pol else None,            # loading_port_id
            port_map.get(pod) if pod else None,            # delivery_port_id
            _first(rows, "Country", clean_text),           # origin
            map_currency(_first(rows, "Currency", lambda v: v)),
            map_consignment_type(_first(rows, "EFS", lambda v: v)),
            _first(rows, "Mode of Shipment", clean_text),
            _first(rows, "Rediness Dt.", clean_date),
            _first(rows, "ETD", clean_date),
            eta,
            _first(rows, "ETA Works", clean_date),
            _first(rows, "Payment Mode", clean_text),      # payment_instrument
            _first(rows, "Payment Ref No", clean_text),    # instrument_number
            _first(rows, "Ret Dt.", clean_date),
            _first(rows, "Exchange Rate", clean_number),
            _first(rows, "Current Status", clean_status) or DEFAULT_STATUS,
            _first(rows, "Remarks", clean_text),
            _first(rows, "GD No", clean_text),
            _first(rows, "GD File", clean_date),
            _first(rows, "Free Days", clean_int),
            _first(rows, "Gate-out", clean_date),
            created_by_id,
            False,                                         # is_deleted
        ))

        # one item line per row in the group
        for r in rows:
            item_code = clean_text(r.get("Item Code"))
            item_rows.append((
                consignment_id,
                # link to the item master when the code exists there;
                # NULL if the sheet code is not catalogued
                item_map.get(item_code) if item_code else None,
                item_code,
                clean_text(r.get("Item Name")),
                clean_text(r.get("Specs/Standard")),
                clean_text(r.get("H.S. Code")),
                clean_number(r.get("Qty.")),
                clean_number(r.get("Unit Price")),
                clean_text(r.get("UOM")),
                clean_text(r.get("Batch No")),
                clean_text(r.get("Job No")),
                clean_text(r.get("MO No")),
                False,                                     # is_deleted
            ))

        # one revision row per ETA change
        for i in range(1, len(chain)):
            eta_rows.append((
                consignment_id,
                "eta",
                chain[i - 1],
                chain[i],
                None,
                None,
            ))

    return consignment_rows, item_rows, eta_rows


#--------------------------------------
# db lookups
#--------------------------------------

def _admin_id(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id FROM users u JOIN roles r ON u.role_id = r.id "
            "WHERE lower(r.name) = 'admin' ORDER BY u.id LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("No admin user found — seed the admin before loading consignments")
    return row[0]


def _port_map(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT name, id FROM ports")
        return {name: pid for name, pid in cur.fetchall()}


def _item_map(conn):
    """item_code -> id for every catalogued item, so a line can link to its
    master. Codes are cleaned the same way as the sheet so they match."""
    with conn.cursor() as cur:
        cur.execute("SELECT item_code, id FROM items")
        return {
            clean_text(code): pid
            for code, pid in cur.fetchall()
            if clean_text(code)
        }


def _bump_sequence(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table}))"
        )
    conn.commit()


#--------------------------------------
# the loader
#--------------------------------------

def load_consignments(conn):
    df = read_and_concat("Sheet1", FILES)

    port_map = _port_map(conn)
    item_map = _item_map(conn)
    created_by_id = _admin_id(conn)

    consignment_rows, item_rows, eta_rows = build_rows(
        df, port_map, item_map, created_by_id
    )

    bulk_insert(conn, "consignments", CONSIGNMENT_COLUMNS, consignment_rows)
    bulk_insert(conn, "consignment_items", ITEM_COLUMNS, item_rows)
    bulk_insert(conn, "eta_revision_history", ETA_COLUMNS, eta_rows)

    _bump_sequence(conn, "consignments")
    _bump_sequence(conn, "consignment_items")
    _bump_sequence(conn, "eta_revision_history")

    linked = sum(1 for r in item_rows if r[1] is not None)
    print(f"Consignments : inserted {len(consignment_rows)} rows")
    print(f"Consignment items : inserted {len(item_rows)} rows "
          f"({linked} linked to an item, {len(item_rows) - linked} without a master match)")
    print(f"ETA revisions : inserted {len(eta_rows)} rows")
