from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, or_, func, case, desc
from sqlalchemy.orm import joinedload

from app.loading.schemas.stores_schemas import (
    Stock, Issuance, StoreRequisition, PurchasesData,
)
from app.masters.models import Item
from app.dashboard.period import coverage, DEAD_STOCK_WINDOW_DAYS
from app.dashboard.references import clamp, paginate, sql_search_clause

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
# PURCHASE vs ISSUANCE BY CATEGORY  (KPI document)
#
# What each item category cost to buy against what it cost to consume, over the
# same period. The two sides come from different tables (`purchases_data` and
# `issuance`), so they are summed separately in SQL and joined on the category
# afterwards — issuance alone is ~49k rows and must never be materialized here.
#
# Only the branch and category filters are applied: `item` and `search` filter
# the STOCK screen, and carrying them across would silently narrow one side of
# the comparison without narrowing the other.
#
# A category present on one side and absent on the other still appears, with
# zero on the missing side — that gap is exactly what the chart is for.
#-------------------------------------

UNCATEGORISED = "Uncategorised"


def _category_totals(db, model, amount_column, date_column, item_category,
                     date_from, date_to):
    label = func.coalesce(Item.category, UNCATEGORISED)

    query = (
        select(label, func.coalesce(func.sum(amount_column), 0))
        .select_from(model)
        .outerjoin(Item, Item.item_code == model.item_code)
        .group_by(label)
    )

    if item_category:
        query = query.where(Item.category.in_(item_category))

    if date_from is not None and date_to is not None:
        query = query.where(date_column.between(date_from, date_to))

    return dict(db.execute(query).all())


def _comparable_window(db):
    # The two tables do not cover the same period: purchases_data currently
    # holds ONE MONTH (2026-06-09 to 2026-07-09) while issuance holds a full
    # YEAR. Summing each in full would compare a month of buying against a year
    # of consuming and report every category as consuming ~10x what it buys —
    # a conclusion about the data's coverage, dressed up as one about the
    # business.
    #
    # So both sides are clipped to the window they SHARE. The window is derived
    # rather than hard-coded, so it stays correct when more purchase history is
    # loaded (at which point it simply widens).
    p_min, p_max = db.execute(
        select(func.min(PurchasesData.purchase), func.max(PurchasesData.purchase))
    ).one()
    i_min, i_max = db.execute(
        select(func.min(Issuance.from_date), func.max(Issuance.from_date))
    ).one()

    if None in (p_min, p_max, i_min, i_max):
        return None, None

    start, end = max(p_min, i_min), min(p_max, i_max)
    if start > end:
        # No overlap at all — better to compare nothing than to compare
        # disjoint periods.
        return None, None

    return start, end


def purchase_vs_issuance_by_category(db, item_category=None, limit=10):
    # NOTE: deliberately NOT filtered by branch. `purchases_data.branch` holds
    # short codes ('QEN', 'QCL', 'QB2', …) while `issuance.branch` and
    # `stock.branch` hold full company names ('Qadri Engineering (Pvt) Ltd.').
    # The two vocabularies share no values, so a branch filter would match the
    # issuance side and silently match NOTHING on the purchases side — giving a
    # chart that reports a category as pure consumption with zero spend, which
    # is false. Company-wide and honest beats filtered and wrong.
    #
    # Mapping the codes to names is not something to guess at (QE / QEN / QE-II
    # are not self-evident); it belongs in the loader, agreed with the business.
    date_from, date_to = _comparable_window(db)

    purchased = _category_totals(
        db, PurchasesData, PurchasesData.amount, PurchasesData.purchase,
        item_category, date_from, date_to,
    )
    issued = _category_totals(
        db, Issuance, Issuance.total_price, Issuance.from_date,
        item_category, date_from, date_to,
    )

    rows = []
    for category in set(purchased) | set(issued):
        rows.append({
            "category": category,
            "purchased": purchased.get(category, Decimal("0")),
            "issued": issued.get(category, Decimal("0")),
        })

    # Ranked by the larger of the two sides, so a category that is huge on
    # consumption but barely purchased (or the reverse) still makes the chart —
    # ranking on purchases alone would hide exactly the imbalances worth seeing.
    rows.sort(key=lambda r: max(r["purchased"], r["issued"]), reverse=True)

    for row in rows:
        row["net"] = row["purchased"] - row["issued"]

    return {
        "categories_total": len(rows),
        "rows": rows[:limit],
        # The shared window both sides were clipped to. Returned so the chart
        # can be labelled with the period it actually describes — without it a
        # reader assumes the figures cover everything loaded, which they do not.
        "period": {"from": date_from, "to": date_to},
        # Tells the front end to label this chart "all branches" even when a
        # branch filter is active on the rest of the screen, so the mismatch is
        # visible rather than mistaken for filtered data.
        "branch_filtered": False,
    }


