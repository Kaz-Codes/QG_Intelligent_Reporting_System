"""
Load trucking jobs and their vehicles from the 'Inbound & Outbound Shifting'
sheet.

The sheet is one row per TRUCK, not per job: two trucks moving one LC arrive as
two rows sharing a shipment reference. That is exactly the header-plus-vehicle
shape the trucking tables want, so rows sharing a reference and an execution
date are collapsed into one job with a vehicle line each. A row with no
reference stands on its own.

Both tables are written here because the vehicle lines point back at a job id
that is assigned in this pass.

The sheet's 'Primary Key' column is useless here — 464 rows carry 5 distinct
values, nearly all of them the empty '--' the formula produces when there is no
export number. Trucking jobs are keyed on their own reference instead.
"""

from psycopg2.extras import Json

from app.loading.scripts.etl_common import (
    bulk_insert, clean_date, clean_date_any, clean_int, clean_number,
    clean_text, parse_qty_uom,
)
from app.loading.scripts.logistics.logistics_common import (
    SHEET_SHIFTING, SHEET_INTRAFACTORY, admin_id, bump_sequence,
    read_logistics_sheet,
)
from app.loading.scripts.backfill_trucking_closed import mark_closed_jobs

DEFAULT_TRACKING_STATUS = "Going to load"

# Who asked for the move -> where the job came from, in the model's vocabulary.
SOURCE_MAP = {
    "import": "from-import-fob",
    "export": "from-export",
    "logistics": "from-logistics",
}

MOVEMENT_TYPES = {"inbound": "Inbound", "outbound": "Outbound",
                  "intrafactory": "Intrafactory"}

# 'To pay' and 'To Pay' are the same term typed two ways.
PAYMENT_STATUS = {"paid": "Paid", "to pay": "To pay", "unpaid": "To pay"}

CONTAINER_SIZE_COLUMNS = {"20 FT Containers": "20 FT", "40 FT Containers": "40 FT"}

CONSIGNMENT_COLUMNS = [
    "id", "movement_type", "source", "source_ref", "taken_snapshot",
    "execution_date", "transporter_name", "shifting_type", "item_details",
    "pickup", "destination", "reference_no",
    "quoted_freight", "actual_freight", "payment_status", "paid_amount",
    "detention", "dispatch_note_date", "eta_works", "remarks",
    "created_by_id", "is_deleted",
]

VEHICLE_COLUMNS = [
    "consignment_id", "vehicle_number", "vehicle_type", "no_of_packages",
    "driver_phone", "net_weight", "gross_weight", "container_no",
    "container_type", "tracking_status", "package_refs",
    "import_consignment_refs", "is_deleted",
]


#--------------------------------------
# small value mappers
#--------------------------------------

def map_movement_type(value):
    s = clean_text(value)
    return MOVEMENT_TYPES.get(s.strip().lower()) if s else None


def map_source(value):
    s = clean_text(value)
    if not s:
        return "manual"
    return SOURCE_MAP.get(s.strip().lower(), "manual")


def map_payment_status(value):
    s = clean_text(value)
    return PAYMENT_STATUS.get(s.strip().lower(), s.strip()) if s else None


def map_tracking_status(value):
    s = clean_text(value)
    return s.strip() if s else DEFAULT_TRACKING_STATUS


def container_type_of(row):
    """Which size box this truck carried, from the two count columns."""
    for column, label in CONTAINER_SIZE_COLUMNS.items():
        count = clean_int(row.get(column))
        if count and count > 0:
            return label
    return None


#--------------------------------------
# grouping rows into jobs
#--------------------------------------

# A row counts as a real movement if ANY of these carries a value. Testing
# only reference/item/vehicle threw away 39 rows that had no reference, item
# name OR vehicle number but were plainly real movements - one carried a
# transporter, 7,500 kg, PKR 12,000 of freight and a 'Delivered' status. A
# genuine spacer row is blank across all of these.
_SIGNAL_COLUMNS = [
    "Shipment Ref. / IDM #",
    "Item Name",
    "Vehicle Number",
    "Execution Date",
    "Requester",
    "Sender",
    "Customer",
    "Transporter",
    "Movement Type",
    "Pickup Point",
    "Destination",
    "Qty. / No. of Packages",
    "Gross Weight (Kgs)",
    "Actual Freight (Rs.)",
    "Quoted Freight (Rs.)",
    "Container Number",
]


def _has_content(row):
    return any(clean_text(row.get(column)) for column in _SIGNAL_COLUMNS)


