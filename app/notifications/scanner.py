import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.dashboard.inventory.calculations import (
    BELOW_REORDER, MOVE_FAST, MOVE_SLOW, derive_movement, derive_stock_status,
)
from app.dashboard.inventory.helpers import issuance_windows, reorder_level_map
from app.enums import ItemRank
from app.imports.helpers import STAGE_GROUPS
from app.imports.models import Consignment, Payment
from app.loading.schemas.stores_schemas import Stock
from app.logistics.models import LogisticsConsignment, LogisticsItem
from app.masters.models import Item
from app.notifications.emit import emit
from app.notifications.models import NotificationState

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# THE THRESHOLD SCANNER
#
# THRESHOLD EVENTS FIRE ON THE CROSSING, NOT ON THE CONDITION.
#
# This is the whole design and everything else follows from it. "Below reorder
# level" is not an event — it is a state, and it stays true until somebody
# restocks. A scan that emits whenever the condition holds emits every single
# pass, for every affected item, for as long as the situation lasts: 96 passes
# a day against a few hundred items is tens of thousands of notifications for
# a handful of real facts, and the channel is dead within a week.
#
# So the previous answer is stored per watched thing in NotificationState, and
# an event is raised only when the answer CHANGES from not-alerting to
# alerting. Recovery updates the state silently — going back above the reorder
# line is not news.
#
# HYSTERESIS. An item sitting exactly on its reorder point still flaps: issue
# two, drop below; receive three, rise above; repeat all day. Crossing DOWN
# happens at the reorder level, but the state only resets to "above" once the
# item recovers past reorder_level * REORDER_HYSTERESIS. Between the two it
# holds whatever state it already had, so a hovering item raises one event and
# then stays quiet.
#
# SET-BASED, NOT LOOPED. Every check asks the database for the rows that are
# CROSSING — the condition joined against the stored state — so Python only
# ever sees the handful of things that actually changed. The stock table has
# thousands of rows and this runs 96 times a day; iterating it here would be a
# scan of the whole table every quarter of an hour.
#
# ONE CHECK IS EXEMPT, deliberately: check_below_reorder compares against the
# dashboard's DERIVED reorder level, which arrives as a dict from a shared
# helper and cannot be a SQL predicate. Reusing the one real definition of
# that threshold is worth more than keeping the rule unbroken, and the SQL
# still narrows the set to rank A/B first. See the note on that function.
#
# NO SECOND DEFINITIONS. Where a figure already exists elsewhere in the app it
# is IMPORTED — derive_movement, derive_stock_status, reorder_level_map,
# issuance_windows, STAGE_GROUPS, derive_open_requests. Dead stock and movement
# class were unified across two dashboards that had drifted apart; a scanner
# quietly recomputing any of them would reopen exactly that wound, with the
# added twist that the disagreement would arrive by notification.
#
# ONE try/except PER CHECK, in run_all. A failing check must not stop the
# others: a bad query in the imports check is not a reason for nobody to hear
# about a stockout.
#-----------------------------------------------------


#--------------------------------
# THRESHOLDS
#
# Every number the scanner judges by, in one place. Inline literals are how a
# threshold ends up meaning one thing in the query and another in the message.
#--------------------------------

# Recovery must clear the reorder line by 5% before the item is considered
# "above" again — the anti-flap band described above. Decimal, because it is
# multiplied against a Numeric quantity and float x Decimal is a TypeError.
REORDER_HYSTERESIS = Decimal("1.05")

CLEARANCE_AGING_DAYS = 7
DEMURRAGE_WARNING_HOURS = 48
PAYMENT_OVERDUE_DAYS = 0
RFD_MISSED_DAYS = 0
TRUCKING_REQUEST_AGED_DAYS = 3

# RUNAWAY GUARD. Past this many crossings in a single check, one summary is
# raised instead of the individual events. A mis-set threshold or a fresh data
# load must not be able to put thousands of rows in front of somebody
# overnight — see _commit_crossings.
MAX_EVENTS_PER_CHECK = 200

# Only rank A and B are worth interrupting anybody about. C is the DEFAULT
# rank — the source workbook only lists A and B — so treating C as critical
# would mean alerting on everything the workbook never mentioned.
CRITICAL_RANKS = [ItemRank.A.value, ItemRank.B.value]

# Stored state values. "alerting" is whichever value means the event has been
# raised; the other means it has not.
BELOW, ABOVE = "below", "above"
OUT, IN_STOCK = "out", "in_stock"
OPEN, CLEAR = "open", "clear"

