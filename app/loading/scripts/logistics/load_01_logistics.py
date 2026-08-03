"""
Load logistics orders and everything that hangs off them.

Four tables in one pass, because the items, packages and containers all point
back at a consignment id and that id is assigned here:

    logistics_consignments   the order header, merged from the shipment and
                             packing sheets (one order can appear on both)
    logistics_items          one row per job on the order
    logistics_packages       one row per packing record
    logistics_containers     expanded from the shipment sheet's per-type counts

Merging: the shipment sheet describes the shipping leg and the packing sheet
describes what went into the boxes. An order that appears on both contributes
to one header — shipment values win for the shipping fields, packing values
win for the packing fields, and neither overwrites the other with a blank.
See logistics_common for why the join is on the normalised export number
rather than the sheet's own 'Primary Key' column.

Packing rows with no export number are local sugar and cement work; each one
becomes an order of its own (logistics_common.build_order_index).
"""

from psycopg2.extras import Json

from app.loading.scripts.etl_common import (
    bulk_insert, clean_date, clean_date_any, clean_int, clean_number,
    clean_status, clean_text, parse_qty_uom,
)
from app.loading.scripts.logistics.logistics_common import (
    SHEET_EXPORT_DOCS, SHEET_PACKING, SHEET_SHIPMENT, admin_id,
    build_order_index, bump_sequence, read_logistics_sheet, row_key,
)

DEFAULT_STATUS = "Under Production"
DEFAULT_PACKING_STATUS = "Packing under manufacturing"

# Matches String(100) on LogisticsItem.job_no.
_JOB_NO_MAX = 100

# The workbook's own vocabulary, tidied to one spelling. Anything not listed
# is passed through as typed rather than being dropped.
STATUS_MAP = {
    "delivered": "Delivered",
    "sailing": "Sailing",
    "at qfl": "At QFL",
    "at port": "At Port",
    "gate out": "Gate Out",
    "packed": "Packed",
    "pending": DEFAULT_STATUS,
}

# Each shipment row carries a COUNT per container type, not one row per
# container. The table wants a row per container, so a count of 3 becomes
# three rows carrying the type and no number (the workbook has no per-
# container numbers on this sheet).
CONTAINER_COLUMNS = {
    "Standard Containers 20'": "20' Standard",
    "Open Top Containers 20'": "20' Open Top",
    "Flat Rack Containers 20'": "20' Flat Rack",
    "Out of Gauge Containers 20'": "20' Out of Gauge",
    "Standard Containers 40'": "40' Standard",
    "Open Top Containers 40'": "40' Open Top",
    "Flat Rack Containers 40'": "40' Flat Rack",
    "Out of Gauge Containers 40'": "40' Out of Gauge",
    "LCL": "LCL",
    "AIR": "AIR",
}

# A count above this is a data-entry slip (a weight or an amount typed into a
# container column); expanding it would write thousands of phantom rows.
MAX_CONTAINERS_PER_ORDER = 60

CONSIGNMENT_COLUMNS = [
    "id", "order_type", "department",
    "origin_country", "origin_city", "origin_province",
    "customer_name", "mo_no", "batch_no", "batch_label", "incoterm",
    "pol", "pod", "shipping_line", "clearing_agent", "booking_no",
    "port_in_date", "etd_sailing_date", "cro_arrival_date", "actual_arrival_date",
    "packing_cost", "transportation_charges", "container_detention", "insurance",
    "trucking_lhr_to_khi", "fumigation_cost", "lashing", "qfl_charges",
    "qfl_container_movement", "custom_clearance_charges", "port_charges",
    "dhl_charges", "sea_air_freight",
    "current_status", "effective_date", "gate_out_date", "sent_to_trucking",
    "remarks_log", "created_by_id", "is_deleted",
]

ITEM_COLUMNS = [
    "consignment_id", "job_no", "item_detail", "quantity", "unit_weight",
    "gross_weight", "planned_rfd_date", "actual_rfd_date", "rfd_history",
    "is_deleted",
]

PACKAGE_COLUMNS = [
    "consignment_id", "colour_code", "packing_works", "packing_ready_date",
    "packing_date", "quoted_packing_cost", "actual_packing_cost",
    "gross_weight", "status", "allocations", "is_deleted",
]

CONTAINER_COLUMNS_DB = [
    "consignment_id", "container_no", "container_type", "is_deleted",
]