#-------------------------------------
# ISSUANCE PER (ITEM, BRANCH) OVER THE TWO REPORTING WINDOWS
#
# One query returns both the 12-month and the 3-month issued VALUE per stock
# line. Everything on the screen that talks about movement is derived from these
# two numbers — the issuance KPIs, the fast/slow/dead split, dead stock and the
# stock-days runway — so those figures are guaranteed to agree with each other.
#
# The windows END AT THE LATEST ISSUANCE IN THE DATA, not at today. The data is
# historical; anchoring to today would measure a window that is partly empty and
# report healthy items as dead. The resolved window is returned so the screen
# can state the dates it actually used.
#-------------------------------------

# Shared with the Overview dashboard's dead-stock default (see
# app.dashboard.period.DEAD_STOCK_WINDOW_DAYS) — the two screens' definitions
# used to disagree on this number, so it now lives in one place for both.
MONTHS_12_DAYS = DEAD_STOCK_WINDOW_DAYS
MONTHS_3_DAYS = 92


def issuance_windows(db):
    """({(item_code, branch): {"v12", "v3"}}, window_info)"""
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()

    if latest is None:
        return {}, {"latest": None, "from_12m": None, "from_3m": None,
                    "days_12m": MONTHS_12_DAYS, "days_3m": MONTHS_3_DAYS}

    from_12m = latest - timedelta(days=MONTHS_12_DAYS)
    from_3m = latest - timedelta(days=MONTHS_3_DAYS)

    rows = db.execute(
        select(
            Issuance.item_code,
            Issuance.branch,
            func.coalesce(
                func.sum(func.coalesce(Issuance.total_price, 0)), 0
            ).label("v12"),
            func.coalesce(
                func.sum(
                    case((Issuance.from_date >= from_3m,
                          func.coalesce(Issuance.total_price, 0)), else_=0)
                ), 0
            ).label("v3"),
        )
        .where(Issuance.item_code.isnot(None))
        .where(Issuance.from_date.between(from_12m, latest))
        .group_by(Issuance.item_code, Issuance.branch)
    ).all()

    by_key = {
        (item_code, branch): {"v12": v12 or Decimal("0"), "v3": v3 or Decimal("0")}
        for item_code, branch, v12, v3 in rows
    }

    return by_key, {
        "latest": latest,
        "from_12m": from_12m,
        "from_3m": from_3m,
        "days_12m": MONTHS_12_DAYS,
        "days_3m": MONTHS_3_DAYS,
    }


#-------------------------------------
# ISSUANCE PER ITEM, FOLDED ACROSS EVERY BRANCH — NOT JUST STOCKED ONES
#
# issuance_windows() keys by (item_code, branch), and group_by_item only ever
# looks a key up for branches that appear in the STOCK table. An item issued
# at a branch with no remaining stock row for it (912 item codes, as of this
# writing) was therefore invisible to the company-wide fold entirely — its
# issuance silently understated, and for the fast/slow/dead split specifically,
# sometimes called dead despite having genuinely moved within the window.
#
# This is the item-level twin, grouped by item_code alone, used for every
# figure that counts ITEMS rather than (item, branch) stock lines — which is
# every company-wide figure on the screen (movement_split, movement_kpis, the
# dead/fast/slow reference lists, the issued_12m/issued_3m badges). The
# per-branch view (serialize_row, movement_by_branch) correctly keeps using
# issuance_windows' narrower map instead — "is THIS branch's stock moving"
# should only count what THIS branch issued.
#-------------------------------------