# Where the item master has no row for a stock line's code. NEVER omitted:
# item names are not unique, so a name with no specification beside it is an
# ambiguous instruction about which physical part to go and find.
SPEC_UNKNOWN = "spec not on file"


@dataclass
class Crossing:
    """One thing whose threshold state just changed."""

    state_key: str
    state_value: str
    # Whether this transition is the one worth telling somebody about.
    # Recoveries are recorded but never raised.
    alert: bool
    payload: dict = field(default_factory=dict)
    entity_type: str = None
    entity_id: int = None
    branch: str = None


#--------------------------------
# THE SHARED TRANSITION MACHINERY
#--------------------------------

def _upsert_states(db, crossings):
    """Write every new state in ONE statement.

    Bulk, and not only for speed: this must happen even when the events were
    grouped away by the runaway guard, or the same hundreds of crossings would
    look new again on the next pass and trip the guard for ever.
    """
    if not crossings:
        return

    now = datetime.now(timezone.utc)

    statement = pg_insert(NotificationState).values([
        {
            "state_key": c.state_key,
            "state_value": c.state_value,
            "last_changed_at": now,
        }
        for c in crossings
    ])

    db.execute(
        statement.on_conflict_do_update(
            index_elements=["state_key"],
            set_={
                "state_value": statement.excluded.state_value,
                "last_changed_at": statement.excluded.last_changed_at,
            },
        )
    )
    db.commit()


def _commit_crossings(db, event_type, crossings, today):
    """Raise what needs raising, then record every new state. Returns events raised."""
    alerts = [c for c in crossings if c.alert]

    if len(alerts) > MAX_EVENTS_PER_CHECK:
        # THE RUNAWAY GUARD. Something is wrong — a threshold, a data load, a
        # first run against a table nobody has scanned before. One summary is
        # useful; four hundred notifications is an outage of the channel.
        logger.warning(
            "Notification runaway guard: %s produced %s crossings in one pass "
            "(limit %s) — grouped into a single event",
            event_type, len(alerts), MAX_EVENTS_PER_CHECK,
        )
        emit(
            db,
            event_type,
            payload={
                "count": len(alerts),
                "event_label": event_type,
            },
            variant="grouped",
            dedupe_key=f"{event_type}:grouped:{today.isoformat()}",
        )
        raised = 1

    else:
        for crossing in alerts:
            emit(
                db,
                event_type,
                payload=crossing.payload,
                entity_type=crossing.entity_type,
                entity_id=crossing.entity_id,
                branch=crossing.branch,
                # The state key already identifies the watched thing
                # uniquely; the date makes a re-crossing on another day a
                # genuinely new event.
                dedupe_key=f"{event_type}:{crossing.state_key}:{today.isoformat()}",
            )
        raised = len(alerts)

    _upsert_states(db, crossings)

    if crossings:
        logger.info(
            "%s: %s crossing(s), %s event(s) raised",
            event_type, len(crossings), raised,
        )

    return raised


def _state_key_sql(prefix, *parts):
    """`prefix:part:part` built in SQL, so the join happens in the database."""
    pieces = [prefix]

    for part in parts:
        pieces.extend([":", part])

    return func.concat(*pieces)


def _crossing_filter(state_column, entering, leaving, alert_state):
    """Only rows whose state actually CHANGES.

    Entering counts when the stored state is not already the alerting one
    (including when there is no stored state at all — a first observation that
    is already over the line is a crossing). Leaving counts only when it is.
    Anything inside the hysteresis band matches neither and is left alone.
    """
    return or_(
        and_(entering, or_(state_column.is_(None), state_column != alert_state)),
        and_(leaving, state_column == alert_state),
    )


def _crossing_state(stored, entering, leaving, alert_state, clear_state):
    """The Python twin of _crossing_filter — same rule, same hysteresis band.

    Returns the new state, or None where nothing changed. It exists only for
    the checks whose condition cannot be expressed in SQL because it is
    computed by a shared helper (see check_below_reorder). Keep the two in
    step: if the transition rule changes, it changes in both.

    `stored` is None when the thing has never been observed, which counts as
    "not alerting" — a first sighting that is already over the line is a
    crossing, not a pre-existing state to be swallowed.
    """
    if entering and stored != alert_state:
        return alert_state

    if leaving and stored == alert_state:
        return clear_state

    return None


#--------------------------------
# INVENTORY
#
# Rank is read from the STOCK ROW, which is per (item_code, branch). An item
# can be an A line at one branch and a C line at another, so rank is never
# folded across branches — the row that crossed is the row that decides.
#--------------------------------

