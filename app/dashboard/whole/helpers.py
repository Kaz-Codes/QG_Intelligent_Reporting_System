from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, func, and_, or_, case

from app.imports.models import Consignment, ConsignmentItem
from app.imports.helpers import STAGE_GROUPS
from app.logistics.models import LogisticsConsignment, LogisticsPackage
from app.trucking.models import TruckingConsignment, TruckingVehicle
from app.loading.schemas.stores_schemas import (
    Stock, Issuance, PurchasesData,
)
from app.masters.models import Item
from app.enums import Status, JobKind
from app.reports.helpers import SHAFT_ITEMS
from app.dashboard.stock_runway import RUNWAY_WINDOW_DAYS, runway_window
from app.dashboard.period import (
    coverage, PURCHASES_DATE_DEFAULT as SHARED_PURCHASES_DATE_DEFAULT,
)

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
# It is the SHARED constant, not a local 90: this section used to divide by 90
# days while its tile was captioned "at the last 12 months' usage", which is why
# the Overview reported 54 days of stock against Inventory's 81.
CONSUMPTION_WINDOW_DAYS = RUNWAY_WINDOW_DAYS


def _live_consignments():
    return Consignment.is_deleted.is_(False)


#-------------------------------------
# IMPORTS
#-------------------------------------

#-----------------------------------------------------
# EACH SECTION HAS ITS OWN DATE, AND ITS OWN CHOICE OF DATE
#
# There is no single "reporting period" that means the same thing to imports,
# procurement and logistics — a consignment's ETA Works, a PO's date and a
# truck's execution date are different events. One window across all of them
# was quietly comparing unlike things, so each section now carries its own.
#
# Where the business genuinely uses two dates, the CALLER picks:
#   imports    — eta_works (when goods land) or required_date (when they were
#                needed). "Value arriving in August" and "value needed in
#                August" are both real questions and they are not the same set.
#   logistics  — etd (departure) or eta (arrival).
#
# The columns are looked up through these maps rather than interpolated, so an
# unknown field name can never reach SQL.
#-----------------------------------------------------

IMPORTS_DATE_FIELDS = {
    "eta_works": Consignment.eta_works,
    "required_date": Consignment.required_date,
}
IMPORTS_DATE_DEFAULT = "eta_works"

# Procurement has two real events too: when the order was PLACED and when it
# was actually BOUGHT. Both are fully populated, and they answer different
# questions ("what did we commit to in August" vs "what did we spend in
# August"), so the caller picks rather than the backend deciding.
PURCHASES_DATE_FIELDS = {
    "po_date": PurchasesData.po_date,
    "purchase": PurchasesData.purchase,
}
# Defined once in app/dashboard/period — see why it is not "po_date".
PURCHASES_DATE_DEFAULT = SHARED_PURCHASES_DATE_DEFAULT


def purchases_date_column(field):
    return PURCHASES_DATE_FIELDS.get(field or PURCHASES_DATE_DEFAULT,
                                     PURCHASES_DATE_FIELDS[PURCHASES_DATE_DEFAULT])

# Trucking carries the movement itself; the logistics order carries the sailing.
# Both are resolved per source so "ETD" means departure in each table.
TRUCKING_DATE_FIELDS = {
    "etd": TruckingConsignment.execution_date,
    "eta": TruckingConsignment.eta_works,
}
LOGISTICS_ORDER_DATE_FIELDS = {
    "etd": LogisticsConsignment.etd_sailing_date,
    "eta": LogisticsConsignment.actual_arrival_date,
}
LOGISTICS_DATE_DEFAULT = "etd"


def imports_date_column(field):
    return IMPORTS_DATE_FIELDS.get(field or IMPORTS_DATE_DEFAULT,
                                   IMPORTS_DATE_FIELDS[IMPORTS_DATE_DEFAULT])


# A consignment's value: the BOOKED total, or the item lines where none was
# booked. Identical to imports.calculations.consignment_value_pkr, expressed in
# SQL — the two screens must value the same consignment the same way, or the
# overview and the module disagree about the same money.
_LINE_VALUE = (
    select(func.sum(ConsignmentItem.quantity * ConsignmentItem.unit_price))
    .where(ConsignmentItem.consignment_id == Consignment.id)
    .where(ConsignmentItem.is_deleted.is_(False))
    .correlate(Consignment)
    .scalar_subquery()
)

