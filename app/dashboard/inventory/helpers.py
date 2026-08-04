from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, or_, func
from sqlalchemy.orm import joinedload

from app.loading.schemas.stores_schemas import Stock, Issuance, StoreRequisition
from app.masters.models import Item

# How far back the consumption rate for the runway is measured.
CONSUMPTION_WINDOW_DAYS = 90

# Reorder level is derived from store requisitions:
#   reorder level = avg daily demand x lead time x (1 + safety factor)
# Demand is the requisitioned quantity over the window; lead time is how long
# a requisition took to come into stock; the safety factor is a buffer.
DEMAND_WINDOW_DAYS = 180
DEFAULT_LEAD_TIME_DAYS = 30
SAFETY_FACTOR = Decimal("0.2")


#-------------------------------------
# FETCH EVERY STOCK ROW
#
# Used to build the filter option lists (branches, items, categories) from the
# whole table, so the dropdowns show every value. The item master is
# joined-loaded for its category and specification.
#-------------------------------------

def fetch_stock(db):
    query = select(Stock).options(joinedload(Stock.item))
    return db.execute(query).scalars().all()


#-------------------------------------
# FILTER OPTION LISTS (cheap DISTINCT queries)
#
# The dropdowns only need distinct values, so they are read with small DISTINCT
# queries instead of materializing every stock row as an ORM object with its
# item joined-loaded. (fetch_stock stays for anything that genuinely needs the
# rows; the dashboard route no longer uses it just for the dropdowns.)
#-------------------------------------

def option_lists(db):
    branches = sorted(v for (v,) in db.execute(select(Stock.branch).distinct()).all() if v)
    items = sorted(v for (v,) in db.execute(select(Stock.item_name).distinct()).all() if v)
    item_categories = sorted(
        v for (v,) in db.execute(
            select(Item.category)
            .join(Stock, Stock.item_code == Item.item_code)
            .distinct()
        ).all() if v
    )
    return {
        "branches": branches,
        "items": items,
        "item_categories": item_categories,
    }


#-------------------------------------
# FETCH THE FILTERED STOCK ROWS
#
# branch / item / category are multi-select (IN). Category lives on the item
# master, so it is filtered through the relationship with .has(). Stock status
# and reorder status are derived, so they are filtered in the route after the
# rows are serialized.
#-------------------------------------

def fetch_filtered_stock(db, branch, item, item_category, search):
    query = select(Stock).options(joinedload(Stock.item))

    if branch:
        query = query.where(Stock.branch.in_(branch))

    if item:
        query = query.where(Stock.item_name.in_(item))

    if item_category:
        query = query.where(Stock.item.has(Item.category.in_(item_category)))

    if search:
        pattern = "%" + search.strip() + "%"
        query = query.where(
            or_(
                Stock.item_name.ilike(pattern),
                Stock.item_code.ilike(pattern),
                Stock.branch.ilike(pattern),
            )
        )

    return db.execute(query).scalars().all()


#-------------------------------------
# AVERAGE DAILY CONSUMPTION PER (ITEM, BRANCH)
#
# From issuance history over the last window, ending at the most recent
# issuance date in the data (the data is historical, so "today" may be empty).
# Feeds days_of_stock (runway = available / avg daily consumption).
#-------------------------------------

def consumption_map(db):
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()
    if latest is None:
        return {}

    start = latest - timedelta(days=CONSUMPTION_WINDOW_DAYS)

    rows = db.execute(
        select(
            Issuance.item_code,
            Issuance.branch,
            func.sum(Issuance.quantity),
        )
        .where(Issuance.from_date >= start)
        .where(Issuance.from_date <= latest)
        .where(Issuance.quantity.isnot(None))
        .group_by(Issuance.item_code, Issuance.branch)
    ).all()

    window = Decimal(CONSUMPTION_WINDOW_DAYS)
    result = {}
    for item_code, branch, total in rows:
        if total is None:
            continue
        result[(item_code, branch)] = Decimal(str(total)) / window

    return result


#-------------------------------------
# DERIVED REORDER LEVEL PER (ITEM, BRANCH)
#
# From store requisitions:
#   reorder level = avg daily demand x lead time x (1 + safety factor)
#
#   * avg daily demand = requisitioned quantity over the last window (ending at
#     the latest prepare_date in the data) / window days
#   * lead time        = average of stock_in_date - prepare_date, per item;
#     falls back to a default when no completed cycle exists
#
# Computed for every item+branch that has demand in the window. Items with no
# requisition demand are absent, so the caller falls back to the stored
# reorder_level column for those.
#-------------------------------------

def reorder_level_map(db):
    latest = db.execute(select(func.max(StoreRequisition.prepare_date))).scalar()
    if latest is None:
        return {}

    window_start = latest - timedelta(days=DEMAND_WINDOW_DAYS)

    rows = db.execute(
        select(
            StoreRequisition.item_code,
            StoreRequisition.branch,
            StoreRequisition.prepare_date,
            StoreRequisition.stock_in_date,
            StoreRequisition.req_quantity,
        )
    ).all()

    demand = {}
    lead_sum = {}
    lead_count = {}

    for item_code, branch, prepare_date, stock_in_date, req_quantity in rows:
        key = (item_code, branch)

        # Demand within the window.
        if prepare_date and window_start <= prepare_date <= latest and req_quantity:
            demand[key] = demand.get(key, Decimal("0")) + req_quantity

        # Lead time, from any completed prepare -> stock-in cycle.
        if prepare_date and stock_in_date and stock_in_date >= prepare_date:
            lead_sum[key] = lead_sum.get(key, 0) + (stock_in_date - prepare_date).days
            lead_count[key] = lead_count.get(key, 0) + 1

    window = Decimal(DEMAND_WINDOW_DAYS)
    default_lead = Decimal(DEFAULT_LEAD_TIME_DAYS)
    buffer_multiplier = Decimal("1") + SAFETY_FACTOR

    result = {}
    for key, total in demand.items():
        if total <= 0:
            continue
        avg_daily = total / window
        lead = (Decimal(lead_sum[key]) / Decimal(lead_count[key])) if lead_count.get(key) else default_lead
        result[key] = (avg_daily * lead * buffer_multiplier).quantize(Decimal("0.001"))

    return result