def issuance_totals_by_item(db, branch=None):
    """{item_code: {"v12", "v3"}} — issuance value over the two windows,
    folded across every branch that issued the item, not just the ones the
    Stock table still has a row for.

    `branch` scopes this to match whatever the caller already filtered the
    stock rows to (the same list `fetch_filtered_stock` takes) — omitted, it
    folds across the whole company, which is correct for the unfiltered
    screen but WRONG once a branch filter is active: without this, an item
    would read as "moving" here because of activity at a branch the current
    view has filtered out entirely.
    """
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()
    if latest is None:
        return {}

    from_12m = latest - timedelta(days=MONTHS_12_DAYS)
    from_3m = latest - timedelta(days=MONTHS_3_DAYS)

    query = (
        select(
            Issuance.item_code,
            func.coalesce(
                func.sum(func.coalesce(Issuance.total_price, 0)), 0
            ).label("v12"),
            func.coalesce(
                func.sum(
                    case((Issuance.from_date >= from_3m,
                          func.coalesce(Issuance.total_price, 0)), else_=0)
                ), 0
            ).label("v3"),
        )
        .where(Issuance.item_code.isnot(None))
        .where(Issuance.from_date.between(from_12m, latest))
    )

    if branch:
        query = query.where(Issuance.branch.in_(branch))

    rows = db.execute(query.group_by(Issuance.item_code)).all()

    return {
        item_code: {"v12": v12 or Decimal("0"), "v3": v3 or Decimal("0")}
        for item_code, v12, v3 in rows
    }


#-------------------------------------
# PURCHASES BRANCH CODE -> STOCK/ISSUANCE BRANCH NAME
#
# purchases_data.branch holds short codes; stock/issuance.branch holds full
# company names, and the two vocabularies do not otherwise line up (see
# purchase_vs_issuance_by_category's identical note). Confirmed by the
# business, not derived — cross-matching item codes the way the AB-items
# branch map is (etl_common / load_05_stock.py) does not work here, because
# purchases and stock cover different populations of items (stock is a
# snapshot; purchases accumulate for years). The best match found that way
# was 41.7%, nowhere near the ~100% that made the AB mapping trustworthy.
#
# Only the four codes with a confirmed branch are here. QBL, QE-II and IOL
# are deliberately absent: QBL may be a different Qadri Brothers site than
# the Unit-II we hold stock data for, QE-II has no confirmed match, and IOL
# is not a branch at all. By instruction, ANY cross-sheet calculation against
# purchases_data must filter to ONLY the branches below — a purchase row
# under an unmapped code is invisible to it, the same as if it did not exist.
#-------------------------------------

PURCHASES_BRANCH_TO_STOCK_BRANCH = {
    "QCL": "Qadcast (Pvt) Ltd.",
    "QE": "Qadbros Engineering (Pvt) Ltd.",
    "QEN": "Qadri Engineering (Pvt) Ltd.",
    "QB2": "Qadri Brothers (Pvt.) Ltd. (Unit-II)",
}


#-------------------------------------
# MOST RECENT PURCHASE DATE, PER (ITEM, BRANCH)
#
# An item bought yesterday has not been issued yet for the obvious reason that
# nobody has had the chance — that is not the same thing as dead stock, which
# is about stock nobody WANTS. derive_movement uses this to hold off calling an
# item dead until more than a year has passed since it was last purchased, the
# same 365-day boundary issuance already uses (see MONTHS_12_DAYS).
#-------------------------------------

def latest_purchase_map(db):
    """{(item_code, branch): most recent purchase date} — branch is the
    STOCK/ISSUANCE name, translated via PURCHASES_BRANCH_TO_STOCK_BRANCH. Rows
    under an unmapped code are excluded outright, per that mapping's docstring."""
    rows = db.execute(
        select(
            PurchasesData.item_code, PurchasesData.branch,
            func.max(PurchasesData.purchase),
        )
        .where(PurchasesData.item_code.isnot(None))
        .where(PurchasesData.branch.in_(PURCHASES_BRANCH_TO_STOCK_BRANCH))
        .group_by(PurchasesData.item_code, PurchasesData.branch)
    ).all()

    result = {}
    for item_code, code, purchased in rows:
        if not purchased:
            continue
        key = (item_code, PURCHASES_BRANCH_TO_STOCK_BRANCH[code])
        if key not in result or purchased > result[key]:
            result[key] = purchased

    return result


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


