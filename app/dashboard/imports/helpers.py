from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.imports.models import Consignment, ConsignmentItem
from app.masters.models import Supplier, Item, Branch


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
    query = select(Consignment).where(
        Consignment.is_deleted == False
    ).options(
        selectinload(Consignment.items),
        joinedload(Consignment.supplier),
        joinedload(Consignment.branch)
    )

    return db.execute(query).scalars().all()


def fetch_filtered_consigments(
        db,
        work, status, item_category,
        supplier, country, from_date,
        to_date, mode_of_shipment
    ):

    query = select(Consignment).where(
        Consignment.is_deleted == False
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

    return db.execute(query).scalars().all()



