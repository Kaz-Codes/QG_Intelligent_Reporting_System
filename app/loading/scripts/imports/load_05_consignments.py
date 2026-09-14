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

import re
from pathlib import Path

from app.enums import ModeOfShipment, PaymentInstrument, Status, UnitOfMeasurement
from app.loading.scripts.etl_common import (
    read_and_concat, list_excel_files, clean_text, clean_status, clean_int,
    clean_number, clean_date, clean_date_any, bulk_insert,
)
from app.loading.scripts.imports.item_codes import assign_item_codes

STATUS_VALUES = [s.value for s in Status]

CURRENT_DIR = Path(__file__).resolve().parents[2]
DIRECTORY = CURRENT_DIR / "data" / "imports"

# DIRECTORY = Path(r"C:\Users\hp\Desktop\internship\erp-fastapi\app\loading\data\imports")

# Every workbook in the folder is loaded, not just the first.
FILES = list_excel_files(DIRECTORY)

DEFAULT_STATUS = "TT/LC in Process"

# The sheet's status vocabulary mapped onto the canonical Status enum.
#
# Only spellings of a stage that already exists are mapped here; a sheet value
# that is a REAL stage with no equivalent (Under De-Stuffing, Order Cancelled)
# was added to the enum instead, so it passes through untouched. Anything still
# unrecognised falls back to DEFAULT_STATUS rather than being stored verbatim —
# that is what previously let values the rest of the system cannot handle into
# the status column.
STATUS_MAP = {
    "lc in process": "TT/LC in Process",
    "t/t in process": "TT/LC in Process",
    "tt in process": "TT/LC in Process",
    # Costing precedes the instrument being opened, so it sits at the same
    # pre-shipment stage rather than getting one of its own.
    "costing in process": "TT/LC in Process",
}

CURRENCY_MAP = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "RMB": "CNY"}


def map_status(value):
    """Sheet status -> a canonical Status value, never anything else."""
    s = clean_status(value)
    if not s:
        return DEFAULT_STATUS

    key = s.strip().lower()
    if key in STATUS_MAP:
        return STATUS_MAP[key]

    # Already canonical (case-insensitively)? Keep the canonical spelling.
    for canonical in STATUS_VALUES:
        if key == canonical.lower():
            return canonical

    return DEFAULT_STATUS

CONSIGNMENT_COLUMNS = [
    "id", "branch_id", "supplier_id", "clearing_agent_id",
    "loading_port_id", "delivery_port_id",
    "origin", "currency", "consignment_type", "mode_of_shipment",
    "cargo_readiness_date", "etd", "eta", "eta_works",
    "payment_instrument", "instrument_number", "opening_or_retirement_date", "required_date",
    "exchange_rate", "current_status", "remarks",
    "gd_number", "gd_filing_date", "free_days_allowed", "gate_out_date",
    "created_by_id",
    # The order this consignment is a batch of, and its position in that order.
    # Both NOT NULL — see BATCH_GROUP_COLUMNS below.
    "batch_group_id", "batch_sequence",
    # is_deleted is NOT NULL with only a Python-side default, so a raw insert
    # has to set it — the ORM default never runs here.
    "is_deleted",
    # Both have server_defaults, so a raw insert *could* omit them — but a
    # historical row that already reached a terminal status is finished work,
    # not a draft someone abandoned mid-entry. See terminal_flags below.
    "record_state", "is_locked",
]

# The two terminal statuses. A sheet row that already carries one of these
# describes a consignment that is over, so it loads as submitted rather than
# as a draft — otherwise the Closed stage fills up with rows the Submitted
# column calls drafts, which is a contradiction.
#
# Only ARRIVED_AT_WORKS also locks (helpers.is_closed = that status AND
# submitted). ORDER_CANCELLED is terminal but was never "closed" in the lock
# sense — there is nothing for an admin to reopen — so it loads unlocked, the
# same as a cancelled order entered through the app.
TERMINAL_STATUSES = {
    Status.ARRIVED_AT_WORKS.value: ("submitted", True),
    Status.ORDER_CANCELLED.value: ("submitted", False),
}


def terminal_flags(status):
    """(record_state, is_locked) for a loaded consignment at `status`."""
    return TERMINAL_STATUSES.get(status, ("draft", False))

ITEM_COLUMNS = [
    # order_item_id is NOT NULL: every shipment line is an allocation against
    # a line on the order, and the loader builds both.
    "consignment_id", "order_item_id",
    "item_id", "item_code", "item_name", "specification",
    "hs_code", "quantity", "unit_price", "unit_of_measurement", "eta_works",
    "batch_no", "job_number", "mo_number",
    "is_deleted",
]

