import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func, select, update

from app.database import SessionLocal
from app.notifications.helpers import current_user
from app.notifications.models import NotificationDelivery
from app.notifications.routes.router import router

logger = logging.getLogger(__name__)

#-------------------------------------------
# MARK ONE NOTIFICATION READ
#
# OWNERSHIP IS ENFORCED IN THE WHERE CLAUSE, NOT BY A CHECK BEFORE IT.
#
# `user_id == user.id` sits in the UPDATE itself, so a delivery belonging to
# somebody else cannot be marked read: it simply is not among the rows the
# statement can touch. Loading the row, comparing owners in Python and then
# updating would be the same rule written twice, with a window between the
# two — and it is the kind of check that gets refactored away later because
# "the update already filters". This way there is only one place it lives.
#
# A delivery that does not exist and a delivery belonging to another user are
# BOTH answered with 404, identically. Answering 403 for the second would
# confirm that the id exists, which is exactly what somebody probing ids is
# trying to learn.
#
# IDEMPOTENT. Marking an already-read notification read again succeeds and
# leaves the original read_at alone — the panel fires this on click, and a
# double click is not an error. `read_at IS NULL` in the WHERE is what
# preserves the first timestamp; the follow-up query is only there to tell
# "already read" apart from "not yours".
#
# AUTHENTICATED, NOT AUTHORIZED — see app/notifications/helpers.py.
#-------------------------------------------

@router.post("/{delivery_id}/read")
async def mark_read(request: Request, delivery_id: int):
    db = SessionLocal()

    try:
        user = current_user(request, db)

        updated = db.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id)
            .where(NotificationDelivery.user_id == user.id)
            .where(NotificationDelivery.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
            .returning(NotificationDelivery.id)
        ).scalars().all()

        db.commit()

        if not updated:
            # Either already read (fine) or not the caller's (404). The same
            # user_id scope applies, so this cannot confirm another user's row.
            exists = db.execute(
                select(func.count(NotificationDelivery.id))
                .where(NotificationDelivery.id == delivery_id)
                .where(NotificationDelivery.user_id == user.id)
            ).scalar() or 0

            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail="Notification not found"
                )

        return {
            "status_code": 200,
            "detail": "Notification marked read",
            "data": {
                "id": delivery_id
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        logger.exception(
            "Unhandled error in app.notifications.routes.mark_read"
        )
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