def _spec(value):
    return value if (value and str(value).strip()) else SPEC_UNKNOWN


def _effective_reorder_level(reorder_levels, item_code, branch, stored_level):
    """The reorder level for one stock line, by the dashboard's own precedence.

    Derived level first, the stored column only as the fallback — exactly the
    order app/dashboard/inventory/serializers.py::serialize_row applies. Kept
    in one place because BOTH inventory checks quote a reorder level in their
    message, and two spellings of the fallback is how they drift apart.
    """
    level = reorder_levels.get((item_code, branch))

    if level is None:
        level = stored_level

    return level


def check_below_reorder(db, today):
    #-----------------------------------------------------
    # THE REORDER LEVEL IS NOT `Stock.reorder_level`.
    #
    # The Inventory dashboard DERIVES it per (item_code, branch) from store
    # requisition demand and lead time — reorder_level_map() in
    # app/dashboard/inventory/helpers.py — and falls back to the stored column
    # only for items with no requisition history. That derived figure is the
    # definition of "reorder level" in this system, so it is imported here
    # rather than recomputed: a notification saying an item is below reorder
    # has to mean the same thing as the dashboard tile saying it, or one of
    # the two is lying to somebody.
    #
    # This is not a nicety in the current data — `stock.reorder_level` is 0 on
    # all 6,098 rows, so a check judging by the raw column alone could never
    # fire at all, and would have looked like a working feature.
    #
    # CONSEQUENCE: the crossing test runs in Python, not SQL, because the
    # threshold comes from a dict rather than a column (the general rule is
    # set-based — see the module header). That is affordable precisely because
    # the SQL below still does the filtering that matters: rank A/B only, which
    # is 363 rows out of 6,098, fetched once per 15-minute pass.
    #-----------------------------------------------------
    reorder_levels = reorder_level_map(db)

    key = _state_key_sql("reorder", Stock.item_code, Stock.branch)

    rows = db.execute(
        select(
            key.label("state_key"),
            Stock.item_code, Stock.branch, Stock.item_name,
            Stock.available_qty, Stock.reorder_level, Stock.rank,
            # The specification the message is required to carry. The stock
            # table does not hold one, so it comes from the item master.
            Item.default_specification,
            NotificationState.state_value,
        )
        .select_from(Stock)
        .outerjoin(Item, Item.item_code == Stock.item_code)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(Stock.item_code.isnot(None), Stock.branch.isnot(None))
        .where(Stock.available_qty.isnot(None))
        .where(Stock.rank.in_(CRITICAL_RANKS))
    ).all()

    crossings = []

    for r in rows:
        level = _effective_reorder_level(
            reorder_levels, r.item_code, r.branch, r.reorder_level,
        )

        # No level from either source means there is no line to be under.
        if level is None or level <= 0:
            continue

        # derive_stock_status, not a fresh comparison: it is the dashboard's
        # own split, and it classifies available <= 0 as Out of Stock rather
        # than Below Reorder — which is what keeps this check and the stockout
        # check from both firing on the same empty bin.
        is_below = derive_stock_status(r.available_qty, level) == BELOW_REORDER
        recovered = (r.available_qty or Decimal("0")) > level * REORDER_HYSTERESIS

        state = _crossing_state(r.state_value, is_below, recovered, BELOW, ABOVE)

        if state is None:
            continue

        crossings.append(Crossing(
            state_key=r.state_key,
            state_value=state,
            alert=(state == BELOW),
            branch=r.branch,
            entity_type="stock_item",
            payload={
                "item_name": r.item_name,
                "specification": _spec(r.default_specification),
                "branch": r.branch,
                "available_qty": r.available_qty,
                "reorder_level": level,
                "rank": r.rank,
            },
        ))

    return _commit_crossings(db, "inventory.below_reorder", crossings, today)