ETA_COLUMNS = [
    "consignment_id", "eta_type", "previous_eta", "new_eta",
    "cause_of_revision", "user_id",
]

# THE ORDER A CONSIGNMENT IS A BATCH OF, and the items on that order.
#
# The loader writes raw psycopg2 INSERTs, so nothing the ORM does applies here:
# no Python-side default runs, and no amount of care in the models stops this
# file writing a consignment with no order above it. Both link columns are NOT
# NULL, so a loader that did not build these rows would simply fail — which is
# the good case. The bad case is the one this section exists to prevent: rows
# that load fine and carry a second, divergent copy of the truth.
#
# Every consignment loaded from the sheet is a group of ONE, founding its own
# group, exactly as the migration back-filled the rows that were already there.
# The sheet has no notion of a split order — `Batch No` is free text an operator
# typed and is deliberately never converted into batches.
BATCH_GROUP_COLUMNS = [
    "id", "founding_consignment_id", "batches_ever",
    "supplier_id", "origin", "currency", "consignment_type", "incoterm",
    "payment_instrument", "instrument_number",
    "exchange_rate", "rate_booked_on", "rate_source",
    "works_branch_id",
    "created_by_id", "is_deleted",
]

ORDER_ITEM_COLUMNS = [
    "id", "batch_group_id",
    "item_id", "item_code", "item_name", "specification", "hs_code",
    "ordered_quantity", "allocated_quantity", "unit_of_measurement",
    "price_basis", "unit_price",
    "branch_id", "required_date",
    "job_number", "mo_number",
    "is_deleted",
]


#--------------------------------------
# small value mappers
#--------------------------------------

def map_currency(value):
    s = clean_text(value)
    if not s:
        return None
    return CURRENCY_MAP.get(s, s)


# The sheet's Country column -> the ISO 3166-1 English short name.
#
# WHY THE LOADER AND NOT ONLY THE MIGRATION. Alembic revision `f3a91c60d28b`
# corrects the 59 stored rows once; this is what stops the next reload putting
# `UAE` and `Turkey` straight back, because `origin` is written verbatim from
# the workbook. Same shape as `map_currency` and `map_mode_of_shipment` above
# and below - the loaders normalise on the way in, so a screen never has to.
#
# `SA` -> Saudi Arabia is the project owner's decision, not an inference: the
# sheet also carries `South Africa` and `KSA`, so the abbreviation is genuinely
# ambiguous and was referred rather than guessed. Recorded here as well as in
# the revision, because this is the copy that keeps applying.
#
# AN UNKNOWN SPELLING IS KEPT, NOT DROPPED. A country nobody has seen before
# is data, and nulling it would cut the row out of every origin breakdown; it
# is collected and reported at the end of the load instead, the way
# `map_mode_of_shipment` reports its own.
COUNTRY_TO_ISO = {
    "turkey":       "Türkiye",
    "uae":          "United Arab Emirates",
    "sa":           "Saudi Arabia",
    "usa":          "United States of America",
    "south korea":  "Korea, Republic of",
    "korea":        "Korea, Republic of",
    "taiwan":       "Taiwan, Province of China",
    "tanzania":     "Tanzania, United Republic of",
    "ksa":          "Saudi Arabia",
    "phillpines":   "Philippines",
    "philipine":    "Philippines",
}

# The ISO names this data is ALREADY known to use correctly, so the report
# below does not cry wolf on every country in the sheet. Eighteen names: the
# eight COUNTRY_TO_ISO produces plus the ten that were already right.
#
# DELIBERATELY NOT THE FULL 249. The frontend needs every country because a
# person picks from it; the loader only needs to tell "a spelling somebody
# should look at" from "a spelling that is fine", and an allow-list of what
# this workbook actually contains does that with eighteen entries instead of a
# second copy of ISO 3166 that has to be kept in step with `countries.ts`. A
# genuinely new country is reported once, checked, and added here - the same
# contract `_unmapped_mode_of_shipment` has had all along.
KNOWN_ISO_ORIGINS = frozenset({
    "Türkiye", "United Arab Emirates", "Saudi Arabia",
    "United States of America", "Korea, Republic of",
    "Taiwan, Province of China", "Tanzania, United Republic of", "Philippines",
    "China", "South Africa", "Canada", "Hong Kong", "Italy", "Germany",
    "Sweden", "Pakistan", "Malaysia", "Singapore",
})

