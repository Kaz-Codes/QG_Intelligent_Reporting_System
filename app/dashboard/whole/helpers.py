from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, func, and_, or_, case

from app.imports.models import Consignment, ConsignmentItem
from app.imports.helpers import STAGE_GROUPS
from app.logistics.models import LogisticsConsignment
from app.trucking.models import TruckingConsignment
from app.loading.schemas.stores_schemas import (
    Stock, Issuance, PurchasesData,
)
from app.masters.models import Item
from app.enums import Status, JobKind
from app.reports.helpers import SHAFT_ITEMS

#-----------------------------------------------------
# OVERVIEW DASHBOARD QUERIES
#
# The overview reads from every module at once, so nothing here materializes ORM
# rows — each function is a single aggregate query returning scalars or a short
# grouped list. The largest table it touches (issuance, ~49k rows) is only ever
# summed in SQL.
#-----------------------------------------------------

# The two terminal import states. Everything else is "in process".
TERMINAL_STATUSES = [Status.ARRIVED_AT_WORKS.value, Status.ORDER_CANCELLED.value]

# How far back stock consumption is measured for the days-of-stock runway.
# Matches the inventory dashboard's window so the two agree.
CONSUMPTION_WINDOW_DAYS = 90


def _live_consignments():
    return Consignment.is_deleted.is_(False)


#-------------------------------------
# IMPORTS
#-------------------------------------

def imports_period_value(db, date_from, date_to):
    # Value booked against consignments whose ETD falls in the window. pkr_total
    # is stored (recomputed on save), never converted at a live rate.
    total, rows = db.execute(
        select(
            func.coalesce(func.sum(Consignment.pkr_total), 0),
            func.count(Consignment.id),
        )
        .where(_live_consignments())
        .where(Consignment.pkr_total.isnot(None))
        .where(Consignment.etd.between(date_from, date_to))
    ).one()

    return total, rows


def imports_value_without_etd(db):
    # Consignments carrying a value but no ETD. They cannot fall inside ANY
    # window, so every period figure above silently excludes them — currently
    # 24 consignments and a sixth of the book's value. Returned so the front end
    # can say so, rather than letting the money disappear between periods.
    return db.execute(
        select(
            func.count(Consignment.id),
            func.coalesce(func.sum(Consignment.pkr_total), 0),
        )
        .where(_live_consignments())
        .where(Consignment.pkr_total.isnot(None))
        .where(Consignment.etd.is_(None))
    ).one()


def imports_in_process_by_stage(db):
    # Counts per status, then rolled into the six pipeline stages the imports
    # list uses. Terminal statuses are excluded, so the "Closed" stage never
    # appears here by construction.
    status_counts = dict(
        db.execute(
            select(Consignment.current_status, func.count(Consignment.id))
            .where(_live_consignments())
            .where(Consignment.current_status.notin_(TERMINAL_STATUSES))
            .group_by(Consignment.current_status)
        ).all()
    )

    stage_counts = {}
    for stage, statuses in STAGE_GROUPS.items():
        if stage == "Closed":
            continue
        count = sum(status_counts.get(status, 0) for status in statuses)
        if count:
            stage_counts[stage] = count

    return stage_counts


def imports_shaft_counts(db):
    # Shafts are identified by the item NAME on the consignment line, not
    # through the item master: these names do not exist in `items`, and the line
    # keeps its own copy of the name anyway (rule 12), so the line is the only
    # reliable place to match them.
    name_match = or_(*[
        ConsignmentItem.item_name.ilike(f"%{name}%") for name in SHAFT_ITEMS
    ])

    shaft_consignments = (
        select(ConsignmentItem.consignment_id)
        .where(ConsignmentItem.is_deleted.is_(False))
        .where(name_match)
        .distinct()
        .scalar_subquery()
    )

    arrived, in_process = db.execute(
        select(
            func.count(case((Consignment.current_status.in_(TERMINAL_STATUSES), 1))),
            func.count(case((Consignment.current_status.notin_(TERMINAL_STATUSES), 1))),
        )
        .where(_live_consignments())
        .where(Consignment.id.in_(shaft_consignments))
    ).one()

    return in_process, arrived


#-------------------------------------
# LOCAL PROCUREMENT
#-------------------------------------

def procurement_period_totals(db, date_from, date_to):
    total, rows, quantity = db.execute(
        select(
            func.coalesce(func.sum(PurchasesData.amount), 0),
            func.count(PurchasesData.id),
            func.coalesce(func.sum(PurchasesData.qty), 0),
        )
        .where(PurchasesData.purchase.between(date_from, date_to))
    ).one()

    return total, rows, quantity


def procurement_category_totals(db, date_from, date_to):
    # Category lives on the item master, reached through item_code. Lines whose
    # item does not resolve are grouped as Uncategorised rather than dropped —
    # dropping them would make the category shares add up to less than the
    # period total shown beside them.
    rows = db.execute(
        select(
            func.coalesce(Item.category, "Uncategorised"),
            func.coalesce(func.sum(PurchasesData.amount), 0),
        )
        .select_from(PurchasesData)
        .outerjoin(Item, Item.item_code == PurchasesData.item_code)
        .where(PurchasesData.purchase.between(date_from, date_to))
        .group_by(func.coalesce(Item.category, "Uncategorised"))
    ).all()

    return {name: value for name, value in rows}


