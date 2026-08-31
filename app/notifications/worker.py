import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, func, select, update
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.notifications.manager import manager
from app.notifications.models import NotificationDelivery, NotificationEvent
from app.notifications.routing import fan_out
from app.notifications.scanner import reconcile_state, run_all
from app.notifications.serializers import serialize_event

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# THE FAN-OUT WORKER
#
# WHY FAN-OUT IS NOT DONE IN THE REQUEST THAT CAUSED IT
#
# The connection pool is 10 with 20 overflow (app/database.py). A fan-out
# holds a connection while it loads every active user, evaluates the tier and
# permission gates over them, and writes a delivery row each. Doing that
# inside the request that saved the consignment means the user waits for it,
# and — worse — that request keeps its pooled connection for the whole time.
# Thirty users on a busy afternoon and the pool is being consumed by work
# nobody is waiting for, competing with the requests people ARE waiting for.
#
# So emit() writes one row and returns, and this picks the work up out of
# band. The consignment save pays for a single INSERT regardless of how many
# people eventually get told.
#
# SYNC SQLALCHEMY ON THE EVENT LOOP. The whole data layer is synchronous, so
# the pass runs in a threadpool. Calling it directly from the coroutine would
# block the event loop and stall every concurrent request in the process —
# which would be a worse bottleneck than the one this exists to avoid.
#
# BATCHED, so one burst cannot monopolise a connection: at most BATCH_SIZE
# events per pass, then the connection is returned and the loop sleeps. A
# backlog drains over several passes instead of in one long transaction.
#-----------------------------------------------------

POLL_SECONDS = 10
BATCH_SIZE = 100

# THE THRESHOLD SCAN RUNS ON THE SAME TASK, at a much slower cadence.
#
# Every 15 minutes, not every minute: none of these thresholds is
# minute-sensitive — a payment that went overdue at 09:01 is no less overdue at
# 09:15 — and 96 passes a day instead of 1,440 is the difference between a
# background job and a second workload.
#
# ONE TASK, NOT TWO, deliberately. A separate scanner task would let a long
# scan and a fan-out pass hold pooled connections at the same moment, which is
# the contention this design exists to avoid. Sharing the task serialises them
# by construction: the scan cannot start while a fan-out is running, and the
# next fan-out waits for the scan. Neither is latency-critical.
SCAN_EVERY_N_POLLS = 90  # 90 x 10s = 15 minutes

#-----------------------------------------------------
# RETENTION
#
# NOTIFICATIONS ARE NOT AN AUDIT TRAIL. app/logs/ is, and it keeps everything
# for ever on purpose. These rows are a work queue for humans: once somebody
# has read a notification it has done its whole job, and keeping it for years
# only grows the two indexes the badge and the panel depend on. Deleting them
# loses nothing recoverable — the underlying business record is untouched, and
# the fact that somebody was told is in activity_logs.
#
# ONLY READ deliveries are purged, however old. An unread notification is
# still outstanding work, and silently deleting it would mean nobody ever
# finds out about the thing it was raised for.
#
# ONCE A DAY, tracked by ELAPSED TIME rather than a poll count. A poll count
# would mean 8,640 consecutive polls, so a server that restarts nightly — or
# any dev machine — would never once reach it and the table would grow for
# ever with nothing looking wrong. The trade is that the first pass after any
# restart runs the cleanup; it is two indexed queries against nothing on a
# clean table, so that is cheap.
#-----------------------------------------------------

READ_RETENTION_DAYS = 90
CLEANUP_INTERVAL = timedelta(days=1)

# Deleted in chunks so a first run against a long-neglected table takes many
# short transactions instead of one that locks a large range and holds a
# pooled connection while it does.
CLEANUP_BATCH_SIZE = 5000