#--------------------------------------
# small value mappers
#--------------------------------------

def map_status(value, default=DEFAULT_STATUS):
    s = clean_status(value)
    if not s:
        return default
    return STATUS_MAP.get(s.strip().lower(), s.strip())


def map_order_type(value):
    """Business Type -> the order_type the model expects.

    'Dispatched' is a progress state in the workbook, not a kind of order, so
    it tells us nothing here and is left unset.
    """
    s = clean_text(value)
    if not s:
        return None
    s = s.lower()
    if s == "export":
        return "Export"
    if s == "local":
        return "Local"
    return None


def _clean_customer(value):
    """Customer names carry trailing newlines from the workbook."""
    s = clean_text(value)
    return " ".join(s.split()) if s else None


class _Header:
    """One order being assembled from however many sheets mention it.

    set() never lets a blank overwrite something already known, so whichever
    sheet happens to be read first does not decide the outcome.
    """

    def __init__(self, consignment_id):
        self.id = consignment_id
        self.values = {}

    def set(self, field, value):
        if value is None:
            return
        if self.values.get(field) is None:
            self.values[field] = value

    def get(self, field, default=None):
        value = self.values.get(field)
        return default if value is None else value


#--------------------------------------
# the shipment sheet -> header + containers
#--------------------------------------

def _apply_shipment(header, row):
    header.set("order_type", "Export")
    header.set("customer_name", _clean_customer(row.get("Customer")))
    header.set("origin_country", clean_text(row.get("Country")))
    header.set("pod", clean_text(row.get("POD")))
    header.set("incoterm", clean_text(row.get("Shipment Terms")))
    header.set("shipping_line", clean_text(row.get("S/Line")))
    header.set("clearing_agent", clean_text(row.get("C/Agent")))
    header.set("booking_no", clean_text(row.get("CRO #")))

    header.set("port_in_date", clean_date_any(row.get("Port-In Dt.")))
    header.set("etd_sailing_date", clean_date_any(row.get("ETD Karachi")))
    header.set("cro_arrival_date", clean_date_any(row.get("CRO Arrival Dt.")))
    header.set("actual_arrival_date", clean_date_any(row.get("Actual Arrival Dt.")))

    header.set("packing_cost", clean_number(row.get("Packing Cost")))
    header.set("trucking_lhr_to_khi", clean_number(row.get("LHR ~ KHI")))
    header.set("fumigation_cost", clean_number(row.get("Fumigation")))
    header.set("lashing", clean_number(row.get("Lashing")))
    header.set("qfl_charges", clean_number(row.get("QFL Cost")))
    header.set("qfl_container_movement", clean_number(row.get("QFL ~ Port")))
    header.set("custom_clearance_charges", clean_number(row.get("Clearance Cost")))
    header.set("port_charges", clean_number(row.get("Wharfage")))
    header.set("dhl_charges", clean_number(row.get("DHL Charges")))
    header.set("insurance", clean_number(row.get("Insurance")))
    header.set("sea_air_freight", clean_number(row.get("Sea Freight")))

    status = clean_status(row.get("Shipment Status"))
    if status:
        header.set("current_status", map_status(status))
        header.set("effective_date", clean_date_any(row.get("Actual Arrival Dt.")))


def _containers_from(row, consignment_id):
    rows = []
    for column, label in CONTAINER_COLUMNS.items():
        count = clean_int(row.get(column))
        if not count or count <= 0:
            continue
        for _ in range(min(count, MAX_CONTAINERS_PER_ORDER)):
            rows.append((consignment_id, None, label, False))
    return rows


#--------------------------------------
# the packing sheet -> header + items + packages
#--------------------------------------

def _apply_packing(header, row):
    header.set("order_type", map_order_type(row.get("Business Type")))
    header.set("department", clean_text(row.get("Product Category")))
    header.set("customer_name", _clean_customer(row.get("Customer")))
    header.set("gate_out_date", clean_date_any(row.get("Gate Out Date")))

    status = clean_status(row.get("Packing Status"))
    if status:
        header.set("current_status", map_status(status))


#--------------------------------------
# the export-documentation sheet -> header only
#--------------------------------------