def check_stockout(db, today):
    key = _state_key_sql("stockout", Stock.item_code, Stock.branch)

    entering = Stock.available_qty <= 0
    leaving = Stock.available_qty > 0

    rows = db.execute(
        select(
            key.label("state_key"),
            Stock.item_code, Stock.branch, Stock.item_name,
            Stock.available_qty, Stock.reorder_level, Stock.rank,
            Item.default_specification,
            NotificationState.state_value,
            entering.label("is_out"),
        )
        .select_from(Stock)
        .outerjoin(Item, Item.item_code == Stock.item_code)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(Stock.item_code.isnot(None), Stock.branch.isnot(None))
        .where(Stock.available_qty.isnot(None))
        .where(Stock.rank.in_(CRITICAL_RANKS))
        .where(_crossing_filter(NotificationState.state_value, entering, leaving, OUT))
    ).all()

    if not rows:
        return 0

    # SECOND GATE: the item has to actually MOVE. Zero of something nobody
    # issues is not news. Loaded only now, and only if something crossed, so a
    # quiet pass never pays for the issuance aggregate at all.
    #
    # derive_movement is THE definition of movement class and is imported, not
    # reimplemented — it is the function the Inventory dashboard and the
    # Overview were deliberately unified onto.
    windows, _ = issuance_windows(db)

    # Same derived reorder level the below-reorder check uses, for the same
    # reason: the stockout message quotes one, and quoting the raw column would
    # print "against a reorder level of 0" on every message.
    reorder_levels = reorder_level_map(db)

    crossings = []

    for r in rows:
        if r.is_out:
            issued = windows.get((r.item_code, r.branch), {})
            movement = derive_movement(
                issued.get("v3"), issued.get("v12"), r.available_qty,
            )

            # Not Fast or Slow: dead, or unclassifiable. Its state is still
            # recorded so it does not re-evaluate every pass, but nobody is
            # told about it.
            if movement not in (MOVE_FAST, MOVE_SLOW):
                crossings.append(Crossing(r.state_key, OUT, alert=False))
                continue

            crossings.append(Crossing(
                state_key=r.state_key,
                state_value=OUT,
                alert=True,
                branch=r.branch,
                entity_type="stock_item",
                payload={
                    "item_name": r.item_name,
                    "specification": _spec(r.default_specification),
                    "branch": r.branch,
                    "available_qty": r.available_qty,
                    "reorder_level": _effective_reorder_level(
                        reorder_levels, r.item_code, r.branch, r.reorder_level,
                    ),
                    "rank": r.rank,
                    "movement": movement,
                },
            ))

        else:
            crossings.append(Crossing(r.state_key, IN_STOCK, alert=False))

    return _commit_crossings(db, "inventory.stockout", crossings, today)


#--------------------------------
# IMPORTS
#--------------------------------

def check_clearance_aging(db, today):
    clearance_statuses = STAGE_GROUPS["Clearance"]
    key = _state_key_sql("clearance_aging", cast(Consignment.id, String))

    # Dated from when the stage took effect, falling back to the ETA. Only one
    # consignment in the data carries an effective_date, so without the
    # fallback this check would be blind to almost everything sitting at port.
    since = func.coalesce(Consignment.effective_date, Consignment.eta)
    cutoff = today - timedelta(days=CLEARANCE_AGING_DAYS)

    entering = and_(since.isnot(None), since <= cutoff)
    leaving = or_(since.is_(None), since > cutoff)

    rows = db.execute(
        select(
            key.label("state_key"),
            Consignment.id, Consignment.instrument_number,
            Consignment.current_status, since.label("since"),
            NotificationState.state_value,
            entering.label("is_aging"),
        )
        .select_from(Consignment)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(Consignment.is_deleted == False)  # noqa: E712
        .where(Consignment.current_status.in_(clearance_statuses))
        .where(Consignment.gate_out_date.is_(None))
        .where(_crossing_filter(NotificationState.state_value, entering, leaving, OPEN))
    ).all()

    crossings = []

    for r in rows:
        if not r.is_aging:
            crossings.append(Crossing(r.state_key, CLEAR, alert=False))
            continue

        crossings.append(Crossing(
            state_key=r.state_key,
            state_value=OPEN,
            alert=True,
            entity_type="consignment",
            entity_id=r.id,
            payload={
                "reference": r.instrument_number or f"IMP-{r.id}",
                "status": r.current_status,
                "days_in_clearance": (today - r.since).days if r.since else "?",
                "port": "port",
                "clearing_agent": "the clearing agent",
            },
        ))

    return _commit_crossings(db, "imports.clearance_aging", crossings, today)


