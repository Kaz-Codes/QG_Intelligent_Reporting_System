from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload, selectinload

from app.logistics.models import LogisticsConsignment, LogisticsPackage
from app.trucking.models import TruckingConsignment


#=====================================================
# SHIPMENTS  (LogisticsConsignment)
#=====================================================

def fetch_orders(db):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.is_deleted == False
    ).options(selectinload(LogisticsConsignment.items))
    return db.execute(query).scalars().all()


def fetch_filtered_orders(db, status, shipping_line, country, customer,
                          etd_from, etd_to, search):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.is_deleted == False
    ).options(selectinload(LogisticsConsignment.items))

    if status:
        query = query.where(LogisticsConsignment.current_status.in_(status))
    if shipping_line:
        query = query.where(LogisticsConsignment.shipping_line.in_(shipping_line))
    if country:
        query = query.where(LogisticsConsignment.origin_country.in_(country))
    if customer:
        query = query.where(LogisticsConsignment.customer_name.in_(customer))
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
                            packing_to, search):
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
                            transporter, exec_from, exec_to, search):
    query = select(TruckingConsignment).where(
        TruckingConsignment.is_deleted == False
    ).options(selectinload(TruckingConsignment.vehicles))

    if movement_type:
        query = query.where(TruckingConsignment.movement_type.in_(movement_type))
    if source:
        query = query.where(TruckingConsignment.source.in_(source))
    if payment_status:
        query = query.where(TruckingConsignment.payment_status.in_(payment_status))
    if transporter:
        query = query.where(TruckingConsignment.transporter_name.in_(transporter))
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
