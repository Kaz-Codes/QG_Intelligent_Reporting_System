from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload
from app.loading.schemas.stores_schemas import PurchasesData
from app.masters.models import Item


#-------------------------------------
# FETCH EVERY PURCHASE ROW
#
# Used to build the filter option lists (so the dropdowns show every value,
# not just the ones on the current page). The item master is joined-loaded
# for its category.
#-------------------------------------

def fetch_consignments(db):
    query = select(PurchasesData).options(joinedload(PurchasesData.item))
    return db.execute(query).scalars().all()


#-------------------------------------
# FETCH THE FILTERED PURCHASE ROWS
#
# The multi-select filters are lists, applied as IN. Item category lives on
# the item master, so it is filtered through the relationship with .has().
# Status is derived (not a column), so it is filtered in the route after the
# rows are loaded.
#-------------------------------------

def fetch_filtered_consignments(
        db, supplier, branch, item_category, mop,
        sourcing_o, po_from_date, po_to_date, search
    ):

    query = select(PurchasesData).options(joinedload(PurchasesData.item))

    if supplier:
        query = query.where(PurchasesData.supplier.in_(supplier))

    if branch:
        query = query.where(PurchasesData.branch.in_(branch))

    if mop:
        query = query.where(PurchasesData.mop.in_(mop))

    if sourcing_o:
        query = query.where(PurchasesData.sourcing_o.in_(sourcing_o))

    if item_category:
        query = query.where(PurchasesData.item.has(Item.category.in_(item_category)))

    if po_from_date:
        query = query.where(PurchasesData.po_date >= po_from_date)

    if po_to_date:
        query = query.where(PurchasesData.po_date <= po_to_date)

    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(
                PurchasesData.item_name.ilike(pattern),
                PurchasesData.po_number.ilike(pattern),
                PurchasesData.ref_no.ilike(pattern),
                PurchasesData.supplier.ilike(pattern),
                PurchasesData.bill_no.ilike(pattern),
            )
        )

    return db.execute(query).scalars().all()