def _apply_export_docs(header, row):
    """Fill in from the paperwork sheet.

    Only the order-level fields it carries, because those are the only ones the
    schema has columns for. Its 22 per-document status columns (customs /
    customer / bank paperwork) are NOT loaded — no model holds a document
    status, and the schema is authoritative, so that data is dropped rather
    than given a table of its own.

    Reading the sheet still matters: ~49 exports appear here and nowhere else,
    so without this they would be headers with nothing on them at all.
    """
    header.set("order_type", "Export")
    header.set("customer_name", _clean_customer(row.get("Customer")))
    header.set("incoterm", clean_text(row.get("Shipping Term")))
    header.set("clearing_agent", clean_text(row.get("Shipping Agent")))
    header.set("etd_sailing_date", clean_date_any(row.get("Sailing Date")))
    header.set("gate_out_date", clean_date_any(row.get("Gate-Out Date")))


def _item_from(row, consignment_id, job_column, detail_column,
               qty_column, gross_column, planned_column, actual_column):
    job = clean_text(row.get(job_column))
    detail = clean_text(row.get(detail_column))
    quantity, _ = parse_qty_uom(row.get(qty_column))

    if not (job or detail or quantity):
        return None

    # job_no is String(100) in the model. Three packing rows type a whole run of
    # jobs into one cell as a joined list ("FLMX-0004+0005+0006+..."), the
    # longest 154 characters. Trim to fit the column rather than widen it - an
    # over-length value aborts the whole logistics_items insert.
    if job and len(job) > _JOB_NO_MAX:
        job = job[:_JOB_NO_MAX]

    return (
        consignment_id,
        job,
        " ".join(detail.split()) if detail else None,
        quantity,
        None,                                        # unit_weight: not in sheet
        clean_number(row.get(gross_column)),
        clean_date(row.get(planned_column)) if planned_column else None,
        clean_date(row.get(actual_column)) if actual_column else None,
        Json([]),                                    # rfd_history
        False,
    )


def _package_from(row, consignment_id):
    packages = clean_int(row.get("Pkgs."))
    # The sheet has two pairs of packing-cost columns and only one of them was
    # ever filled in: 'Quoted/Actual Packing Cost' are empty in all 1,375 rows,
    # while 'Packing Cost Budgeted' carries 27 figures. Read the budgeted
    # column first so those 27 are not thrown away, and keep the named pair as
    # a fallback for when the workbook starts using it.
    quoted = (
        clean_number(row.get("Quoted Packing Cost"))
        or clean_number(row.get("Packing Cost Budgeted"))
    )
    actual = (
        clean_number(row.get("Actual Packing Cost"))
        or clean_number(row.get("Packing Cost Actual"))
    )
    packing_date = clean_date(row.get("Actual Packing Date"))
    ready_date = clean_date(row.get("Actual RFD Date"))
    status = clean_status(row.get("Packing Status"))

    # Nothing about packing was recorded on this row - a package row here
    # would be an empty shell.
    if not any([packages, quoted, actual, packing_date, ready_date, status]):
        return None

    return (
        consignment_id,
        clean_text(row.get("Color Code")),
        clean_text(row.get("Works")),
        ready_date,
        packing_date,
        quoted,
        actual,
        clean_number(row.get("Gross Weight (Kgs)")),
        map_status(status, DEFAULT_PACKING_STATUS),
        Json([]),                                    # allocations
        False,
    )


#--------------------------------------
# building every row
#--------------------------------------