def check_demurrage_risk(db, today):
    key = _state_key_sql("demurrage", cast(Consignment.id, String))

    # Demurrage begins free_days_allowed after arrival. In Postgres a date
    # plus an integer is a date, so the run-out is computed in SQL and the
    # crossing test stays set-based like every other check.
    warn_on = today + timedelta(hours=DEMURRAGE_WARNING_HOURS)
    demurrage_starts = Consignment.eta + Consignment.free_days_allowed

    entering = demurrage_starts <= warn_on
    leaving = demurrage_starts > warn_on

    rows = db.execute(
        select(
            key.label("state_key"),
            Consignment.id, Consignment.instrument_number,
            Consignment.eta, Consignment.free_days_allowed,
            NotificationState.state_value,
            entering.label("at_risk"),
        )
        .select_from(Consignment)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(Consignment.is_deleted == False)  # noqa: E712
        .where(Consignment.eta.isnot(None))
        .where(Consignment.free_days_allowed.isnot(None))
        .where(Consignment.gate_out_date.is_(None))
        .where(_crossing_filter(NotificationState.state_value, entering, leaving, OPEN))
    ).all()

    crossings = []

    for r in rows:
        if not r.at_risk:
            crossings.append(Crossing(r.state_key, CLEAR, alert=False))
            continue

        starts = r.eta + timedelta(days=int(r.free_days_allowed or 0))
        crossings.append(Crossing(
            state_key=r.state_key,
            state_value=OPEN,
            alert=True,
            entity_type="consignment",
            entity_id=r.id,
            payload={
                "reference": r.instrument_number or f"IMP-{r.id}",
                "free_days_left": max((starts - today).days, 0),
                "port": "port",
                "arrived_on": r.eta.isoformat(),
                "demurrage_starts": starts.isoformat(),
            },
        ))

    return _commit_crossings(db, "imports.demurrage_risk", crossings, today)


def check_payment_overdue(db, today):
    key = _state_key_sql("payment_overdue", cast(Payment.id, String))
    cutoff = today - timedelta(days=PAYMENT_OVERDUE_DAYS)

    entering = Payment.retirement_date < cutoff
    leaving = Payment.retirement_date >= cutoff

    rows = db.execute(
        select(
            key.label("state_key"),
            Payment.id, Payment.retirement_date, Payment.consignment_id,
            Consignment.instrument_number, Consignment.payment_instrument,
            NotificationState.state_value,
            entering.label("is_overdue"),
        )
        .select_from(Payment)
        .join(Consignment, Consignment.id == Payment.consignment_id)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(Payment.is_deleted == False)  # noqa: E712
        .where(Consignment.is_deleted == False)  # noqa: E712
        .where(Payment.retirement_date.isnot(None))
        .where(func.lower(func.coalesce(Payment.status, "")) != "paid")
        .where(_crossing_filter(NotificationState.state_value, entering, leaving, OPEN))
    ).all()

    crossings = []

    for r in rows:
        if not r.is_overdue:
            crossings.append(Crossing(r.state_key, CLEAR, alert=False))
            continue

        crossings.append(Crossing(
            state_key=r.state_key,
            state_value=OPEN,
            alert=True,
            entity_type="consignment",
            entity_id=r.consignment_id,
            payload={
                "instrument": r.payment_instrument or "Payment",
                "instrument_number": r.instrument_number or "",
                "reference": r.instrument_number or f"IMP-{r.consignment_id}",
                "supplier": "the supplier",
                "due_date": r.retirement_date.isoformat(),
                "days_overdue": (today - r.retirement_date).days,
            },
        ))

    return _commit_crossings(db, "imports.payment_overdue", crossings, today)


#--------------------------------
# LOGISTICS
#--------------------------------

def check_rfd_missed(db, today):
    key = _state_key_sql("rfd_missed", cast(LogisticsItem.id, String))
    cutoff = today - timedelta(days=RFD_MISSED_DAYS)

    entering = LogisticsItem.planned_rfd_date < cutoff
    leaving = LogisticsItem.planned_rfd_date >= cutoff

    rows = db.execute(
        select(
            key.label("state_key"),
            LogisticsItem.id, LogisticsItem.item_detail,
            LogisticsItem.planned_rfd_date,
            LogisticsConsignment.id.label("order_id"),
            LogisticsConsignment.mo_no, LogisticsConsignment.customer_name,
            NotificationState.state_value,
            entering.label("is_missed"),
        )
        .select_from(LogisticsItem)
        .join(LogisticsConsignment, LogisticsConsignment.id == LogisticsItem.consignment_id)
        .outerjoin(NotificationState, NotificationState.state_key == key)
        .where(LogisticsItem.is_deleted == False)  # noqa: E712
        .where(LogisticsConsignment.is_deleted == False)  # noqa: E712
        .where(LogisticsItem.planned_rfd_date.isnot(None))
        # Not yet dispatched: an actual RFD means it went.
        .where(LogisticsItem.actual_rfd_date.is_(None))
        .where(_crossing_filter(NotificationState.state_value, entering, leaving, OPEN))
    ).all()

    crossings = []

    for r in rows:
        if not r.is_missed:
            crossings.append(Crossing(r.state_key, CLEAR, alert=False))
            continue

        crossings.append(Crossing(
            state_key=r.state_key,
            state_value=OPEN,
            alert=True,
            entity_type="logistics_order",
            entity_id=r.order_id,
            payload={
                "item_detail": r.item_detail or "An item",
                "mo_no": r.mo_no or f"order {r.order_id}",
                "customer": r.customer_name or "unknown customer",
                "planned_rfd": r.planned_rfd_date.isoformat(),
                "days_late": (today - r.planned_rfd_date).days,
            },
        ))

    return _commit_crossings(db, "logistics.rfd_missed", crossings, today)


