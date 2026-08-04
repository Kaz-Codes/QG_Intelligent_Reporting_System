from sqlalchemy import select, or_
from sqlalchemy.orm import joinedload
from app.loading.schemas.stores_schemas import PurchasesData
from app.masters.models import Item


#-------------------------------------
# FILTER OPTION LISTS (cheap DISTINCT queries)
#
# The dropdowns only need the distinct values, so they are read with five small
# DISTINCT queries instead of materializing every purchase row as an ORM object
# (131k+ objects with the item joined-loaded — that was the multi-second floor
# on every dashboard request, before a single aggregate was even computed).
#-------------------------------------

def _distinct(db, column):
    return sorted(v for (v,) in db.execute(select(column).distinct()).all() if v)


def option_lists(db):
    return {
        "suppliers": _distinct(db, PurchasesData.supplier),
        "branches": _distinct(db, PurchasesData.branch),
        "sourcing_officers": _distinct(db, PurchasesData.sourcing_o),
        "mops": _distinct(db, PurchasesData.mop),
        "item_categories": sorted(
            v for (v,) in db.execute(
                select(Item.category)
                .join(PurchasesData, PurchasesData.item_code == Item.item_code)
                .distinct()
            ).all() if v
        ),
    }


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
