"""
Load the ports master from the imports sheet.

Port of loading (POL) and port of delivery (POD) are two separate columns in
the sheet, but the database keeps them in ONE ports table, told apart by the
`used_as` column (Loading vs Delivery). So every distinct POL name is loaded as
a Loading port and every distinct POD name as a Delivery port.

The sheet also carries pol_id / pod_id columns, but they are NOT usable as the
port id here: the two columns number their ports independently and collide
(id 1 is Durban as a POL but Karachi as a POD). So ports are keyed by NAME and
given fresh ids, and the consignment loader resolves loading/delivery ports by
name against this table.
"""

from pathlib import Path

from app.loading.scripts.etl_common import read_sheet, clean_text, bulk_insert


CURRENT_DIR = Path(__file__).resolve().parents[2]
DIRECTORY = CURRENT_DIR / "data" / "imports"

# DIRECTORY = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

# the real workbook, skipping any ~$ excel lock file
EXCEL_FILE = next(
    f for f in DIRECTORY.iterdir()
    if f.suffix == ".xlsx" and not f.name.startswith("~$")
)

PORT_COLUMNS = ["id", "name", "country", "port_type", "un_locode", "used_as", "is_active", "is_verified"]


def build_port_rows(df):
    """Return (rows, name_to_id).

    rows -> list of (id, name, port_type, used_as) for a bulk insert.
    name_to_id -> {port name: id} so the consignment loader can resolve FKs.
    POL and POD names do not overlap in this data, so one map is enough.
    """
    rows = []
    name_to_id = {}
    next_id = 1

    def add(name, used_as):
        nonlocal next_id
        name = clean_text(name)
        if not name or name in name_to_id:
            return
        name_to_id[name] = next_id
        # everything here is a sea port; port_type can be corrected later
        rows.append((next_id, name, None, "Sea", None, used_as, True, True))
        next_id += 1

    # only rows that carry an item code are real consignment lines
    for _, row in df.iterrows():
        if not clean_text(row.get("Item Code")):
            continue
        add(row.get("POL"), "Loading")
        add(row.get("POD"), "Delivery")

    return rows, name_to_id


def load_ports(conn):
    df = read_sheet("Sheet1", EXCEL_FILE)

    rows, _ = build_port_rows(df)

    bulk_insert(conn, "ports", PORT_COLUMNS, rows)

    # ids were set by hand, so move the sequence past them or the app's own
    # inserts would collide
    with conn.cursor() as cur:
        cur.execute(
            "SELECT setval('ports_id_seq', (SELECT COALESCE(MAX(id), 1) FROM ports))"
        )
    conn.commit()

    print(f"Ports : inserted {len(rows)} rows")