def procurement_delay(db, date_from, date_to):
    # A line is late when it was purchased after the date it was required.
    comparable, late = db.execute(
        select(
            func.count(PurchasesData.id),
            func.count(case((PurchasesData.required_d < PurchasesData.purchase, 1))),
        )
        .where(PurchasesData.purchase.between(date_from, date_to))
        .where(PurchasesData.required_d.isnot(None))
    ).one()

    return late, comparable


def procurement_cycle_times(db, date_from, date_to):
    # Average days from each candidate demand date to the purchase date. Rows
    # where the "demand" date sits after the purchase are excluded rather than
    # counted as negative lead time — they are data errors, and letting them in
    # would drag the average below what any real cycle took.
    in_window = PurchasesData.purchase.between(date_from, date_to)

    store_days, store_rows = db.execute(
        select(
            func.avg(PurchasesData.purchase - PurchasesData.ppc_store),
            func.count(PurchasesData.id),
        )
        .where(in_window)
        .where(PurchasesData.ppc_store.isnot(None))
        .where(PurchasesData.ppc_store <= PurchasesData.purchase)
    ).one()

    po_days, po_rows = db.execute(
        select(
            func.avg(PurchasesData.purchase - PurchasesData.po_date),
            func.count(PurchasesData.id),
        )
        .where(in_window)
        .where(PurchasesData.po_date.isnot(None))
        .where(PurchasesData.po_date <= PurchasesData.purchase)
    ).one()

    to_days = lambda v: round(float(v), 1) if v is not None else None
    return to_days(store_days), store_rows, to_days(po_days), po_rows


#-------------------------------------
# LOGISTICS
#-------------------------------------

def trucking_cost_by_movement(db):
    # Lifetime freight split by movement type. Grouped in SQL including the NULL
    # group, which is a real bucket here (191 jobs) and not an error to filter
    # away — see calculations.UNCLASSIFIED.
    return db.execute(
        select(
            TruckingConsignment.movement_type,
            func.count(TruckingConsignment.id),
            func.coalesce(func.sum(TruckingConsignment.actual_freight), 0),
            func.coalesce(func.sum(TruckingConsignment.quoted_freight), 0),
        )
        .where(TruckingConsignment.is_deleted.is_(False))
        .group_by(TruckingConsignment.movement_type)
    ).all()


def shipments_handled(db):
    # Export side is standard logistics orders only — rework service jobs are
    # not shipments handled for a customer, and job_kind is what separates them.
    export_orders = db.execute(
        select(func.count(LogisticsConsignment.id))
        .where(LogisticsConsignment.is_deleted.is_(False))
        .where(LogisticsConsignment.job_kind == JobKind.STANDARD.value)
    ).scalar_one()

    import_consignments = db.execute(
        select(func.count(Consignment.id)).where(_live_consignments())
    ).scalar_one()

    return export_orders, import_consignments


#-------------------------------------
# STORES
#-------------------------------------

def stock_totals(db):
    return db.execute(
        select(
            func.coalesce(func.sum(Stock.stock_qty_amount), 0),
            func.coalesce(func.sum(Stock.available_amount), 0),
            func.count(Stock.id),
        )
    ).one()


def stock_by_branch(db):
    return db.execute(
        select(
            Stock.branch,
            func.coalesce(func.sum(Stock.stock_qty_amount), 0),
            func.count(Stock.id),
        )
        .where(Stock.branch.isnot(None))
        .group_by(Stock.branch)
    ).all()


def consumption_by_branch(db, window_days=CONSUMPTION_WINDOW_DAYS):
    # Rupee value issued per branch over the window, ending at the most recent
    # issuance in the data rather than today — the data is historical, and
    # anchoring to today would measure an empty window and report every store as
    # having infinite runway.
    latest = db.execute(select(func.max(Issuance.from_date))).scalar()
    if latest is None:
        return {}, window_days

    start = latest - timedelta(days=window_days)

    rows = db.execute(
        select(
            Issuance.branch,
            func.coalesce(func.sum(Issuance.total_price), 0),
        )
        .where(Issuance.branch.isnot(None))
        .where(Issuance.from_date.between(start, latest))
        .group_by(Issuance.branch)
    ).all()

    return {branch: value for branch, value in rows}, window_days


def dead_stock(db, threshold_days):
    # A stock line is dead when it still carries value but nothing has been
    # issued against that (item, branch) within the threshold. Measured back
    # from the latest issuance in the data, for the same reason as above.
    #
    # history_days is returned alongside because the issuance table only spans
    # about a year: once the threshold reaches back past the first issuance
    # there is nothing left to distinguish "not issued lately" from "never
    # issued at all", and the figure stops responding to the threshold. The
    # caller needs that to know whether the number it got is meaningful.
    earliest, latest = db.execute(
        select(func.min(Issuance.from_date), func.max(Issuance.from_date))
    ).one()

    if latest is None:
        return 0, Decimal("0"), 0

    history_days = (latest - earliest).days if earliest else 0
    cutoff = latest - timedelta(days=threshold_days)

    recently_issued = (
        select(Issuance.item_code, Issuance.branch)
        .where(Issuance.from_date > cutoff)
        .where(Issuance.item_code.isnot(None))
        .distinct()
        .subquery()
    )

    lines, value = db.execute(
        select(
            func.count(Stock.id),
            func.coalesce(func.sum(Stock.stock_qty_amount), 0),
        )
        .outerjoin(
            recently_issued,
            and_(
                Stock.item_code == recently_issued.c.item_code,
                Stock.branch == recently_issued.c.branch,
            ),
        )
        .where(recently_issued.c.item_code.is_(None))
        .where(Stock.stock_qty_amount > 0)
    ).one()

    return lines, value, history_days