_unmapped_country = set()


def map_country(value):
    s = clean_text(value)
    if not s:
        return None

    key = " ".join(s.split()).lower()
    if key in COUNTRY_TO_ISO:
        return COUNTRY_TO_ISO[key]

    if s not in KNOWN_ISO_ORIGINS:
        _unmapped_country.add(s)
    return s


def map_consignment_type(value):
    """The sheet's EFS column -> EFS / Regular import / unknown.

    Matched on the first letter rather than an exact list, because the column is
    hand-typed and carries things like "NO HS Code Issue" — plainly not EFS, but
    an exact match drops it into the unknown bucket alongside the genuinely
    blank rows. None still means "the sheet does not say", which is a real and
    large bucket here (well over half the lines) and is reported as its own
    category rather than being folded into Regular.
    """
    s = clean_text(value)
    if not s:
        return None

    s = s.strip().lower()

    if s.startswith("y") or s == "efs":
        return "EFS"
    if s.startswith("n"):
        return "Regular import"
    return None


#--------------------------------------
# mode_of_shipment / payment_instrument / unit_of_measurement
#
# Alembic revision d5e81b6a2c07 normalised these three columns onto their
# enums once already — see CLAUDE.md, "A STRING COLUMN DOES NOT ENFORCE THE
# ENUM, AND THE LOADERS GO ROUND IT." This loader never mapped them, only
# `currency` and `consignment_type` above got that treatment, so a reload
# would undo the fix and put 96.6% of consignments back where the request
# schema 422s on a field the operator never touched.
#
# Matched case- and whitespace-insensitively: the sheet has "By  Air" with
# two spaces. UNRECOGNISED VALUES ARE LEFT ALONE AND REPORTED, never
# blanked to None — that is different from map_status/map_incoterm above,
# which blank on purpose. An enum-backed column can hold anything (the
# column is a plain String), so leaving the raw value in place costs
# nothing today and keeps the evidence that the sheet changed shape,
# rather than discarding it the way a silent None would.
#--------------------------------------

MODE_OF_SHIPMENT_VALUES = [m.value for m in ModeOfShipment]
PAYMENT_INSTRUMENT_VALUES = [p.value for p in PaymentInstrument]
UNIT_OF_MEASUREMENT_VALUES = [u.value for u in UnitOfMeasurement]

_unmapped_mode_of_shipment = set()
_unmapped_payment_instrument = set()
_unmapped_unit_of_measurement = set()

MODE_OF_SHIPMENT_MAP = {
    "sea": ModeOfShipment.SEA_FREIGHT_FCL.value,
    "by sea": ModeOfShipment.SEA_FREIGHT_FCL.value,
    "lcl": ModeOfShipment.SEA_FREIGHT_LCL.value,
    "air": ModeOfShipment.AIR_FREIGHT.value,
    "by air": ModeOfShipment.AIR_FREIGHT.value,
}

# A leading count/size token — "1 x 20' OT", "2 x 20' + 2 x 40' OT" —
# describes a container booking, not a shipment mode. Every such row in the
# sheet is sea freight, so it maps the same way a plain "Sea" does.
_CONTAINER_SPEC = re.compile(r"^\d+\s*x\s*\d+")


def map_mode_of_shipment(value):
    s = clean_text(value)
    if not s:
        return None

    key = " ".join(s.split()).lower()

    if key in MODE_OF_SHIPMENT_MAP:
        return MODE_OF_SHIPMENT_MAP[key]

    if _CONTAINER_SPEC.match(key):
        return ModeOfShipment.SEA_FREIGHT_FCL.value

    for canonical in MODE_OF_SHIPMENT_VALUES:
        if key == canonical.lower():
            return canonical

    _unmapped_mode_of_shipment.add(s)
    return s


PAYMENT_INSTRUMENT_MAP = {
    "advance": PaymentInstrument.ADV.value,
    "tt": PaymentInstrument.ADV.value,
    "100%lc": PaymentInstrument.LC.value,
}

# Real, named payment types the sheet uses that the enum has no slot for —
# widening it is a business call (design doc, "widen the enums"), not made
# here. Blanked rather than left raw, the same as an out-of-enum value the
# migration already treated this way.
PAYMENT_INSTRUMENT_BLANK = {"foc", "exp", "contract"}


