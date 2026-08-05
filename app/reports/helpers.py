from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.imports.models import Consignment, ConsignmentItem
from app.logistics.models import LogisticsConsignment
from app.loading.schemas.stores_schemas import (
    PurchasesData, Stock, StoreRequisition,
)
from app.masters.models import Branch, Item, Supplier
from app.reports.models import SavedReport

# Reuse the inventory dashboard's reorder-level tuning so a reorder figure in a
# report matches the same figure on the dashboard.
from app.dashboard.inventory.helpers import (
    DEMAND_WINDOW_DAYS, DEFAULT_LEAD_TIME_DAYS, SAFETY_FACTOR,
)


#-----------------------------------------------------
# THE FOUR REPORT TYPES
#
# Fixed order — the cross-type result is these tables concatenated in this
# order, and pagination walks the concatenation. Keep it stable so a given page
# number always means the same slice.
#-----------------------------------------------------

TYPE_ORDER = ["purchases", "imports", "inventory", "logistics"]

# Which of the shared filters each type can honour. A type that cannot honour an
# active filter is dropped from the result entirely (it produces no rows), which
# mirrors the front end: a logistics row has no branch, so filtering by branch
# hides logistics. `search` is honoured by every type and is not listed here.
FILTER_SUPPORT = {
    "purchases": {"item", "shaft", "supplier", "branch", "category", "date"},
    "imports":   {"shaft", "supplier", "branch", "category", "date"},
    "inventory": {"item", "shaft", "branch", "category"},
    "logistics": {"date"},
}


# The "shaft" filter is a curated, STATIC list of item names — the only shaft
# items that appear in the data. These live in the imports item lines (not in the
# purchases/stock tables), so `shaft` is its own filter matched against item
# names across every item-carrying type (purchases, imports via its lines,
# inventory) — NOT folded into `item`, which supports only purchases/inventory.
SHAFT_ITEMS = [
    "Forged Alloy Steel Round Bar",
    "Forged Steel Hollow Drill Bars",
    "Forged Steel Alloy Round Bar",
    "Forged Steel Round Bar",
]


