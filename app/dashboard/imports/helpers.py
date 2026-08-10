from sqlalchemy import select, func
from sqlalchemy.orm import joinedload, selectinload

from app.imports.models import Consignment, ConsignmentItem
from app.masters.models import Supplier, Item, Branch
from app.enums import Status
from app.dashboard.period import coverage


#-------------------------------------
# FETCH THE CONSIGNMENTS THE IMPORTS
# DASHBOARD IS BUILT FROM
#
# Only live consignments count, a deleted one is not part of
# the picture. Items are loaded up front because the value of
# a consignment is worked out from its item lines, and the
# supplier and branch are loaded so they can be grouped by
# name without a query per row.
#-------------------------------------

def fetch_consignments(db):
    # The item MASTER is loaded behind each line as well — the route builds its
    # item_categories dropdown from item.item.category, which lazy-loaded one
    # query per line without this.
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).options(
        selectinload(Consignment.items).joinedload(ConsignmentItem.item),
        joinedload(Consignment.supplier),
        joinedload(Consignment.branch)
    )

    return db.execute(query).scalars().all()


def source_coverage(db, date_from, date_to):
    """What the consignments table holds, against what the window catches.

    Windowed on ETA Works — the arrival at the factory, which is the date the
    imports screen is about and the one the delivery-delay figure uses.
    """
    # Arrived-at-works rows are excluded here too, so the denominator matches
    # the population the screen actually shows.
    live = Consignment.current_status != Status.ARRIVED_AT_WORKS.value

    earliest, latest, total = db.execute(
        select(
            func.min(Consignment.eta_works),
            func.max(Consignment.eta_works),
            func.count(Consignment.id),
        ).where(Consignment.is_deleted == False).where(live)
    ).one()

    in_period = db.execute(
        select(func.count(Consignment.id))
        .where(Consignment.is_deleted == False)
        .where(live)
        .where(Consignment.eta_works.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, "ETA Works")


def fetch_filtered_consigments(
        db,
        work, status, item_category,
        supplier, country, from_date,
        to_date, mode_of_shipment,
        date_from=None, date_to=None
    ):

    # Same eager loading as fetch_consignments, plus the item MASTER behind each
    # line (category_delays reads item.item.category). Without these the value,
    # supplier and category figures lazy-load per row — an N+1 across the whole
    # filtered set, which was roughly half the response time before.
    # distinct() because the item_category / work / supplier filters join, and a
    # consignment with several matching lines would otherwise be counted once
    # per line in every figure on the screen.
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).where(
        # "Arrived at Works" is finished business. This is an OPERATIONAL
        # screen — what is still moving and what is late — so a consignment
        # that has landed drops off it entirely rather than padding every
        # count and diluting every delay percentage with work already done.
        Consignment.current_status != Status.ARRIVED_AT_WORKS.value
    ).options(
        selectinload(Consignment.items).joinedload(ConsignmentItem.item),
        joinedload(Consignment.supplier),
        joinedload(Consignment.branch)
    )

    if work:
        query = (
            query.join(Consignment.branch)
                 .where(Branch.name == work)
        )

    if status:
       query = query.where(
            Consignment.current_status == status
        )

    if item_category:
        query = (
            query.join(Consignment.items)
                 .join(ConsignmentItem.item)
                 .where(Item.category == item_category)
        )

    if supplier:
        query = (
            query.join(Consignment.supplier)
                 .where(Supplier.name == supplier)
        )

    if country:
        query = query.where(
            Consignment.origin == country
        )
        
    if from_date:
        query = query.where(Consignment.eta_works >= from_date)
    if to_date:
        query = query.where(Consignment.eta_works <= to_date)

    if mode_of_shipment:
        query = query.where(
            Consignment.mode_of_shipment == mode_of_shipment
        )

    # The dashboard-wide reporting window, on ETA Works. from_date/to_date above
    # stay as the screen's own explicit range filter.
    if date_from is not None and date_to is not None:
        query = query.where(Consignment.eta_works.between(date_from, date_to))

    return db.execute(query).unique().scalars().all()