def map_payment_instrument(value):
    s = clean_text(value)
    if not s:
        return None

    key = " ".join(s.split()).lower()

    if key in PAYMENT_INSTRUMENT_BLANK:
        return None

    if key in PAYMENT_INSTRUMENT_MAP:
        return PAYMENT_INSTRUMENT_MAP[key]

    for canonical in PAYMENT_INSTRUMENT_VALUES:
        if key == canonical.lower():
            return canonical

    _unmapped_payment_instrument.add(s)
    return s


UNIT_OF_MEASUREMENT_MAP = {
    "kgs": UnitOfMeasurement.KG.value,
    "tons": UnitOfMeasurement.TON.value,
    # Metric tonne — an UNCONFIRMED reading. The enum has no separate MT
    # value, only Ton, and this is the closest match rather than a
    # confirmed business decision. Flagged rather than assumed silently.
    "mt": UnitOfMeasurement.TON.value,
    "pc": UnitOfMeasurement.PCS.value,
    "pc.": UnitOfMeasurement.PCS.value,
    "pcs.": UnitOfMeasurement.PCS.value,
}


def map_unit_of_measurement(value):
    s = clean_text(value)
    if not s:
        return None

    key = " ".join(s.split()).lower()

    if key in UNIT_OF_MEASUREMENT_MAP:
        return UNIT_OF_MEASUREMENT_MAP[key]

    for canonical in UNIT_OF_MEASUREMENT_VALUES:
        if key == canonical.lower():
            return canonical

    _unmapped_unit_of_measurement.add(s)
    return s


def _report_unmapped():
    """Print anything that matched no known spelling, for all four columns.

    Called once at the end of a load. Nothing here BLOCKS the load — the
    values are already sitting in the row tuples, left as-is — this is only
    so an unrecognised spelling is seen rather than discovered later as a
    422 nobody can explain.
    """
    reports = [
        ("mode_of_shipment", _unmapped_mode_of_shipment),
        ("payment_instrument", _unmapped_payment_instrument),
        ("unit_of_measurement", _unmapped_unit_of_measurement),
        # A country spelling COUNTRY_TO_ISO has never seen. Unlike the three
        # above it cannot cause a 422 - `origin` is free text, not an enum -
        # but an unreported one silently splits a country across two rows of
        # every origin breakdown, which is the reason the field became a list.
        ("origin", _unmapped_country),
    ]
    for label, values in reports:
        if values:
            print(f"  ! {label}: {len(values)} unrecognised value(s), left as-is: "
                  f"{sorted(values)}")


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