@dataclass
class Filters:
    # The dropdown filters are multi-select (repeated query params) → matched
    # with IN. An empty/None list means "not filtered". Date range and search
    # stay single-valued.
    item: Optional[list[str]] = None
    shaft: Optional[list[str]] = None
    supplier: Optional[list[str]] = None
    branch: Optional[list[str]] = None
    category: Optional[list[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None

    def active_names(self):
        # The filters that narrow which TYPES apply (search is excluded — it
        # narrows rows within a type, never a whole type). Empty lists are
        # falsy, so an unset multi-select does not count as active.
        names = set()
        if self.item:
            names.add("item")
        if self.shaft:
            names.add("shaft")
        if self.supplier:
            names.add("supplier")
        if self.branch:
            names.add("branch")
        if self.category:
            names.add("category")
        if self.date_from or self.date_to:
            names.add("date")
        return names


def type_included(report_type, filters):
    return filters.active_names().issubset(FILTER_SUPPORT[report_type])


def selected_types(types):
    # None / empty means all four.
    if not types:
        return list(TYPE_ORDER)
    return [t for t in TYPE_ORDER if t in types]


def _like(term):
    return "%" + term.strip() + "%"


#-----------------------------------------------------
# PER-TYPE WHERE CLAUSES
#
# Each returns a list of conditions, applied to both the count and the page
# fetch so they always agree. Only the filters a type supports are read; the
# caller has already dropped the type if an unsupported filter is active.
#-----------------------------------------------------

def _purchases_conditions(f):
    conds = []
    if f.item:
        conds.append(PurchasesData.item_name.in_(f.item))
    if f.shaft:
        conds.append(PurchasesData.item_name.in_(f.shaft))
    if f.supplier:
        conds.append(PurchasesData.supplier.in_(f.supplier))
    if f.branch:
        conds.append(PurchasesData.branch.in_(f.branch))
    if f.category:
        conds.append(PurchasesData.item.has(Item.category.in_(f.category)))
    if f.date_from:
        conds.append(PurchasesData.purchase >= f.date_from)
    if f.date_to:
        conds.append(PurchasesData.purchase <= f.date_to)
    if f.search:
        p = _like(f.search)
        conds.append(or_(
            PurchasesData.item_name.ilike(p),
            PurchasesData.po_number.ilike(p),
            PurchasesData.ref_no.ilike(p),
            PurchasesData.supplier.ilike(p),
            PurchasesData.bill_no.ilike(p),
        ))
    return conds


def _imports_conditions(f):
    conds = [Consignment.is_deleted == False]  # noqa: E712
    if f.shaft:
        conds.append(Consignment.items.any(
            (ConsignmentItem.is_deleted == False) &  # noqa: E712
            ConsignmentItem.item_name.in_(f.shaft)
        ))
    if f.supplier:
        conds.append(Consignment.supplier.has(Supplier.name.in_(f.supplier)))
    if f.branch:
        conds.append(Consignment.branch.has(Branch.name.in_(f.branch)))
    if f.category:
        conds.append(Consignment.items.any(
            (ConsignmentItem.is_deleted == False) &  # noqa: E712
            ConsignmentItem.item.has(Item.category.in_(f.category))
        ))
    if f.date_from:
        conds.append(Consignment.requisition_date >= f.date_from)
    if f.date_to:
        conds.append(Consignment.requisition_date <= f.date_to)
    if f.search:
        p = _like(f.search)
        conds.append(or_(
            Consignment.instrument_number.ilike(p),
            Consignment.origin.ilike(p),
            Consignment.gd_number.ilike(p),
            Consignment.supplier.has(Supplier.name.ilike(p)),
        ))
    return conds


def _inventory_conditions(f):
    conds = []
    if f.item:
        conds.append(Stock.item_name.in_(f.item))
    if f.shaft:
        conds.append(Stock.item_name.in_(f.shaft))
    if f.branch:
        conds.append(Stock.branch.in_(f.branch))
    if f.category:
        conds.append(Stock.item.has(Item.category.in_(f.category)))
    if f.search:
        p = _like(f.search)
        conds.append(or_(
            Stock.item_name.ilike(p),
            Stock.item_code.ilike(p),
            Stock.branch.ilike(p),
        ))
    return conds


def _logistics_conditions(f):
    conds = [LogisticsConsignment.is_deleted == False]  # noqa: E712
    if f.date_from:
        conds.append(LogisticsConsignment.port_in_date >= f.date_from)
    if f.date_to:
        conds.append(LogisticsConsignment.port_in_date <= f.date_to)
    if f.search:
        p = _like(f.search)
        conds.append(or_(
            LogisticsConsignment.mo_no.ilike(p),
            LogisticsConsignment.customer_name.ilike(p),
            LogisticsConsignment.pod.ilike(p),
            LogisticsConsignment.shipping_line.ilike(p),
            LogisticsConsignment.origin_country.ilike(p),
        ))
    return conds


_MODEL = {
    "purchases": PurchasesData,
    "imports": Consignment,
    "inventory": Stock,
    "logistics": LogisticsConsignment,
}

_CONDITIONS = {
    "purchases": _purchases_conditions,
    "imports": _imports_conditions,
    "inventory": _inventory_conditions,
    "logistics": _logistics_conditions,
}

# The eager loads each type's row serializer needs (master names, item lines).
_OPTIONS = {
    "purchases": lambda: (joinedload(PurchasesData.item),),
    "imports": lambda: (
        joinedload(Consignment.branch),
        joinedload(Consignment.supplier),
        selectinload(Consignment.items).joinedload(ConsignmentItem.item),
    ),
    "inventory": lambda: (joinedload(Stock.item),),
    "logistics": lambda: (selectinload(LogisticsConsignment.items),),
}


def conditions_for(report_type, filters):
    return _CONDITIONS[report_type](filters)


def count_for(db, report_type, conds):
    model = _MODEL[report_type]
    stmt = select(func.count()).select_from(model)
    if conds:
        stmt = stmt.where(*conds)
    return db.execute(stmt).scalar() or 0


def fetch_slice(db, report_type, conds, offset, limit):
    model = _MODEL[report_type]
    stmt = select(model).options(*_OPTIONS[report_type]())
    if conds:
        stmt = stmt.where(*conds)
    stmt = stmt.order_by(model.id).offset(offset).limit(limit)
    return db.execute(stmt).scalars().unique().all()


def fetch_all(db, report_type, conds, cap):
    # For export: the whole filtered set, capped so a runaway filter can't pull
    # the entire database into memory.
    model = _MODEL[report_type]
    stmt = select(model).options(*_OPTIONS[report_type]())
    if conds:
        stmt = stmt.where(*conds)
    stmt = stmt.order_by(model.id).limit(cap)
    return db.execute(stmt).scalars().unique().all()


#-----------------------------------------------------
# CROSS-TYPE PAGINATION
#
# The result is the selected types concatenated in TYPE_ORDER. Given the global
# offset/limit, work out which types the page slice falls in and the sub-offset
# and sub-limit within each, so only the rows on the page are ever fetched.
#-----------------------------------------------------

def plan_slices(counts_ordered, offset, limit):
    plan = []
    need = limit
    pos = 0  # global index where the current type starts

    for report_type, count in counts_ordered:
        if need <= 0:
            break
        if count <= 0 or offset >= pos + count:
            pos += count
            continue
        sub_offset = max(0, offset - pos)
        take = min(count - sub_offset, need)
        if take > 0:
            plan.append((report_type, sub_offset, take))
            need -= take
        pos += count

    return plan


#-----------------------------------------------------
# SCOPED INVENTORY MAPS
#
# The reorder level (from requisitions) and consumption rate (from issuance)
# are per (item_code, branch). The dashboard builds them for the whole table;
# here they are scoped to just the item codes on the page, so a paged report
# never scans every requisition/issuance row.
#-----------------------------------------------------

def reorder_levels_for(db, item_codes):
    codes = [c for c in item_codes if c]
    if not codes:
        return {}

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
        ).where(StoreRequisition.item_code.in_(codes))
    ).all()

    demand = {}
    lead_sum = {}
    lead_count = {}

    for item_code, branch, prepare_date, stock_in_date, req_quantity in rows:
        key = (item_code, branch)
        if prepare_date and window_start <= prepare_date <= latest and req_quantity:
            demand[key] = demand.get(key, Decimal("0")) + req_quantity
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
# FILTER OPTION LISTS
#
# Distinct values for the dropdowns, scoped to the selected types and built from
# the whole tables (so a dropdown shows every value, not just the current page).
#-----------------------------------------------------