CONSIGNMENT_VALUE = func.coalesce(
    Consignment.pkr_total,
    _LINE_VALUE * Consignment.exchange_rate,
    0,
)


#-----------------------------------------------------
# MONEY IS COUNTED IN THE MONTH IT ARRIVED
#
# A consignment groups every sheet row sharing a payment reference, and those
# rows do not all arrive together — 19 of 175 consignments carry lines with
# different ETAs. Valuing the whole consignment against its HEADER date credits
# the entire amount to one month: payment ref 65704 reported Rs 10.64m in
# August, when Rs 8.98m arrived on 6 August and Rs 1.25m had landed on 27 July.
#
# So period value is summed over LINES, each dated by its own ETA (falling back
# to its consignment's where the sheet gave the line none). A consignment whose
# lines span two months now contributes to both, in the right proportion.
#
# WHY NOT THE STORED `pkr_total`. It is the booked figure and imports rule 4
# says never to restate it — but it is a figure for the WHOLE consignment, and
# there is no stored per-line PKR to split it with. For the 89% of consignments
# that sit wholly inside one window the two agree to within sheet rounding
# (Rs 10,643,562 booked against Rs 10,638,670 from the lines, 0.05%); for the
# rest, a correct month beats a stored total attributed to the wrong one. The
# consignment-level `CONSIGNMENT_VALUE` above still prefers the booked total and
# is what the un-windowed figures use.
#-----------------------------------------------------

LINE_ETA = func.coalesce(ConsignmentItem.eta_works, Consignment.eta_works)

LINE_VALUE_PKR = (
    ConsignmentItem.quantity * ConsignmentItem.unit_price * Consignment.exchange_rate
)


def line_date_column(date_field):
    """Which date a LINE is filtered on.

    Only ETA at works exists per line; `required_date` is a header attribute
    with no line equivalent, so that choice keeps using the header rather than
    silently filtering on a different column.
    """
    if (date_field or IMPORTS_DATE_DEFAULT) == "required_date":
        return Consignment.required_date
    return LINE_ETA


def line_scope(shafts_only=False):
    """The WHERE clauses every line-level imports figure shares."""
    scope = [
        ConsignmentItem.is_deleted.is_(False),
        Consignment.is_deleted.is_(False),
    ]
    if shafts_only:
        scope.append(Consignment.id.in_(shaft_consignment_ids()))
    return scope


def _line_select(date_from, date_to, date_field, shafts_only):
    return (
        select(
            func.coalesce(func.sum(LINE_VALUE_PKR), 0),
            func.count(func.distinct(ConsignmentItem.consignment_id)),
            func.count(ConsignmentItem.id),
        )
        .select_from(ConsignmentItem)
        .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
        .where(*line_scope(shafts_only))
        .where(line_date_column(date_field).between(date_from, date_to))
    )


#-----------------------------------------------------
# THE SHAFTS FILTER
#
# A tab, not a pair of tiles. Shafts used to be two standalone KPIs sitting
# among figures that covered everything, so "9 shafts in process" could not be
# compared with the 30 beside it — different populations, same row. As a filter
# it narrows EVERY figure in the section at once, and each tile then means the
# same thing it always did, over shafts.
#
# Matched on the LINE's item name, not the item master: these names are not in
# `items` at all, and the line keeps its own copy anyway (imports rule 12).
#-----------------------------------------------------

def shaft_consignment_ids():
    return (
        select(ConsignmentItem.consignment_id)
        .where(ConsignmentItem.is_deleted.is_(False))
        .where(or_(*[ConsignmentItem.item_name.ilike(f"%{name}%")
                     for name in SHAFT_ITEMS]))
        .distinct()
        .scalar_subquery()
    )


def _imports_scope(shafts_only):
    """The WHERE clauses every imports figure in this section shares."""
    scope = [_live_consignments()]
    if shafts_only:
        scope.append(Consignment.id.in_(shaft_consignment_ids()))
    return scope


