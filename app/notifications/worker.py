import asyncio
import logging

from sqlalchemy import func, select, update
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.notifications.models import NotificationEvent
from app.notifications.routing import fan_out

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
    """One pass. Returns (events processed, delivery rows written)."""
    db = SessionLocal()

    try:
        events = _claim(db, BATCH_SIZE)
        delivered = 0

        for event in events:
            try:
                delivered += fan_out(db, event)
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

        return len(events), delivered

    finally:
        # Always returned to the pool, however the pass ended.
        db.close()


async def fanout_loop():
    """Wake, drain a batch off the event loop, sleep. Runs for the app's life."""
    logger.info(
        "Notification fan-out worker started (every %ss, batches of %s)",
        POLL_SECONDS, BATCH_SIZE,
    )

    while True:
        try:
            await asyncio.sleep(POLL_SECONDS)
            await run_in_threadpool(run_once)

        except asyncio.CancelledError:
            # Shutdown. Re-raised so the task actually ends.
            logger.info("Notification fan-out worker stopped")
            raise

        except Exception:
            # Never let a bad pass kill the loop — that would silently stop
            # every notification in the system until the next restart.
            logger.exception(
                "Notification fan-out pass failed; continuing"
            )
