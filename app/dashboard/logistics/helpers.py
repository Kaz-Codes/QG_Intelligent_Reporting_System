from sqlalchemy import select, or_, func
from sqlalchemy.orm import joinedload, selectinload

from app.logistics.models import LogisticsConsignment, LogisticsPackage
from app.trucking.models import TruckingConsignment
from app.dashboard.period import coverage

# The label the screen uses for an order that does not say whether it is local
# or export. A real bucket, not a filter for "everything".
NOT_STATED = "Not stated"

# A trucking job whose movement type the sheet never gave. Its own bucket
# rather than being folded into Inbound or Outbound — there is no way to tell
# which it was, and guessing would corrupt the split permanently.
UNCLASSIFIED = "Unclassified"


#=====================================================
# EACH TAB HAS ITS OWN DATE, AND ITS OWN CHOICE OF DATE
#
# The three tabs measure three different events, and two of them have two
# candidate dates the business genuinely uses — so the CALLER picks, exactly as
# the Overview's sections do. Filtering shipments on departure and on arrival
# are different questions ("what sailed in August" against "what landed in
# August") and neither is the obviously right default for everyone.
#
# Looked up through these maps rather than interpolated, so an unknown field
# name can never reach SQL.
#=====================================================

SHIPMENT_DATE_FIELDS = {
    "etd": LogisticsConsignment.etd_sailing_date,
    "eta": LogisticsConsignment.actual_arrival_date,
}
SHIPMENT_DATE_DEFAULT = "etd"
SHIPMENT_DATE_OPTIONS = [
    {"value": "etd", "label": "ETD (sailing)"},
    {"value": "eta", "label": "ETA (arrival)"},
]

PACKING_DATE_FIELDS = {
    "packed": LogisticsPackage.packing_date,
    "rfd": LogisticsPackage.packing_ready_date,
}
PACKING_DATE_DEFAULT = "packed"
PACKING_DATE_OPTIONS = [
    {"value": "packed", "label": "Packed date"},
    {"value": "rfd", "label": "Ready-for-dispatch date"},
]

# Trucking carries the movement itself. Same pair, and the same labels, as the
# Overview's logistics section — so a figure can be compared across the two.
TRANSPORT_DATE_FIELDS = {
    "etd": TruckingConsignment.execution_date,
    "eta": TruckingConsignment.eta_works,
}
TRANSPORT_DATE_DEFAULT = "etd"
TRANSPORT_DATE_OPTIONS = [
    {"value": "etd", "label": "ETD (execution)"},
    {"value": "eta", "label": "ETA (arrival at works)"},
]


def _column(fields, default, field):
    return fields.get(field or default, fields[default])


def shipment_date_column(field):
    return _column(SHIPMENT_DATE_FIELDS, SHIPMENT_DATE_DEFAULT, field)


def packing_date_column(field):
    return _column(PACKING_DATE_FIELDS, PACKING_DATE_DEFAULT, field)


def transport_date_column(field):
    return _column(TRANSPORT_DATE_FIELDS, TRANSPORT_DATE_DEFAULT, field)


def _coverage(db, model, column, date_from, date_to, label, extra=None):
    """What this source holds against what the window caught."""
    conditions = [model.is_deleted == False]
    if extra is not None:
        conditions.append(extra)

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column), func.count(model.id))
        .where(*conditions)
    ).one()
    in_period = db.execute(
        select(func.count(model.id)).where(*conditions)
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


def shipments_coverage(db, date_from, date_to, date_field=None):
    label = "ETD (sailing)" if (date_field or SHIPMENT_DATE_DEFAULT) == "etd" else "ETA (arrival)"
    return _coverage(db, LogisticsConsignment, shipment_date_column(date_field),
                     date_from, date_to, label)


def packing_coverage(db, date_from, date_to, date_field=None):
    label = "packed date" if (date_field or PACKING_DATE_DEFAULT) == "packed" else "ready-for-dispatch date"
    return _coverage(db, LogisticsPackage, packing_date_column(date_field),
                     date_from, date_to, label)


def transport_coverage(db, date_from, date_to, date_field=None):
    label = "ETD (execution)" if (date_field or TRANSPORT_DATE_DEFAULT) == "etd" else "ETA (arrival at works)"
    return _coverage(db, TruckingConsignment, transport_date_column(date_field),
                     date_from, date_to, label)


#=====================================================
# SHIPMENTS  (LogisticsConsignment)
#=====================================================

def fetch_orders(db):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.is_deleted == False
    # Containers are eager-loaded too: the container-type usage chart reads
    # them, and without this every order would lazy-load its own.
    ).options(
        selectinload(LogisticsConsignment.items),
        selectinload(LogisticsConsignment.containers),
    )
    return db.execute(query).scalars().all()