def build_rows(created_by_id):
    keyed, local = build_order_index()

    headers = {}

    def header_for(consignment_id):
        if consignment_id not in headers:
            headers[consignment_id] = _Header(consignment_id)
        return headers[consignment_id]

    # --- shipment sheet ---
    container_rows = []
    item_rows = []
    shipment = read_logistics_sheet(SHEET_SHIPMENT)

    for _, row in shipment.iterrows():
        key = row_key(row, SHEET_SHIPMENT)
        if key is None:
            continue
        consignment_id = keyed[key]
        header = header_for(consignment_id)
        _apply_shipment(header, row)
        container_rows.extend(_containers_from(row, consignment_id))

    # --- packing sheet ---
    package_rows = []
    packing = read_logistics_sheet(SHEET_PACKING)
    packed_orders = set()

    for index, row in packing.iterrows():
        key = row_key(row, SHEET_PACKING)
        consignment_id = keyed[key] if key is not None else local.get(index)
        if consignment_id is None:
            continue

        header = header_for(consignment_id)
        _apply_packing(header, row)
        packed_orders.add(consignment_id)

        item = _item_from(
            row, consignment_id,
            "Jobs #", "Description", "Qty.", "Gross Weight (Kgs)",
            "Target RFD", "Actual RFD Date",
        )
        if item:
            item_rows.append(item)

        package = _package_from(row, consignment_id)
        if package:
            package_rows.append(package)

    # --- export documentation sheet: order-level fields only ---
    export_docs = read_logistics_sheet(SHEET_EXPORT_DOCS)

    for _, row in export_docs.iterrows():
        key = row_key(row, SHEET_EXPORT_DOCS)
        if key is None:
            continue
        _apply_export_docs(header_for(keyed[key]), row)

    # --- items from the shipment sheet, only where packing has none ---
    # The packing sheet is the better source for what is on an order, so it is
    # used wherever it exists; the shipment sheet fills the orders it never
    # reached, which would otherwise have a header and nothing under it.
    for _, row in shipment.iterrows():
        key = row_key(row, SHEET_SHIPMENT)
        if key is None:
            continue
        consignment_id = keyed[key]
        if consignment_id in packed_orders:
            continue
        item = _item_from(
            row, consignment_id,
            "Job #", "Description", "Pkgs.", "G.W. - Kgs", None, None,
        )
        if item:
            item_rows.append(item)

    # --- headers, in id order ---
    key_by_id = {cid: key for key, cid in keyed.items()}
    consignment_rows = []

    for consignment_id in sorted(headers):
        header = headers[consignment_id]
        key = key_by_id.get(consignment_id)
        exp_no, batch = key if key else (None, "")

        consignment_rows.append((
            consignment_id,
            header.get("order_type"),
            header.get("department"),
            header.get("origin_country"),
            None,                                    # origin_city
            None,                                    # origin_province
            header.get("customer_name"),
            exp_no,                                  # mo_no: the export number
            clean_int(batch),                        # batch_no
            batch or None,                           # batch_label
            header.get("incoterm"),
            None,                                    # pol: not in the workbook
            header.get("pod"),
            header.get("shipping_line"),
            header.get("clearing_agent"),
            header.get("booking_no"),
            header.get("port_in_date"),
            header.get("etd_sailing_date"),
            header.get("cro_arrival_date"),
            header.get("actual_arrival_date"),
            header.get("packing_cost"),
            header.get("transportation_charges"),
            header.get("container_detention"),
            header.get("insurance"),
            header.get("trucking_lhr_to_khi"),
            header.get("fumigation_cost"),
            header.get("lashing"),
            header.get("qfl_charges"),
            header.get("qfl_container_movement"),
            header.get("custom_clearance_charges"),
            header.get("port_charges"),
            header.get("dhl_charges"),
            header.get("sea_air_freight"),
            header.get("current_status", DEFAULT_STATUS),
            header.get("effective_date"),
            header.get("gate_out_date"),
            False,                                   # sent_to_trucking
            Json([]),                                # remarks_log
            created_by_id,
            False,                                   # is_deleted
        ))

    return consignment_rows, item_rows, package_rows, container_rows


#--------------------------------------
# the loader
#--------------------------------------

def load_logistics(conn):
    created_by_id = admin_id(conn)

    consignment_rows, item_rows, package_rows, container_rows = build_rows(
        created_by_id
    )

    bulk_insert(conn, "logistics_consignments", CONSIGNMENT_COLUMNS, consignment_rows)
    bulk_insert(conn, "logistics_items", ITEM_COLUMNS, item_rows)
    bulk_insert(conn, "logistics_packages", PACKAGE_COLUMNS, package_rows)
    bulk_insert(conn, "logistics_containers", CONTAINER_COLUMNS_DB, container_rows)

    bump_sequence(conn, "logistics_consignments")
    bump_sequence(conn, "logistics_items")
    bump_sequence(conn, "logistics_packages")
    bump_sequence(conn, "logistics_containers")

    exports = sum(1 for r in consignment_rows if r[1] == "Export")
    locals_ = sum(1 for r in consignment_rows if r[1] == "Local")
    print(f"Logistics orders : inserted {len(consignment_rows)} rows "
          f"({exports} export, {locals_} local, "
          f"{len(consignment_rows) - exports - locals_} untyped)")
    print(f"Logistics items : inserted {len(item_rows)} rows")
    print(f"Logistics packages : inserted {len(package_rows)} rows")
    print(f"Logistics containers : inserted {len(container_rows)} rows")