def _distinct(db, column, extra=None):
    stmt = select(column).distinct()
    if extra is not None:
        stmt = stmt.where(extra)
    return [v for (v,) in db.execute(stmt).all() if v]


def build_options(db, types):
    items = set()
    suppliers = set()
    branches = set()
    categories = set()

    if "purchases" in types:
        items.update(_distinct(db, PurchasesData.item_name))
        suppliers.update(_distinct(db, PurchasesData.supplier))
        branches.update(_distinct(db, PurchasesData.branch))
    if "inventory" in types:
        items.update(_distinct(db, Stock.item_name))
        branches.update(_distinct(db, Stock.branch))
    if "imports" in types:
        suppliers.update(_distinct(
            db, Supplier.name, Supplier.consignments.any(Consignment.is_deleted == False)  # noqa: E712
        ))
        branches.update(_distinct(
            db, Branch.name, Branch.consignments.any(Consignment.is_deleted == False)  # noqa: E712
        ))

    # Category always comes from the Item master, shared by every type.
    if types:
        categories.update(_distinct(db, Item.category))

    # Shafts are a static, curated list of item names — meaningful for the
    # item-carrying types (purchases, imports, inventory).
    shafts = SHAFT_ITEMS if ({"purchases", "imports", "inventory"} & set(types)) else []

    return {
        "items": sorted(items),
        "shafts": list(shafts),
        "suppliers": sorted(suppliers),
        "branches": sorted(branches),
        "categories": sorted(categories),
    }


#-----------------------------------------------------
# SAVED-REPORT CRUD
#-----------------------------------------------------

def list_saved(db):
    stmt = (
        select(SavedReport)
        .where(SavedReport.is_deleted == False)  # noqa: E712
        .options(joinedload(SavedReport.created_by))
        .order_by(SavedReport.created_at.desc(), SavedReport.id.desc())
    )
    return db.execute(stmt).scalars().all()


def get_saved(db, report_id):
    stmt = (
        select(SavedReport)
        .where(SavedReport.id == report_id, SavedReport.is_deleted == False)  # noqa: E712
        .options(joinedload(SavedReport.created_by))
    )
    return db.execute(stmt).scalar_one_or_none()


def create_saved(db, data, user):
    saved = SavedReport(
        name=data.name,
        types=data.types,
        columns=data.columns,
        filters=data.filters,
        created_by_id=user.id,
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def update_saved(db, saved, data):
    saved.name = data.name
    saved.types = data.types
    saved.columns = data.columns
    saved.filters = data.filters
    db.commit()
    db.refresh(saved)
    return saved


def delete_saved(db, saved, user):
    saved.is_deleted = True
    saved.deleted_at = datetime.now(timezone.utc)
    saved.deleted_by_id = user.id
    db.commit()