def fetch_filtered_orders(db, status, shipping_line, country, customer,
                          etd_from, etd_to, search,
                          date_from=None, date_to=None, date_field=None,
                          order_type=None):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.is_deleted == False
    # Containers are eager-loaded too: the container-type usage chart reads
    # them, and without this every order would lazy-load its own.
    ).options(
        selectinload(LogisticsConsignment.items),
        selectinload(LogisticsConsignment.containers),
    )

    if status:
        query = query.where(LogisticsConsignment.current_status.in_(status))
    if shipping_line:
        query = query.where(LogisticsConsignment.shipping_line.in_(shipping_line))
    if country:
        query = query.where(LogisticsConsignment.origin_country.in_(country))
    if customer:
        query = query.where(LogisticsConsignment.customer_name.in_(customer))
    # Local against export. 392 of 745 orders do not state it, so the screen
    # offers "Not stated" as a real choice rather than pretending the column is
    # complete — see the data note this drives.
    if order_type:
        wanted = [t for t in order_type if t != NOT_STATED]
        clauses = []
        if wanted:
            clauses.append(LogisticsConsignment.order_type.in_(wanted))
        if NOT_STATED in order_type:
            clauses.append(LogisticsConsignment.order_type.is_(None))
        if clauses:
            query = query.where(or_(*clauses))
    # The dashboard-wide window, on the caller's chosen date. etd_from/etd_to
    # stay as the screen's own explicit range on the port-in date.
    if date_from is not None and date_to is not None:
        query = query.where(shipment_date_column(date_field).between(date_from, date_to))
    if etd_from:
        query = query.where(LogisticsConsignment.port_in_date >= etd_from)
    if etd_to:
        query = query.where(LogisticsConsignment.port_in_date <= etd_to)
    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(
                LogisticsConsignment.mo_no.ilike(pattern),
                LogisticsConsignment.customer_name.ilike(pattern),
                LogisticsConsignment.origin_country.ilike(pattern),
            )
        )

    return db.execute(query).scalars().all()


#=====================================================
# PACKING  (LogisticsPackage + its order)
#=====================================================

def fetch_packages(db):
    query = select(LogisticsPackage).where(
        LogisticsPackage.is_deleted == False
    ).options(joinedload(LogisticsPackage.consignment))
    return db.execute(query).scalars().all()


def fetch_filtered_packages(db, status, works, product_category,
                            business_type, customer, packing_from,
                            packing_to, search,
                            date_from=None, date_to=None, date_field=None):
    query = select(LogisticsPackage).where(
        LogisticsPackage.is_deleted == False
    ).options(joinedload(LogisticsPackage.consignment))

    if status:
        query = query.where(LogisticsPackage.status.in_(status))
    if works:
        query = query.where(LogisticsPackage.packing_works.in_(works))
    if packing_from:
        query = query.where(LogisticsPackage.packing_date >= packing_from)
    if packing_to:
        query = query.where(LogisticsPackage.packing_date <= packing_to)

    # Order-level filters go through the relationship.
    if product_category:
        query = query.where(
            LogisticsPackage.consignment.has(LogisticsConsignment.department.in_(product_category))
        )
    if business_type:
        query = query.where(
            LogisticsPackage.consignment.has(LogisticsConsignment.order_type.in_(business_type))
        )
    if customer:
        query = query.where(
            LogisticsPackage.consignment.has(LogisticsConsignment.customer_name.in_(customer))
        )

    # The dashboard-wide window, on the caller's chosen packing date.
    if date_from is not None and date_to is not None:
        query = query.where(packing_date_column(date_field).between(date_from, date_to))

    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(
                LogisticsPackage.colour_code.ilike(pattern),
                LogisticsPackage.consignment.has(
                    or_(
                        LogisticsConsignment.customer_name.ilike(pattern),
                        LogisticsConsignment.department.ilike(pattern),
                    )
                ),
            )
        )

    return db.execute(query).scalars().all()