def check_detention_risk(db, today):
    """NOT IMPLEMENTED — the data to compute it does not exist.

    A detention window needs a date the container became chargeable from, and
    an allowance. Logistics stores NEITHER: `container_detention` is a Numeric
    COST (money already incurred, on the order), `logistics_containers` holds
    only a number and a type with no business dates at all, and there is no
    free-days column on a logistics order the way there is on an import.

    The nearest available dates — cro_arrival_date, actual_arrival_date — say
    when the goods arrived, not when detention starts, and turning one into
    the other requires a free-days allowance that is nowhere in this system.
    Inventing a constant for it would be inventing a business rule.

    So this raises nothing rather than raising something plausible and wrong.
    The catalogue entry and this function stay so the gap is visible where
    somebody will look for it; when the column exists this is the one place to
    change.
    """
    return 0


#--------------------------------
# TRUCKING
#--------------------------------

def check_request_aged(db, today):
    """Open hand-offs nobody has taken.

    Reuses cross_module.derive_open_requests, which already computes days_open
    from the source record's own hand-off timestamp — the same figure the
    trucking list badges and the Overview tile count. Imported here rather
    than re-derived so all three can never disagree about what "aged" means.
    """
    from app.cross_module import derive_open_requests

    requests = derive_open_requests(db)

    # The open-request set is small by construction — it is a work queue, and
    # anything taken leaves it — so this is the one check with no set-based
    # crossing query behind it.
    keys = [f"aged:{r['source']}:{r['source_ref']}" for r in requests]

    stored = {}

    if keys:
        stored = dict(db.execute(
            select(NotificationState.state_key, NotificationState.state_value)
            .where(NotificationState.state_key.in_(keys))
        ).all())

    crossings = []

    for request, key in zip(requests, keys):
        days_open = request.get("days_open")

        if days_open is None:
            continue

        aged = days_open > TRUCKING_REQUEST_AGED_DAYS
        was = stored.get(key)

        if aged and was != OPEN:
            crossings.append(Crossing(
                state_key=key,
                state_value=OPEN,
                alert=True,
                entity_type=(
                    "consignment" if request["source"] == "from-import-fob"
                    else "logistics_order"
                ),
                entity_id=int(request["source_ref"]) if str(request["source_ref"]).isdigit() else None,
                payload={
                    "label": request.get("label") or request["source_ref"],
                    "days_open": days_open,
                    "source_ref": request["source_ref"],
                },
            ))

        elif not aged and was == OPEN:
            crossings.append(Crossing(key, CLEAR, alert=False))

    return _commit_crossings(db, "trucking.request_aged", crossings, today)


#--------------------------------
# THE PASS
#--------------------------------

CHECKS = [
    ("inventory.below_reorder", check_below_reorder),
    ("inventory.stockout", check_stockout),
    ("imports.clearance_aging", check_clearance_aging),
    ("imports.demurrage_risk", check_demurrage_risk),
    ("imports.payment_overdue", check_payment_overdue),
    ("logistics.rfd_missed", check_rfd_missed),
    ("logistics.detention_risk", check_detention_risk),
    ("trucking.request_aged", check_request_aged),
]


def run_all(db):
    """Every threshold check, in sequence. Returns total events raised.

    Each is wrapped on its own: one failing check — a bad query, a schema
    change nobody propagated — must not stop the rest. Silence from the
    inventory scanner because the imports scanner threw would be the worst
    kind of failure here, because nothing about it looks broken.
    """
    today = date.today()
    total = 0

    for name, check in CHECKS:
        try:
            total += check(db, today)

        except Exception:
            db.rollback()
            logger.exception(
                "Threshold check %s failed; continuing with the rest", name
            )

    return total