def _claim(db, limit):
    """Mark up to `limit` queued events as ours, and return them.

    Claim-then-process, in two transactions, rather than one. The trade is
    deliberate: if fan-out fails after the claim, that event loses its
    deliveries and is not retried. The alternative — claiming and processing
    in one transaction so a failure rolls the claim back — retries for ever,
    and because the batch is ordered by id a permanently-poisoned event would
    sit at the front of every future batch and stop the queue dead.
    A lost notification is recoverable; a stalled queue is not noticed.

    The UPDATE re-checks `fanned_out_at IS NULL` under the row lock, so two
    workers racing on the same rows cannot both claim them.
    """
    queued = (
        select(NotificationEvent.id)
        .where(NotificationEvent.fanned_out_at.is_(None))
        .order_by(NotificationEvent.id)
        .limit(limit)
        .scalar_subquery()
    )

    claimed_ids = db.execute(
        update(NotificationEvent)
        .where(NotificationEvent.fanned_out_at.is_(None))
        .where(NotificationEvent.id.in_(queued))
        .values(fanned_out_at=func.now())
        .returning(NotificationEvent.id)
    ).scalars().all()

    db.commit()

    if not claimed_ids:
        return []

    return db.execute(
        select(NotificationEvent).where(NotificationEvent.id.in_(claimed_ids))
    ).scalars().all()


def run_once():
    """One pass. Returns (events processed, delivery rows written, pushes).

    `pushes` is a list of (user_ids, message) for the caller to send once it
    is back on the event loop — see the note on fan_out's on_delivered. The
    message is SERIALIZED HERE, while the session is still open: building it
    after db.close() would touch a detached instance and raise.
    """
    db = SessionLocal()

    try:
        events = _claim(db, BATCH_SIZE)
        delivered = 0
        pushes = []

        for event in events:
            try:
                message = serialize_event(event)
                delivered += fan_out(
                    db,
                    event,
                    on_delivered=lambda user_ids, m=message: pushes.append(
                        (user_ids, m)
                    ),
                )
            except Exception:
                # One bad event does not stop the batch. It stays marked as
                # processed — see _claim on why that is the safer failure.
                db.rollback()
                logger.exception(
                    "Fan-out failed for notification event %s (%s)",
                    event.id, event.event_type,
                )

        if events:
            logger.info(
                "Notification fan-out: %s event(s), %s delivery row(s)",
                len(events), delivered,
            )

        return len(events), delivered, pushes

    finally:
        # Always returned to the pool, however the pass ended.
        db.close()


def run_scan_once():
    """One threshold-scanner pass. Returns how many events it raised."""
    db = SessionLocal()

    try:
        return run_all(db)

    finally:
        db.close()


def _delete_in_batches(db, id_query, model):
    """Delete everything `id_query` selects, CLEANUP_BATCH_SIZE at a time."""
    removed = 0

    while True:
        ids = db.execute(id_query.limit(CLEANUP_BATCH_SIZE)).scalars().all()

        if not ids:
            break

        db.execute(delete(model).where(model.id.in_(ids)))
        db.commit()

        removed += len(ids)

        # A short final batch means the query is exhausted, so this saves one
        # round trip that would only come back empty.
        if len(ids) < CLEANUP_BATCH_SIZE:
            break

    return removed


def run_reconcile_once():
    """One state-reconciliation pass. Returns how many rows were reset."""
    db = SessionLocal()

    try:
        return reconcile_state(db, READ_RETENTION_DAYS)

    finally:
        db.close()