def imports_period_value(db, date_from, date_to, date_field=None, shafts_only=False):
    """(value, consignments, lines) for the window, summed over LINES.

    Dated by each line's own ETA, so money lands in the month it arrived rather
    than in whichever month its consignment header happened to name. The
    consignment count is DISTINCT consignments having a line in the window — a
    consignment straddling two months is counted in both, because it genuinely
    delivered in both.
    """
    total, consignments, lines = db.execute(
        _line_select(date_from, date_to, date_field, shafts_only)
    ).one()

    return total, consignments, lines


def imports_value_undated(db, date_field=None, shafts_only=False):
    # Consignments carrying a value but no date in the column being filtered on.
    # They cannot fall inside ANY window, so every period figure silently
    # excludes them. Returned so the front end can say so, rather than letting
    # the money disappear between periods — and recomputed per chosen field,
    # since required_date is sparser than eta_works.
    column = imports_date_column(date_field)

    return db.execute(
        select(
            func.count(Consignment.id),
            func.coalesce(func.sum(CONSIGNMENT_VALUE), 0),
        )
        .where(*_imports_scope(shafts_only))
        .where(column.is_(None))
    ).one()


def imports_date_coverage(db, date_field=None, shafts_only=False):
    """(dated, total) live consignments for the chosen date column.

    Feeds the section's data note: required_date is sparser than eta_works, so
    switching the filter genuinely changes how much of the book is visible and
    the screen should say which it is looking at.
    """
    column = imports_date_column(date_field)

    return db.execute(
        select(func.count(column), func.count(Consignment.id))
        .where(*_imports_scope(shafts_only))
    ).one()


def trucking_date_coverage(db, date_field=None):
    """(dated, total) trucking jobs for the chosen date column."""
    column = TRUCKING_DATE_FIELDS.get(date_field or LOGISTICS_DATE_DEFAULT,
                                      TRUCKING_DATE_FIELDS[LOGISTICS_DATE_DEFAULT])

    return db.execute(
        select(func.count(column), func.count(TruckingConsignment.id))
        .where(TruckingConsignment.is_deleted.is_(False))
    ).one()