#=====================================================
# TRANSPORT  (TruckingConsignment — export trucking)
#=====================================================

def fetch_trucking(db):
    query = select(TruckingConsignment).where(
        TruckingConsignment.is_deleted == False
    ).options(selectinload(TruckingConsignment.vehicles))
    return db.execute(query).scalars().all()


def fetch_filtered_trucking(db, movement_type, source, payment_status,
                            transporter, exec_from, exec_to, search,
                            date_from=None, date_to=None, date_field=None):
    query = select(TruckingConsignment).where(
        TruckingConsignment.is_deleted == False
    ).options(selectinload(TruckingConsignment.vehicles))

    # Intra-factory moves have no movement type on the sheet — it IS the sheet —
    # so they arrive labelled, while 207 inbound/outbound rows genuinely say
    # nothing and stay Unclassified. Both are real answers; neither is a filter
    # for "everything".
    if movement_type:
        wanted = [m for m in movement_type if m != UNCLASSIFIED]
        clauses = []
        if wanted:
            clauses.append(TruckingConsignment.movement_type.in_(wanted))
        if UNCLASSIFIED in movement_type:
            clauses.append(TruckingConsignment.movement_type.is_(None))
        if clauses:
            query = query.where(or_(*clauses))
    if source:
        query = query.where(TruckingConsignment.source.in_(source))
    if payment_status:
        query = query.where(TruckingConsignment.payment_status.in_(payment_status))
    if transporter:
        query = query.where(TruckingConsignment.transporter_name.in_(transporter))
    # The dashboard-wide window, on the caller's chosen date. exec_from/exec_to
    # stay as the screen's own explicit execution-date range.
    if date_from is not None and date_to is not None:
        query = query.where(transport_date_column(date_field).between(date_from, date_to))
    if exec_from:
        query = query.where(TruckingConsignment.execution_date >= exec_from)
    if exec_to:
        query = query.where(TruckingConsignment.execution_date <= exec_to)
    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(
                TruckingConsignment.transporter_name.ilike(pattern),
                TruckingConsignment.destination.ilike(pattern),
                TruckingConsignment.item_details.ilike(pattern),
            )
        )

    return db.execute(query).scalars().all()


def logistics_links(db, jobs):
    """{logistics order id (str) -> {customer, city, province}} for the jobs
    that came from a logistics order (source 'from-logistics', source_ref = the
    order id). Customer/city/province live on the order, not the trucking job —
    a local logistics consignment handed to trucking carries them here."""
    ref_ids = {
        j.source_ref for j in jobs
        if j.source == "from-logistics" and j.source_ref
    }

    int_ids = []
    for ref in ref_ids:
        try:
            int_ids.append(int(ref))
        except (TypeError, ValueError):
            continue

    if not int_ids:
        return {}

    rows = db.execute(
        select(
            LogisticsConsignment.id,
            LogisticsConsignment.customer_name,
            LogisticsConsignment.origin_city,
            LogisticsConsignment.origin_province,
        ).where(LogisticsConsignment.id.in_(int_ids))
    ).all()

    return {
        str(order_id): {"customer": customer, "city": city, "province": province}
        for order_id, customer, city, province in rows
    }
