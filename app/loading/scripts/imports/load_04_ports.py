"""
Load the ports master from its own dedicated workbook(s) in data/ports/, not
from the imports sheet — the imports sheet only ever carried a port NAME per
consignment (as POL/POD), never the country/type/UN-LOCODE detail this master
needs, so ports get their own small file with one row per port.

Every row here becomes one ports row: `used_as` is always PortUsedAs.BOTH,
because this file does not distinguish "loading" from "delivery" the way the
old POL/POD-column design used to — a consignment's own `loading_port_id` /
`delivery_port_id` FK is what actually decides which role a port plays for
THAT consignment, not a property of the port master row itself.

NOT deduplicated by name on purpose: the file legitimately lists the same
port name more than once with a different `Type` (e.g. a city that is both a
sea port and an air port) — collapsing by name would silently drop one of
them. `ports.name` has no unique constraint, so inserting every row is safe.
Note this only says the LOAD is safe — `load_05_consignments.py::_port_map`
still resolves a consignment's port by NAME ALONE (`{name: id}`, last one
wins on a duplicate), so a name that appears under more than one `Type` here
is still a separate, pre-existing ambiguity in that lookup, not something
this file's own insert step can fix.
"""

from pathlib import Path

from app.enums import PortType, PortUsedAs
from app.loading.scripts.etl_common import read_and_concat, list_excel_files, clean_text, bulk_insert


CURRENT_DIR = Path(__file__).resolve().parents[2]
DIRECTORY = CURRENT_DIR / "data" / "ports"

# DIRECTORY = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

# Every workbook in the folder is loaded, not just the first.
FILES = list_excel_files(DIRECTORY)

PORT_COLUMNS = ["name", "country", "port_type", "un_locode", "used_as", "is_active", "is_verified"]

# Matched case/whitespace-insensitively against PortType's own values -
# checked directly against the current workbook (133,178 rows) and every
# single one already spells it exactly "Land"/"Sea"/"Dry"/"Air", so this is
# defensive for a future re-export rather than fixing anything seen today.
# UNRECOGNISED VALUES ARE LEFT ALONE AND REPORTED, never guessed at or
# dropped - same convention as map_mode_of_shipment etc. in
# load_05_consignments.py, and for the same reason: port_type is a plain
# String column, so an unmapped spelling costs nothing to keep and reporting
# it is what surfaces a workbook that changed shape.
PORT_TYPE_VALUES = [t.value for t in PortType]
_unmapped_port_type = set()


def map_port_type(value):
    """A blank cell becomes PortType.SEA, not None: port_type is NOT NULL
    with `default="Sea"` on the model, and that Python-side default never
    runs on this raw insert - same reasoning as used_as below, which has
    the same problem for a different reason (its default never applies at
    all here, since the file carries no per-row usage of its own)."""
    s = clean_text(value)
    if not s:
        return PortType.SEA.value

    key = " ".join(s.split()).lower()
    for canonical in PORT_TYPE_VALUES:
        if key == canonical.lower():
            return canonical

    _unmapped_port_type.add(s)
    return s


def build_port_rows(df):
    """Return rows -> list of (name, country, port_type, un_locode, used_as,
    is_active, is_verified) matching PORT_COLUMNS, one per sheet row, ready
    for a bulk insert.
    """
    rows = []

    def add(name, country, type, un_locode):
        # clean_text turns a blank cell's pandas NaN into None and strips
        # placeholders — without it a blank Name/Type cell reaches psycopg2
        # as a raw float, which it can't adapt into these NOT NULL text
        # columns, and the whole load dies on that one row. port_type goes
        # through map_port_type instead of a bare clean_text, since it's
        # NOT NULL and enum-backed (see that function for the blank-cell
        # default and the unmapped-spelling handling).
        rows.append((
            clean_text(name), clean_text(country), map_port_type(type), clean_text(un_locode),
            # This file carries no Loading/Delivery distinction of its own
            # (see the module docstring) — BOTH, not None, is what the model
            # itself defaults to for a port usable either way; the model's
            # own `default=` never runs on this raw insert, so it has to be
            # written explicitly here.
            PortUsedAs.BOTH.value,
            True, True,
        ))

    for _, row in df.iterrows():
        add(row.get("Port Name"), row.get("Country"), row.get("Type"), row.get("UN/LOCODE"))

    return rows


def load_ports(conn):
    df = read_and_concat("Sheet1", FILES)

    rows = build_port_rows(df)

    bulk_insert(conn, "ports", PORT_COLUMNS, rows)

    # ids were set by hand, so move the sequence past them or the app's own
    # inserts would collide
    # with conn.cursor() as cur:
    #     cur.execute(
    #         "SELECT setval('ports_id_seq', (SELECT COALESCE(MAX(id), 1) FROM ports))"
    #     )
    conn.commit()

    print(f"Ports : inserted {len(rows)} rows")

    # Nothing here blocks the load - the value is already sitting in the row,
    # left as-is (see map_port_type) - this is only so an unrecognised
    # spelling is seen now rather than discovered later as a stray value in
    # the Masters screen's Port Type filter.
    if _unmapped_port_type:
        print(f"  ! port_type: {len(_unmapped_port_type)} unrecognised value(s), left as-is: "
              f"{sorted(_unmapped_port_type)}")