def _group(df):
    """Ordered list of groups, each a list of truck rows making up one job.

    Same shipment reference AND same execution date is one job. The date is
    part of the key because a reference like 'LC # 2629' is reused across
    separate movements weeks apart, and merging those would report one job
    with a dozen trucks that never travelled together.
    """
    order = []
    groups = {}
    standalone = 0

    for _, row in df.iterrows():
        reference = clean_text(row.get("Shipment Ref. / IDM #"))
        execution = clean_date_any(row.get("Execution Date"))

        if not _has_content(row):
            continue

        if reference:
            key = ("ref", reference, execution)
        else:
            key = ("solo", standalone)
            standalone += 1

        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    return [groups[k] for k in order]


def _first(rows, column, cleaner):
    """First non-null cleaned value of a column across a group of rows."""
    for row in rows:
        value = cleaner(row.get(column))
        if value is not None:
            return value
    return None


def _total(rows, column):
    """Sum a per-truck money column across the job. None if none of them had
    a figure — a job with no freight recorded is not a job costing zero."""
    values = [clean_number(row.get(column)) for row in rows]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


#--------------------------------------
# building the rows
#--------------------------------------

def build_rows(created_by_id):
    df = read_logistics_sheet(SHEET_SHIFTING)

    consignment_rows = []
    vehicle_rows = []

    for index, rows in enumerate(_group(df)):
        consignment_id = index + 1

        consignment_rows.append((
            consignment_id,
            _first(rows, "Movement Type", map_movement_type),
            _first(rows, "Requester", map_source) or "manual",
            None,                                        # source_ref
            Json([]),                                    # taken_snapshot
            _first(rows, "Execution Date", clean_date_any),
            _first(rows, "Transporter", clean_text),
            None,                                        # shifting_type
            _first(rows, "Item Name", clean_text),
            _first(rows, "Pickup Point", clean_text),
            _first(rows, "Destination", clean_text),
            _first(rows, "Shipment Ref. / IDM #", clean_text),
            _total(rows, "Quoted Freight (Rs.)"),
            _total(rows, "Actual Freight (Rs.)"),
            _first(rows, "Payment Terms", map_payment_status),
            None,                                        # paid_amount
            _total(rows, "Detention Amount"),
            _first(rows, "Dispatch Note Date", clean_date),
            _first(rows, "ETA Works / ETA Destination", clean_date_any),
            _first(rows, "Remarks", clean_text),
            created_by_id,
            False,                                       # is_deleted
        ))

        for row in rows:
            packages, _ = parse_qty_uom(row.get("Qty. / No. of Packages"))
            vehicle_rows.append((
                consignment_id,
                clean_text(row.get("Vehicle Number")),
                clean_text(row.get("Vehicle Type")),
                int(packages) if packages is not None else None,
                clean_text(row.get("Driver #")),
                None,                                    # net_weight
                clean_number(row.get("Gross Weight (Kgs)")),
                clean_text(row.get("Container Number")),
                container_type_of(row),
                map_tracking_status(row.get("Tracking Status")),
                Json([]),                                # package_refs
                Json([]),                                # import_consignment_refs
                False,                                   # is_deleted
            ))

    return consignment_rows, vehicle_rows


#--------------------------------------
# the loader
#--------------------------------------

def load_trucking(conn):
    created_by_id = admin_id(conn)

    consignment_rows, vehicle_rows = build_rows(created_by_id)

    # Intra-factory moves are a second sheet feeding the same tables; their ids
    # continue the sequence so both sets share one id space.
    intra_consignments, intra_vehicles = build_intrafactory_rows(
        created_by_id, len(consignment_rows) + 1
    )
    consignment_rows += intra_consignments
    vehicle_rows += intra_vehicles

    bulk_insert(conn, "trucking_consignments", CONSIGNMENT_COLUMNS, consignment_rows)
    bulk_insert(conn, "trucking_vehicles", VEHICLE_COLUMNS, vehicle_rows)

    bump_sequence(conn, "trucking_consignments")
    bump_sequence(conn, "trucking_vehicles")

    # A job is closed when every one of its vehicles is Delivered AND it is
    # submitted (helpers.is_closed). That depends on rows inserted a moment
    # ago, so it can't be a value written inline with the header — it has to
    # be a pass over both tables once they exist.
    mark_closed_jobs(conn)

    inbound = sum(1 for r in consignment_rows if r[1] == "Inbound")
    outbound = sum(1 for r in consignment_rows if r[1] == "Outbound")
    intra = sum(1 for r in consignment_rows if r[1] == "Intrafactory")
    delivered = sum(1 for r in vehicle_rows if r[9] == "Delivered")

    print(f"Trucking jobs : inserted {len(consignment_rows)} rows "
          f"({inbound} inbound, {outbound} outbound, {intra} intra-factory, "
          f"{len(consignment_rows) - inbound - outbound - intra} untyped)")
    print(f"Trucking vehicles : inserted {len(vehicle_rows)} rows "
          f"({delivered} delivered)")


