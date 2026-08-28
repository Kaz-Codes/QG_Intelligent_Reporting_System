import logging
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.notifications.helpers import current_user
from app.notifications.models import NotificationDelivery, NotificationEvent
from app.notifications.routes.router import router
from app.notifications.serializers import serialize_delivery

logger = logging.getLogger(__name__)

#-------------------------------------------
# THE NOTIFICATION PANEL
#
# The caller's own deliveries, newest first, with the event joined on for the
# title, body, severity and click-through target.
#
# AUTHENTICATED, NOT AUTHORIZED — see app/notifications/helpers.py for why
# there is no permission check here and why adding one would break the panel.
#
# SCOPED TO THE CALLER, ALWAYS. `user_id == user.id` is not a filter the
# client can influence: there is no user_id parameter on this route at all,
# so there is no version of this request that returns somebody else's feed.
#
# INDEX USE. The where/order pair is (user_id, read_at, created_at), which is
# exactly ix_notification_deliveries_user_read_created. unread_only adds
# `read_at IS NULL`, which is the second column, so the same index serves both
# the filtered and unfiltered reads.
#
# The module filter is applied on the EVENT, so it needs the join — which is
# why this one is a real join and not the correlated EXISTS used elsewhere.
# It is safe here: delivery -> event is many-to-one, so joining cannot
# duplicate a delivery row and cannot corrupt the count.
#-------------------------------------------

@router.get("/")
async def list_notifications(request: Request,
                             page: int = 1,
                             page_size: int = 20,
                             unread_only: bool = False,
                             module: Optional[str] = None):
    db = SessionLocal()

    try:
        user = current_user(request, db)

        if page < 1:
            page = 1

        if page_size < 1 or page_size > 100:
            page_size = 20

        filters = [NotificationDelivery.user_id == user.id]

        if unread_only:
            filters.append(NotificationDelivery.read_at.is_(None))

        if module:
            filters.append(NotificationEvent.module == module)

        # Counted over the same join and the same filters as the page itself,
        # so total_pages can never disagree with what paging actually returns.
        total = db.execute(
            select(func.count(NotificationDelivery.id))
            .select_from(NotificationDelivery)
            .join(NotificationEvent,
                  NotificationEvent.id == NotificationDelivery.event_id)
            .where(*filters)
        ).scalar() or 0

        deliveries = db.execute(
            select(NotificationDelivery)
            .join(NotificationEvent,
                  NotificationEvent.id == NotificationDelivery.event_id)
            .where(*filters)
            # joinedload on top of the join above: the join is for filtering,
            # this is for loading. Without it serialize_delivery reads
            # delivery.event per row and the page becomes N+1 queries.
            .options(joinedload(NotificationDelivery.event))
            .order_by(NotificationDelivery.created_at.desc(),
                      NotificationDelivery.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return {
            "status_code": 200,
            "detail": "Notifications fetched",
            "data": [serialize_delivery(d) for d in deliveries],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total else 0
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unhandled error in app.notifications.routes.list_notifications"
        )
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
