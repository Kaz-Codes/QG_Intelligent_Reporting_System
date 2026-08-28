import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import update

from app.database import SessionLocal
from app.notifications.helpers import current_user
from app.notifications.models import NotificationDelivery
from app.notifications.routes.router import router

logger = logging.getLogger(__name__)

#-------------------------------------------
# MARK EVERYTHING READ
#
# ONE UPDATE STATEMENT. Not a select followed by a loop of saves: a user who
# has ignored the panel for a fortnight can easily have hundreds of unread
# deliveries, and "Mark all read" must not turn into hundreds of round trips
# holding a pooled connection while somebody watches a spinner.
#
# Scoped to the caller in the WHERE clause, the same way mark_read is, and for
# the same reason — there is no user_id parameter on this route, so there is
# no version of this request that clears somebody else's panel.
#
# `read_at IS NULL` is not just an optimisation. Without it this would rewrite
# read_at on every already-read row and destroy the record of when things were
# actually first seen.
#
# AUTHENTICATED, NOT AUTHORIZED — see app/notifications/helpers.py.
#-------------------------------------------

@router.post("/read-all")
async def mark_all_read(request: Request):
    db = SessionLocal()

    try:
        user = current_user(request, db)

        result = db.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.user_id == user.id)
            .where(NotificationDelivery.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )

        db.commit()

        return {
            "status_code": 200,
            "detail": "All notifications marked read",
            "data": {
                "updated": result.rowcount or 0
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unhandled error in app.notifications.routes.mark_all_read"
        )
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
