from sqlalchemy import select, or_, func
from sqlalchemy.orm import joinedload
from app.loading.schemas.stores_schemas import PurchasesData
from app.masters.models import Item
from app.dashboard.period import coverage, PURCHASES_DATE_DEFAULT

# The two real procurement events. "What did we commit to in August" and "what
# did we spend in August" are different questions, both are fully populated,
# and which one a screen means is a business choice — so the caller picks
# rather than the backend deciding. Looked up through this map, never
# interpolated, so an unknown name cannot reach SQL.
DATE_FIELDS = {
    "po_date": PurchasesData.po_date,
    "purchase": PurchasesData.purchase,
}
# Defined once in app/dashboard/period, so this screen and the Overview
# cannot default to different dates for the same figure again.
DATE_FIELD_DEFAULT = PURCHASES_DATE_DEFAULT

DATE_FIELD_OPTIONS = [
    {"value": "po_date", "label": "PO date (ordered)"},
    {"value": "purchase", "label": "Purchase date (bought)"},
]


def date_column(field):
    return DATE_FIELDS.get(field or DATE_FIELD_DEFAULT,
                           DATE_FIELDS[DATE_FIELD_DEFAULT])


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

def source_coverage(db, date_from, date_to, date_field=None):
    """What the table holds, and how much of it the chosen window catches.

    Reported so an empty period is explained rather than shown as a confident
    Rs 0 — purchases currently stop in January, so the default (this month) is
    legitimately empty and the screen has to be able to say so.
    """
    column = date_column(date_field)
    label = "PO date" if (date_field or DATE_FIELD_DEFAULT) == "po_date" else "purchase date"

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column), func.count(PurchasesData.id))
    ).one()

    in_period = db.execute(
        select(func.count(PurchasesData.id))
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


def fetch_filtered_consignments(
        db, supplier, branch, item_category, mop,
        sourcing_o, po_from_date, po_to_date, search,
        date_from=None, date_to=None, date_field=None
    ):

    query = select(PurchasesData).options(joinedload(PurchasesData.item))

    # The dashboard-wide reporting window, applied to the PURCHASE date (when
    # the money was actually spent), not the PO date. po_from_date/po_to_date
    # remain a separate, explicit filter on the PO date for anyone who wants it.
    if date_from is not None and date_to is not None:
        query = query.where(date_column(date_field).between(date_from, date_to))

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