#-----------------------------------------------------
# ISSUANCE IN A PERIOD
#
# Replaces the fixed 12-month and 3-month issuance tiles. Those two answered one
# question at two arbitrary window lengths, neither of which anybody chose, and
# a reader could not ask "what went out THIS month" — the thing a storekeeper
# actually wants — without doing arithmetic in their head.
#
# One tile with its own date filter, defaulting to the current month like every
# other window on the system. Items are counted BY ITEM CODE, folded across the
# branches that issued them, exactly as the rest of this screen counts items and
# exactly as the Overview's Stores section does — so "633 items" is one number
# wherever it appears.
#
# The 12-month figures have NOT gone away: the movement classification (fast /
# slow / dead) and the days-of-stock runway are still built on them. They are
# just no longer shown as tiles of their own, because the movement split says
# the same thing with a reason attached.
#-----------------------------------------------------

def issuance_in_period(db, date_from, date_to, branch=None, category=None):
    """{value, items, lines, quantity} for what was issued in the window."""
    conditions = [Issuance.from_date.between(date_from, date_to)]
    if branch:
        conditions.append(Issuance.branch.in_(branch))

    value, items, lines, quantity = db.execute(
        select(
            func.coalesce(func.sum(Issuance.total_price), 0),
            func.count(func.distinct(Issuance.item_code)),
            func.count(Issuance.id),
            func.coalesce(func.sum(Issuance.quantity), 0),
        ).where(*conditions)
    ).one()

    return {"value": value, "items": items, "lines": lines, "quantity": quantity}


def issuance_item_references(db, date_from, date_to, branch=None,
                             page=None, page_size=None, search=None):
    """The items issued in the window, biggest value first, with quantities.

    Grouped onto the item code rather than listed line by line: the tile counts
    items, so its drill-down has to as well or the two disagree. Quantity
    travels with the value because an issuance is a physical movement — how much
    left the store is half of what was asked.
    """
    conditions = [Issuance.from_date.between(date_from, date_to),
                  Issuance.item_code.isnot(None)]
    if branch:
        conditions.append(Issuance.branch.in_(branch))

    clause = sql_search_clause(search, Issuance.item_code, Issuance.item_name)
    if clause is not None:
        conditions.append(clause)

    total = db.execute(
        select(func.count(func.distinct(Issuance.item_code))).where(*conditions)
    ).scalar()

    page, size = clamp(page, page_size)
    rows = db.execute(
        select(
            Issuance.item_code,
            func.min(Issuance.item_name),
            func.coalesce(func.sum(Issuance.quantity), 0),
            func.count(Issuance.id),
            func.coalesce(func.sum(Issuance.total_price), 0).label("value"),
        )
        .where(*conditions)
        .group_by(Issuance.item_code)
        .order_by(desc("value"), Issuance.item_code)
        .offset((page - 1) * size).limit(size)
    ).all()

    def money(amount):
        v = float(amount or 0)
        if abs(v) >= 1_000_000_000:
            return f"Rs {v / 1_000_000_000:.2f}B"
        if abs(v) >= 1_000_000:
            return f"Rs {v / 1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"Rs {v / 1_000:.0f}K"
        return f"Rs {v:,.0f}"

    def qty(value):
        number = float(value or 0)
        return f"{number:,.0f}" if number.is_integer() else f"{number:,.3f}".rstrip("0").rstrip(".")

    items = [
        {
            "id": code,
            "reference": code,
            "detail": name,
            "meta": f"{qty(quantity)} issued over {lines} line{'' if lines == 1 else 's'}",
            "badge": money(value),
        }
        for code, name, quantity, lines, value in rows
    ]

    return paginate(items, page, size, total=total or 0)


def issuance_coverage(db, date_from, date_to):
    earliest, latest, total = db.execute(
        select(func.min(Issuance.from_date), func.max(Issuance.from_date),
               func.count(Issuance.id))
    ).one()
    in_period = db.execute(
        select(func.count(Issuance.id))
        .where(Issuance.from_date.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, "issuance date")