def build_rows(df, port_map, item_map, created_by_id, branch_ids=None):
    consignment_rows = []
    item_rows = []
    eta_rows = []
    group_rows = []
    order_item_rows = []
    dropped_branches = 0

    # The group id and the consignment id are kept deliberately EQUAL: every
    # loaded consignment founds its own group, so group N belongs to
    # consignment N and the two sequences stay legible side by side. Nothing
    # depends on the equality — the columns are real foreign keys — but a
    # reader comparing the two tables after a load should not have to derive
    # the mapping.
    order_item_id = 0

    for index, rows in enumerate(_group(df)):
        consignment_id = index + 1
        batch_group_id = consignment_id

        pol = _first(rows, "POL", clean_text)
        pod = _first(rows, "POD", clean_text)

        chain = _eta_chain(rows)
        eta = chain[-1] if chain else None

        status = map_status(_first(rows, "Current Status", clean_status))
        record_state, is_locked = terminal_flags(status)

        branch_id = _first(rows, "works_id", clean_int)
        if branch_ids is not None and branch_id is not None and branch_id not in branch_ids:
            branch_id = None
            dropped_branches += 1

        # Computed ONCE and written to both consignments AND the group below,
        # rather than mapped twice from two separate _first() calls. Mapping
        # it twice cannot actually disagree — both calls read the same rows —
        # but a single shared value is what makes that true by construction
        # rather than by coincidence, which is the whole lesson of the
        # migration that only fixed the consignments copy and left the
        # group's holding 'Advance' (CLAUDE.md, "A STRING COLUMN DOES NOT
        # ENFORCE THE ENUM").
        payment_instrument = map_payment_instrument(
            _first(rows, "Payment Mode", lambda v: v)
        )

        consignment_rows.append((
            consignment_id,
            branch_id,
            _first(rows, "supplier_id", clean_int),
            _first(rows, "clearing_agent_id", clean_int),
            port_map.get(pol) if pol else None,            # loading_port_id
            port_map.get(pod) if pod else None,            # delivery_port_id
            _first(rows, "Country", map_country),          # origin
            map_currency(_first(rows, "Currency", lambda v: v)),
            map_consignment_type(_first(rows, "EFS", lambda v: v)),
            map_mode_of_shipment(_first(rows, "Mode of Shipment", lambda v: v)),
            _first(rows, "Rediness Dt.", clean_date),
            _first(rows, "ETD", clean_date),
            eta,
            _first(rows, "ETA Works", clean_date_any),
            payment_instrument,
            _first(rows, "Payment Ref No", clean_text),    # instrument_number
            _first(rows, "Ret Dt.", clean_date),
            _first(rows, "Req. Dt.", clean_date),
            _first(rows, "Exchange Rate", clean_number),
            status,
            _first(rows, "Remarks", clean_text),
            _first(rows, "GD No", clean_text),
            _first(rows, "GD File", clean_date),
            _first(rows, "Free Days", clean_int),
            _first(rows, "Gate-out", clean_date),
            created_by_id,
            batch_group_id,
            1,                                             # batch_sequence
            False,                                         # is_deleted
            record_state,
            is_locked,
        ))

        # One group per consignment, carrying a COPY of the shared values. They
        # stay on the consignment too until revision B drops them there, and
        # the copy here is what the app reads — the same shape the migration
        # left the pre-existing rows in.
        group_rows.append((
            batch_group_id,
            consignment_id,                                # founding_consignment_id
            1,                                             # batches_ever
            _first(rows, "supplier_id", clean_int),
            _first(rows, "Country", map_country),          # origin
            map_currency(_first(rows, "Currency", lambda v: v)),
            map_consignment_type(_first(rows, "EFS", lambda v: v)),
            None,                                          # incoterm: not in the sheet
            payment_instrument,
            _first(rows, "Payment Ref No", clean_text),    # instrument_number
            _first(rows, "Exchange Rate", clean_number),
            None,                                          # rate_booked_on: not in the sheet
            None,                                          # rate_source: not in the sheet
            branch_id,                                     # works_branch_id
            created_by_id,
            False,                                         # is_deleted
        ))

        # one item line per row in the group, and one ORDER item above each of
        # them. The sheet describes a single shipment, so what was ordered and
        # what this batch carried are the same quantity: ordered_quantity and
        # allocated_quantity both take the sheet quantity, which is what these
        # rows mean.
        for r in rows:
            item_code = clean_text(r.get("Item Code"))
            item_id = item_map.get(item_code) if item_code else None
            item_name = clean_text(r.get("Item Name"))
            specification = clean_text(r.get("Specs/Standard"))
            hs_code = clean_text(r.get("H.S. Code"))
            quantity = clean_number(r.get("Qty."))
            unit_price = clean_number(r.get("Unit Price"))
            uom = map_unit_of_measurement(r.get("UOM"))
            job_number = clean_text(r.get("Job No"))
            mo_number = clean_text(r.get("MO No"))

            order_item_id += 1
            order_item_rows.append((
                order_item_id,
                batch_group_id,
                item_id,
                item_code,
                item_name,
                specification,
                hs_code,
                # COALESCE in Python, for the same reason the migration does it
                # in SQL: ordered_quantity is NOT NULL and a sheet row can carry
                # no quantity at all. A line that orders nothing back-fills as 0
                # rather than taking the whole load down.
                quantity if quantity is not None else 0,
                quantity if quantity is not None else 0,
                uom,
                "quantity",                                # price_basis
                unit_price,
                # branch and required date are header columns in the sheet and
                # per-item columns here, so every order item inherits its
                # consignment's — the header value is the true one for every
                # line under it.
                branch_id,
                _first(rows, "Req. Dt.", clean_date),      # required_date
                job_number,
                mo_number,
                False,                                     # is_deleted
            ))

            item_rows.append((
                consignment_id,
                order_item_id,
                # link to the item master when the code exists there;
                # NULL if the sheet code is not catalogued
                item_id,
                item_code,
                item_name,
                specification,
                hs_code,
                quantity,
                unit_price,
                uom,
                # The LINE's own ETA, not the header's. The rows grouped under
                # one payment reference do not all arrive together — see the
                # column's comment on ConsignmentItem for what that cost.
                clean_date_any(r.get("ETA Works")),
                clean_text(r.get("Batch No")),
                job_number,
                mo_number,
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

    if dropped_branches:
        print(f"  {dropped_branches} consignment(s) referenced a works that is not a "
              f"branch (QH) — kept, with no branch")

    return consignment_rows, item_rows, eta_rows, group_rows, order_item_rows


#--------------------------------------
# db lookups
#--------------------------------------

def _admin_id(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE is_admin = true ORDER BY id LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("No admin user found — seed the admin before loading consignments")
    return row[0]


def _port_map(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT name, id FROM ports")
        return {name: pid for name, pid in cur.fetchall()}


def _branch_ids(conn):
    """The branch ids that actually exist, so a consignment cannot point at one
    that does not.

    The sheet's works_id 5 is "QH", which is not a branch of the business and is
    no longer loaded (see load_02_branches). Writing branch_id = 5 anyway would
    fail the foreign key and take the whole insert down with it, so those
    consignments are kept with NO branch instead — the import is real, its
    branch attribution is not.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM branches")
        return {row[0] for row in cur.fetchall()}


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

    # _group() keeps only rows that carry an Item Code, so the gaps have to be
    # filled BEFORE grouping — otherwise every uncoded row is dropped and the
    # sheet loses most of its lines (294 of 451 in the current workbook).
    code_report = assign_item_codes(df, conn)
    print(
        "  item codes: "
        f"{code_report['already_coded']} already coded, "
        f"{code_report['from_sheet_sibling']} from a sibling row, "
        f"{code_report['from_master']} from the items master, "
        f"{code_report['generated']} generated "
        f"({code_report['generated_items']} distinct items)"
    )
    if code_report["no_item_name"]:
        print(f"  ! {code_report['no_item_name']} row(s) have no item name and are skipped")
    if code_report["conflicting_pairs"]:
        print(f"  ! {code_report['conflicting_pairs']} item(s) carry more than one code in the sheet")

    port_map = _port_map(conn)
    item_map = _item_map(conn)
    branch_ids = _branch_ids(conn)
    created_by_id = _admin_id(conn)

    consignment_rows, item_rows, eta_rows, group_rows, order_item_rows = build_rows(
        df, port_map, item_map, created_by_id, branch_ids
    )

    # CONSIGNMENTS AND THEIR GROUPS GO IN ONE TRANSACTION, with no commit
    # between them. Each table has a NOT NULL foreign key onto the other, so
    # neither half stands alone; the constraints are DEFERRABLE INITIALLY
    # DEFERRED precisely so the pair can be inserted together and checked at
    # COMMIT. Commit after the first and the deferred check runs while the
    # other half is still missing.
    bulk_insert(conn, "consignments", CONSIGNMENT_COLUMNS, consignment_rows, commit=False)
    bulk_insert(conn, "consignment_batch_groups", BATCH_GROUP_COLUMNS, group_rows,
                commit=False)
    conn.commit()

    # Order items hang off the groups, and the lines hang off both the
    # consignments and the order items, so both are already committed by here.
    bulk_insert(conn, "consignment_order_items", ORDER_ITEM_COLUMNS, order_item_rows)
    bulk_insert(conn, "consignment_items", ITEM_COLUMNS, item_rows)
    bulk_insert(conn, "eta_revision_history", ETA_COLUMNS, eta_rows)

    _bump_sequence(conn, "consignments")
    _bump_sequence(conn, "consignment_items")
    _bump_sequence(conn, "eta_revision_history")
    # The two new tables take explicit ids like every other loaded table, so
    # they need the same bump: without it the first row the APP inserts reuses
    # id 1 and dies on the primary key, surfacing as a bare
    # "Internal server error" with nothing on screen to point at.
    _bump_sequence(conn, "consignment_batch_groups")
    _bump_sequence(conn, "consignment_order_items")

    linked = sum(1 for r in item_rows if r[1] is not None)
    # record_state / is_locked are the last two columns of CONSIGNMENT_COLUMNS.
    submitted = sum(1 for r in consignment_rows if r[-2] == "submitted")
    locked = sum(1 for r in consignment_rows if r[-1])
    print(f"Consignments : inserted {len(consignment_rows)} rows "
          f"({submitted} at a terminal status loaded as submitted, {locked} of them closed)")
    print(f"Consignment items : inserted {len(item_rows)} rows "
          f"({linked} linked to an item, {len(item_rows) - linked} without a master match)")
    print(f"Batch groups : inserted {len(group_rows)} rows (every consignment a group of one)")
    print(f"Order items : inserted {len(order_item_rows)} rows")
    _report_unmapped()
    print(f"ETA revisions : inserted {len(eta_rows)} rows")
