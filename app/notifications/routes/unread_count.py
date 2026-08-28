import logging

from fastapi import HTTPException, Request
from sqlalchemy import String, cast, distinct, func, select

from app.database import SessionLocal
from app.notifications.helpers import current_user
from app.notifications.models import NotificationDelivery
from app.notifications.routes.router import router

logger = logging.getLogger(__name__)

#-------------------------------------------
# THE UNREAD BADGE
#
# THE HOTTEST ENDPOINT IN THE FEATURE — every page load in the SPA calls it,
# for every user, all day. So it is deliberately the smallest thing it can be:
#
#   * ONE query. No join to notification_events, because the badge is a
#     number and needs nothing the event holds. Joining here would double the
#     work on the most-called route in the module to render a count.
#   * COUNT ONLY. No rows are fetched, materialised or serialized — the panel
#     asks for the rows separately, and only when somebody actually opens it.
#   * INDEX-ONLY SHAPE. (user_id, read_at IS NULL) is the leading pair of
#     ix_notification_deliveries_user_read_created, so this is a short index
#     range scan whatever the size of the table.
#
# Keep it that way. If the badge ever needs a breakdown — per module, per
# severity — that is a GROUP BY on this same index and still one query; it is
# not a reason to start loading deliveries here.
#
# AUTHENTICATED, NOT AUTHORIZED — see app/notifications/helpers.py.
#-------------------------------------------

@router.get("/unread-count")
async def unread_count(request: Request):
    db = SessionLocal()

    try:
        user = current_user(request, db)

        # COUNTS PANEL ENTRIES, NOT ROWS. A grouped run shows as one entry, so
        # it must count as one — a badge reading 14 over a panel showing 3
        # things is the kind of small disagreement that makes people stop
        # trusting the number. DISTINCT over the group key, falling back to the
        # row's own id for the ungrouped majority, gives exactly that.
        #
        # Still one query over the same index range as before; the DISTINCT
        # adds a heap fetch per unread row, which for a per-user unread set is
        # nothing. If that ever stops being true the fix is to carry the count
        # on the group, not to go back to counting rows.
        entry = func.coalesce(
            NotificationDelivery.group_key,
            cast(NotificationDelivery.id, String),
        )

        count = db.execute(
            select(func.count(distinct(entry)))
            .where(NotificationDelivery.user_id == user.id)
            .where(NotificationDelivery.read_at.is_(None))
        ).scalar() or 0

        return {
            "status_code": 200,
            "detail": "Unread count fetched",
            "data": {
                "unread": count
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unhandled error in app.notifications.routes.unread_count"
        )
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