def run_cleanup_once():
    """Purge read deliveries past the retention window, then orphaned events.

    Returns (deliveries removed, events removed).
    """
    db = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=READ_RETENTION_DAYS)

        # READ deliveries only — an unread one is outstanding work whatever
        # its age. Aged on created_at, which is what
        # ix_notification_deliveries_created_at exists for (read_at is not
        # the leading column of any index, and this deletes across all users).
        deliveries = _delete_in_batches(
            db,
            select(NotificationDelivery.id)
            .where(NotificationDelivery.read_at.isnot(None))
            .where(NotificationDelivery.created_at < cutoff),
            NotificationDelivery,
        )

        #-----------------------------------------------------
        # THEN THE EVENTS NOTHING POINTS AT ANY MORE.
        #
        # Two guards, and both are load-bearing:
        #
        #   fanned_out_at IS NOT NULL — an event still QUEUED has no delivery
        #   rows yet by definition. Without this, cleanup would delete the
        #   backlog the fan-out worker has not reached.
        #
        #   created_at < cutoff — closes the race in the other direction. The
        #   worker commits fanned_out_at BEFORE it inserts the deliveries (see
        #   _claim), so for a moment an event is marked routed and has none.
        #   Requiring it to be 90 days old as well means cleanup can never be
        #   looking at an event any live worker is mid-way through.
        #
        # A correlated EXISTS, not a LEFT JOIN ... IS NULL: the join would
        # build the full delivery set for every event just to discard it.
        #-----------------------------------------------------
        events = _delete_in_batches(
            db,
            select(NotificationEvent.id)
            .where(NotificationEvent.fanned_out_at.isnot(None))
            .where(NotificationEvent.created_at < cutoff)
            .where(
                ~exists().where(
                    NotificationDelivery.event_id == NotificationEvent.id
                )
            ),
            NotificationEvent,
        )

        if deliveries or events:
            logger.info(
                "Notification retention: removed %s read delivery row(s) and "
                "%s orphaned event(s) older than %s days",
                deliveries, events, READ_RETENTION_DAYS,
            )

        return deliveries, events

    finally:
        db.close()


async def background_loop():
    """Fan-out every poll, threshold scan and retention on their own cadences.

    Runs for the lifetime of the app; started and cancelled by main.lifespan.
    """
    logger.info(
        "Notification worker started (fan-out every %ss in batches of %s, "
        "threshold scan every %s polls, retention every %s)",
        POLL_SECONDS, BATCH_SIZE, SCAN_EVERY_N_POLLS, CLEANUP_INTERVAL,
    )

    # BEFORE ANYTHING ELSE, and before the first scan below: a state row that
    # claims an event nobody can find would keep its condition silent for ever,
    # so it is cleared now and re-raised by that scan. See reconcile_state.
    try:
        await run_in_threadpool(run_reconcile_once)
    except Exception:
        # A failed reconciliation must not stop the worker starting. The cost
        # is that a desynchronised row stays silent until the next restart,
        # which is no worse than before this existed.
        logger.exception(
            "Notification state reconciliation failed at startup; continuing"
        )

    polls = 0
    last_cleanup = None

    while True:
        try:
            await asyncio.sleep(POLL_SECONDS)
            polls += 1

            # Sync SQLAlchemy, so every database pass goes to a thread —
            # running one on the loop would block every concurrent request in
            # the process.
            _, _, pushes = await run_in_threadpool(run_once)

            # THE SOCKET SENDS HAPPEN HERE, on the event loop, not in the
            # worker thread that produced them — see fan_out's on_delivered.
            # Each is already scoped to the users the delivery rows were
            # written for, so nobody receives a notification they have no row
            # for.
            for user_ids, message in pushes:
                await manager.broadcast(user_ids, message)

            # THE FIRST POLL SCANS, then every SCAN_EVERY_N_POLLS after it.
            # Without the `polls == 1`, a restart left every threshold
            # unwatched for a full fifteen minutes — the counter starts at
            # zero, so the modulo does not come true until poll 90. A stockout
            # that crossed during the restart would sit unreported for the
            # whole of that window, which is exactly when somebody is most
            # likely to be watching.
            if polls == 1 or polls % SCAN_EVERY_N_POLLS == 0:
                await run_in_threadpool(run_scan_once)

            now = datetime.now(timezone.utc)

            if last_cleanup is None or now - last_cleanup >= CLEANUP_INTERVAL:
                await run_in_threadpool(run_cleanup_once)
                last_cleanup = now

        except asyncio.CancelledError:
            # Shutdown. Re-raised so the task actually ends.
            logger.info("Notification worker stopped")
            raise

        except Exception:
            # Never let a bad pass kill the loop — that would silently stop
            # every notification in the system until the next restart.
            logger.exception(
                "Notification worker pass failed; continuing"
            )


# The N2 name, kept so nothing that imported it breaks. The loop does two jobs
# now, which is why the canonical name changed.
fanout_loop = background_loop