#--------------------------------------
# INTRA-FACTORY MOVES
#
# A SEPARATE SHEET, a different shape, the same table. Moving material between
# Qadri's own sites is trucking like any other, so it belongs in
# trucking_consignments — but the sheet does not look like the inbound/outbound
# one and cannot be read by the same code:
#
#   * no Movement Type column   — the sheet IS the movement type
#   * Sender / Receiver         — not Pickup Point / Destination
#   * one 'T/ Freight - Rs.'    — not a quoted/actual pair, so there is no
#                                 saving to compute and quoted stays NULL
#                                 rather than being set equal to actual
#   * no containers, no ETA, no dispatch note
#
# Every one of those columns is nullable on the model, so this needs no schema
# change — the gap was purely that nothing ever read the sheet. 875 rows and
# Rs 17.5m of freight were simply invisible.
#
# ONE ROW IS ONE JOB. Bilty numbers are near-unique (824 distinct across 862
# non-blank), unlike the inbound/outbound sheet where several trucks share a
# shipment reference. So these are not grouped — grouping on a Bilty '-' would
# merge 39 unrelated moves into a single job.
#--------------------------------------

# The sheet writes both 'Other' and 'Others' for the same thing. Left unmapped,
# the 72 'Other' rows would fall through to NULL — the same duplicate-spelling
# problem the logistics status vocabulary already guards against.
SHIFTING_TYPES = {
    "regular": "Regular",
    "special": "Special",
    "other": "Others",
    "others": "Others",
}

# A row with none of these is a spacer, not a movement.
_INTRA_SIGNAL_COLUMNS = (
    "Execution Date", "Sender", "Receiver", "Transporter",
    "Vehicle Number", "Item Details", "Bilty #",
)


def map_shifting_type(value):
    s = clean_text(value)
    return SHIFTING_TYPES.get(s.strip().lower()) if s else None


def build_intrafactory_rows(created_by_id, start_id):
    """(consignments, vehicles) for the intra-factory sheet, ids from start_id."""
    df = read_logistics_sheet(SHEET_INTRAFACTORY)

    consignment_rows = []
    vehicle_rows = []
    next_id = start_id

    for _, row in df.iterrows():
        if not any(clean_text(row.get(column)) for column in _INTRA_SIGNAL_COLUMNS):
            continue

        consignment_id = next_id
        next_id += 1

        consignment_rows.append((
            consignment_id,
            "Intrafactory",                              # the sheet IS the type
            # 'Requester' here is a PERSON (Manan, Ahtsham, ...), not a
            # handing-over module, so source stays manual — intra-factory work
            # is internal and nobody hands it over.
            "manual",
            None,                                        # source_ref
            Json([]),                                    # taken_snapshot
            clean_date_any(row.get("Execution Date")),
            clean_text(row.get("Transporter")),
            map_shifting_type(row.get("Shifting Type")),
            clean_text(row.get("Item Details")),
            clean_text(row.get("Sender")),               # pickup
            clean_text(row.get("Receiver")),             # destination
            clean_text(row.get("Bilty #")),              # reference_no
            None,                                        # quoted_freight
            clean_number(row.get("T/ Freight - Rs.")),   # actual_freight
            # 'Bill Status' says whether the BILL was cleared, which is not the
            # payment-terms vocabulary this column holds elsewhere. Left NULL
            # rather than mapped onto a term it does not mean.
            None,                                        # payment_status
            None,                                        # paid_amount
            None,                                        # detention
            None,                                        # dispatch_note_date
            None,                                        # eta_works
            clean_text(row.get("Delay Reason")),         # remarks
            created_by_id,
            False,                                       # is_deleted
        ))

        vehicle_rows.append((
            consignment_id,
            clean_text(row.get("Vehicle Number")),
            clean_text(row.get("Vehicle Type")),
            None,                                        # no_of_packages
            None,                                        # driver_phone
            None,                                        # net_weight
            clean_number(row.get("Weight")),             # gross_weight
            None,                                        # container_no
            None,                                        # container_type
            map_tracking_status(row.get("Status")),
            Json([]),                                    # package_refs
            Json([]),                                    # import_consignment_refs
            False,                                       # is_deleted
        ))

    return consignment_rows, vehicle_rows