def imports_in_process_by_stage(db, date_from=None, date_to=None,
                                date_field=None, shafts_only=False):
    # Counts per status, then rolled into the six pipeline stages the imports
    # list uses. Terminal statuses are excluded, so the "Closed" stage never
    # appears here by construction.
    status_counts = dict(
        db.execute(
            select(Consignment.current_status, func.count(Consignment.id))
            .where(*_imports_scope(shafts_only))
            .where(*([imports_date_column(date_field).between(date_from, date_to)]
                     if date_from is not None and date_to is not None else []))
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

def procurement_period_totals(db, date_from, date_to, date_field=None):
    """Value + how many ORDERS, not item lines.

    A PO with five lines is five rows in this table; counting rows made
    procurement look three times busier than it was and could not be compared
    with anything else on the screen. Distinct PO numbers is the order count.
    """
    total, orders, quantity = db.execute(
        select(
            func.coalesce(func.sum(PurchasesData.amount), 0),
            func.count(func.distinct(PurchasesData.po_number)),
            func.coalesce(func.sum(PurchasesData.qty), 0),
        )
        .where(purchases_date_column(date_field).between(date_from, date_to))
    ).one()

    return total, orders, quantity


def procurement_category_totals(db, date_from, date_to, date_field=None):
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
        .where(purchases_date_column(date_field).between(date_from, date_to))
        .group_by(func.coalesce(Item.category, "Uncategorised"))
    ).all()

    return {name: value for name, value in rows}


def procurement_delay(db, date_from, date_to, date_field=None):
    # A line is late when it was purchased after the date it was required.
    comparable, late = db.execute(
        select(
            func.count(func.distinct(PurchasesData.po_number)),
            func.count(func.distinct(
                case((PurchasesData.required_d < PurchasesData.purchase,
                      PurchasesData.po_number))
            )),
        )
        .where(purchases_date_column(date_field).between(date_from, date_to))
        .where(PurchasesData.required_d.isnot(None))
    ).one()

    return late, comparable


def procurement_cycle_times(db, date_from, date_to, date_field=None):
    # Average days from each candidate demand date to the purchase date. Rows
    # where the "demand" date sits after the purchase are excluded rather than
    # counted as negative lead time — they are data errors, and letting them in
    # would drag the average below what any real cycle took.
    in_window = purchases_date_column(date_field).between(date_from, date_to)

    store_days, store_rows = db.execute(
        select(
            func.avg(PurchasesData.purchase - PurchasesData.ppc_store),
            func.count(func.distinct(PurchasesData.po_number)),
        )
        .where(in_window)
        .where(PurchasesData.ppc_store.isnot(None))
        .where(PurchasesData.ppc_store <= PurchasesData.purchase)
    ).one()

    po_days, po_rows = db.execute(
        select(
            func.avg(PurchasesData.purchase - PurchasesData.po_date),
            func.count(func.distinct(PurchasesData.po_number)),
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

def trucking_cost_by_movement(db, date_from=None, date_to=None, date_field=None):
    """Freight split by movement type, within the window.

    Grouped in SQL including the NULL movement group, which is a real bucket
    here (191 jobs) and not an error to filter away — see
    calculations.UNCLASSIFIED.

    ETD is the execution date (when the truck ran); ETA is eta_works. Both are
    well populated (97.5% / 88.7%), so this section responds properly to the
    window.
    """
    column = TRUCKING_DATE_FIELDS.get(date_field or LOGISTICS_DATE_DEFAULT,
                                      TRUCKING_DATE_FIELDS[LOGISTICS_DATE_DEFAULT])

    query = (
        select(
            TruckingConsignment.movement_type,
            func.count(TruckingConsignment.id),
            func.coalesce(func.sum(TruckingConsignment.actual_freight), 0),
            func.coalesce(func.sum(TruckingConsignment.quoted_freight), 0),
        )
        .where(TruckingConsignment.is_deleted.is_(False))
    )

    if date_from is not None and date_to is not None:
        query = query.where(column.between(date_from, date_to))

    return db.execute(query.group_by(TruckingConsignment.movement_type)).all()


def shipments_handled(db, date_from=None, date_to=None, date_field=None):
    """Export orders + import consignments in the window, with their coverage.

    COVERAGE MATTERS HERE and nowhere else on this screen: only 13.8% of
    logistics orders carry an ETD and 9.9% an arrival date, so windowing drops
    most of them. The counts are returned alongside how many orders could be
    dated at all, so the screen can explain a small number instead of just
    showing one. The import side is fine (86-92%).

    Export side is standard logistics orders only — rework service jobs are not
    shipments handled for a customer, and job_kind is what separates them.
    """
    field = date_field or LOGISTICS_DATE_DEFAULT
    order_column = LOGISTICS_ORDER_DATE_FIELDS.get(
        field, LOGISTICS_ORDER_DATE_FIELDS[LOGISTICS_DATE_DEFAULT]
    )
    # The import side's equivalent of the same two events.
    consignment_column = Consignment.etd if field == "etd" else Consignment.eta_works

    standard = (
        (LogisticsConsignment.is_deleted.is_(False))
        & (LogisticsConsignment.job_kind == JobKind.STANDARD.value)
    )

    export_total, export_datable = db.execute(
        select(
            func.count(LogisticsConsignment.id),
            func.count(order_column),
        ).where(standard)
    ).one()

    import_total, import_datable = db.execute(
        select(
            func.count(Consignment.id),
            func.count(consignment_column),
        ).where(_live_consignments())
    ).one()

    if date_from is None or date_to is None:
        return {
            "export": export_total, "import": import_total,
            "export_datable": export_datable, "export_total": export_total,
            "import_datable": import_datable, "import_total": import_total,
        }

    export_orders = db.execute(
        select(func.count(LogisticsConsignment.id))
        .where(standard)
        .where(order_column.between(date_from, date_to))
    ).scalar_one()

    import_consignments = db.execute(
        select(func.count(Consignment.id))
        .where(_live_consignments())
        .where(consignment_column.between(date_from, date_to))
    ).scalar_one()

    return {
        "export": export_orders, "import": import_consignments,
        "export_datable": export_datable, "export_total": export_total,
        "import_datable": import_datable, "import_total": import_total,
    }


#-------------------------------------
# STORES
#-------------------------------------

def stock_totals(db):
    return db.execute(
        select(
            func.coalesce(func.sum(Stock.stock_qty_amount), 0),
            func.coalesce(func.sum(Stock.available_amount), 0),
            func.count(func.distinct(Stock.item_code)),
        )
    ).one()


def stock_by_branch(db):
    return db.execute(
        select(
            Stock.branch,
            func.coalesce(func.sum(Stock.stock_qty_amount), 0),
            func.count(func.distinct(Stock.item_code)),
        )
        .where(Stock.branch.isnot(None))
        .group_by(Stock.branch)
    ).all()


def consumption_by_branch(db, window_days=CONSUMPTION_WINDOW_DAYS):
    # Rupee value issued per branch over the window, ending at the most recent
    # issuance in the data rather than today — the data is historical, and
    # anchoring to today would measure an empty window and report every store as
    # having infinite runway.
    start, latest, window_days = runway_window(db, window_days)
    if latest is None:
        return {}, window_days

    # ONLY issuance that depletes stock we actually hold — matched to a stock
    # row on (item_code, branch), which is the population the Inventory
    # dashboard measures. Counting every issuance instead put Rs 1.75bn of
    # consumption against items with no stock row at all, understating the
    # runway of the stock we DO hold: 58 days here against Inventory's 81 for
    # the same warehouses. Runway asks how long the stock on hand will last, so
    # consumption that cannot deplete it does not belong in the denominator.
    depletes_stock = (
        select(1)
        .where(Stock.item_code == Issuance.item_code)
        .where(Stock.branch == Issuance.branch)
        .correlate(Issuance)
        .exists()
    )

    rows = db.execute(
        select(
            Issuance.branch,
            func.coalesce(func.sum(Issuance.total_price), 0),
        )
        .where(Issuance.branch.isnot(None))
        .where(Issuance.from_date.between(start, latest))
        .where(depletes_stock)
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
            func.count(func.distinct(Stock.item_code)),
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


#-----------------------------------------------------
# COUNT AND VALUE FOR EVERY IMPORTS BUCKET
#
# In process, arrived and cancelled, each with how many and how much — the same
# pair the period-value tile reports, so the tiles in one row can be read
# against each other. Reporting a count alone said 30 consignments were moving
# without saying whether that was Rs 4m or Rs 400m of exposure.
#
# WINDOWED, on the section's chosen date. It was a lifetime snapshot, on the
# argument that a pipeline is "what is open now" — but the Imports dashboard
# windows the same three figures, so the two screens reported 142 arrived and
# 141 for what a reader took to be one number. A tile that cannot be reconciled
# with the same tile on the module screen is worse than one whose window is
# debatable, so the window wins and both screens now agree exactly.
#-----------------------------------------------------

def imports_population(db, date_from=None, date_to=None, date_field=None,
                       shafts_only=False):
    scope = _imports_scope(shafts_only)
    if date_from is not None and date_to is not None:
        scope.append(imports_date_column(date_field).between(date_from, date_to))

    in_process = Consignment.current_status.notin_(TERMINAL_STATUSES)
    arrived = Consignment.current_status == Status.ARRIVED_AT_WORKS.value
    cancelled = Consignment.current_status == Status.ORDER_CANCELLED.value

    def bucket(condition):
        return (
            func.count(case((condition, 1))),
            func.coalesce(func.sum(case((condition, CONSIGNMENT_VALUE))), 0),
        )

    row = db.execute(
        select(
            func.count(Consignment.id),
            func.coalesce(func.sum(CONSIGNMENT_VALUE), 0),
            *bucket(in_process), *bucket(arrived), *bucket(cancelled),
        ).where(*scope)
    ).one()

    keys = ("total", "in_process", "arrived", "cancelled")
    return {
        key: {"count": row[i * 2], "value": row[i * 2 + 1]}
        for i, key in enumerate(keys)
    }


#-----------------------------------------------------
# DELAYED IMPORTS
#
# The SAME rule the Imports dashboard uses (calculations.DELAY_GRACE_DAYS):
# more than a week past the required date is delayed; anything inside the week
# is normal scheduling slip and counts as on time. Imported rather than
# restated, so the two screens cannot drift to different definitions of "late".
#-----------------------------------------------------

def imports_delay(db, date_from=None, date_to=None, date_field=None,
                  shafts_only=False):
    from app.dashboard.imports.calculations import DELAY_GRACE_DAYS

    scope = _imports_scope(shafts_only)
    if date_from is not None and date_to is not None:
        scope.append(imports_date_column(date_field).between(date_from, date_to))
    measurable = and_(Consignment.required_date.isnot(None),
                      Consignment.eta_works.isnot(None))
    late = Consignment.eta_works > Consignment.required_date + DELAY_GRACE_DAYS

    comparable, late_count, late_value = db.execute(
        select(
            func.count(case((measurable, 1))),
            func.count(case((and_(measurable, late), 1))),
            func.coalesce(func.sum(case((and_(measurable, late), CONSIGNMENT_VALUE))), 0),
        ).where(*scope)
    ).one()

    return {
        "count": late_count,
        "value": late_value,
        "basis": comparable,
        "grace_days": DELAY_GRACE_DAYS,
        "delay_pct": round(late_count / comparable * 100, 1) if comparable else None,
    }


#-----------------------------------------------------
# COVERAGE, PER SECTION
#
# Every section that has a time dimension reports what its source actually
# holds, so the screen can say "no purchases in August — latest is 23 Jan" and
# offer a jump there, instead of a confident Rs 0.
#
# It also removes a live bug: with no coverage to fall back on, the shared
# period control's "All data" preset used a hardcoded 2000-01-01, which put a
# date in the From box for a year the data has never contained.
#-----------------------------------------------------

def imports_coverage(db, date_from, date_to, date_field=None, shafts_only=False):
    column = imports_date_column(date_field)
    label = "ETA at works" if (date_field or IMPORTS_DATE_DEFAULT) == "eta_works" else "required date"
    scope = _imports_scope(shafts_only)

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column), func.count(Consignment.id)).where(*scope)
    ).one()
    in_period = db.execute(
        select(func.count(Consignment.id)).where(*scope)
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


def purchases_coverage(db, date_from, date_to, date_field=None):
    column = purchases_date_column(date_field)
    label = "PO date" if (date_field or PURCHASES_DATE_DEFAULT) == "po_date" else "purchase date"

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column),
               func.count(func.distinct(PurchasesData.po_number)))
    ).one()
    in_period = db.execute(
        select(func.count(func.distinct(PurchasesData.po_number)))
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


def logistics_coverage(db, date_from, date_to, date_field=None):
    column = TRUCKING_DATE_FIELDS.get(date_field or LOGISTICS_DATE_DEFAULT,
                                      TRUCKING_DATE_FIELDS[LOGISTICS_DATE_DEFAULT])
    label = "ETD (departure)" if (date_field or LOGISTICS_DATE_DEFAULT) == "etd" else "ETA (arrival)"
    live = TruckingConsignment.is_deleted.is_(False)

    earliest, latest, total = db.execute(
        select(func.min(column), func.max(column),
               func.count(TruckingConsignment.id)).where(live)
    ).one()
    in_period = db.execute(
        select(func.count(TruckingConsignment.id)).where(live)
        .where(column.between(date_from, date_to))
    ).scalar_one()

    return coverage(earliest, latest, in_period, total, label)


#-----------------------------------------------------
# ISSUANCE IN A PERIOD
#
# Replaces the "Stores holding stock" tile, which was a count of branches — a
# number that changes about once a year and told nobody anything about how the
# stores are running. What was actually ISSUED this month, and against how many
# distinct items, is the figure that moves.
#
# Items are counted BY ITEM CODE, folded across branches, exactly as the
# Inventory dashboard counts them, so "1,443 items" means the same thing on
# both screens.
#
# The window is the caller's, defaulting to the current month like every other
# period on the system.
#-----------------------------------------------------

def issuance_period(db, date_from, date_to):
    value, items, lines, quantity = db.execute(
        select(
            func.coalesce(func.sum(Issuance.total_price), 0),
            func.count(func.distinct(Issuance.item_code)),
            func.count(Issuance.id),
            func.coalesce(func.sum(Issuance.quantity), 0),
        ).where(Issuance.from_date.between(date_from, date_to))
    ).one()

    return {"value": value, "items": items, "lines": lines, "quantity": quantity}


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


#-----------------------------------------------------
# LOGISTICS, BEYOND TRUCKING COST
#
# The section had two figures, both about road movement, which made "logistics"
# look like a synonym for trucking. These add one from each of the other two
# areas — packing and sea/air shipping — chosen for what the data can actually
# support rather than for what would look impressive:
#
#   packed tonnage    618 of 678 packages carry a weight (91%)
#   freight per kg    1,130 of 1,369 jobs have both freight and a vehicle weight
#   transit time      174 of 745 orders carry BOTH an ETD and an arrival (23%)
#
# Deliberately NOT added: packing cost or savings (0 of 678 packages record an
# actual cost, so both are null), and anything built on gate-out (13%) or sea
# freight (12%). A tile that is null or rests on an eighth of the book is worse
# than no tile — see the KPIs already held back for want of data.
#
# Each returns its own basis, so the screen states the denominator rather than
# implying the figure covers everything.
#-----------------------------------------------------

def logistics_packed_tonnage(db, date_from=None, date_to=None):
    """Weight packed in the window, and over how many packages."""
    conditions = [LogisticsPackage.is_deleted.is_(False)]
    if date_from is not None and date_to is not None:
        conditions.append(
            func.coalesce(LogisticsPackage.packing_date,
                          LogisticsPackage.packing_ready_date)
            .between(date_from, date_to)
        )

    weight, weighed, packages = db.execute(
        select(
            func.coalesce(func.sum(LogisticsPackage.gross_weight), 0),
            func.count(LogisticsPackage.gross_weight),
            func.count(LogisticsPackage.id),
        ).where(*conditions)
    ).one()

    return {
        "kilograms": weight,
        "tonnes": round(float(weight) / 1000, 1) if weight else 0.0,
        "packages": packages,
        # How many of them actually carry a weight — the rest add nothing.
        "basis": weighed,
    }


def logistics_freight_per_kg(db, date_from=None, date_to=None, date_field=None):
    """Rupees of road freight per kilogram moved.

    A RATE, not another total: the section already reports what trucking cost,
    and a second money figure differing only by basis is the duplication this
    whole screen has been cleaned of. Weight comes from the vehicles, which is
    where it is recorded.
    """
    column = TRUCKING_DATE_FIELDS.get(date_field or LOGISTICS_DATE_DEFAULT,
                                      TRUCKING_DATE_FIELDS[LOGISTICS_DATE_DEFAULT])

    conditions = [
        TruckingConsignment.is_deleted.is_(False),
        TruckingVehicle.is_deleted.is_(False),
        TruckingConsignment.actual_freight.isnot(None),
        TruckingVehicle.gross_weight.isnot(None),
    ]
    if date_from is not None and date_to is not None:
        conditions.append(column.between(date_from, date_to))

    freight, weight, jobs = db.execute(
        select(
            func.coalesce(func.sum(TruckingConsignment.actual_freight), 0),
            func.coalesce(func.sum(TruckingVehicle.gross_weight), 0),
            func.count(func.distinct(TruckingConsignment.id)),
        )
        .select_from(TruckingConsignment)
        .join(TruckingVehicle, TruckingVehicle.consignment_id == TruckingConsignment.id)
        .where(*conditions)
    ).one()

    return {
        "rate": round(float(freight) / float(weight), 2) if weight else None,
        "freight": freight,
        "kilograms": weight,
        "basis": jobs,
    }


def logistics_transit_time(db, date_from=None, date_to=None, date_field=None):
    """Average days from sailing to arrival, on the orders that record both."""
    column = LOGISTICS_ORDER_DATE_FIELDS.get(
        date_field or LOGISTICS_DATE_DEFAULT,
        LOGISTICS_ORDER_DATE_FIELDS[LOGISTICS_DATE_DEFAULT],
    )

    measurable = and_(
        LogisticsConsignment.etd_sailing_date.isnot(None),
        LogisticsConsignment.actual_arrival_date.isnot(None),
        # An arrival before its own sailing is a data error, not a negative
        # transit; excluded rather than dragging the average below reality.
        LogisticsConsignment.actual_arrival_date >= LogisticsConsignment.etd_sailing_date,
    )

    conditions = [LogisticsConsignment.is_deleted.is_(False), measurable]
    if date_from is not None and date_to is not None:
        conditions.append(column.between(date_from, date_to))

    days, orders = db.execute(
        select(
            func.avg(LogisticsConsignment.actual_arrival_date
                     - LogisticsConsignment.etd_sailing_date),
            func.count(LogisticsConsignment.id),
        ).where(*conditions)
    ).one()

    return {
        "days": round(float(days), 1) if days is not None else None,
        "basis": orders,
    }
