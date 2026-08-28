from app.logistics.routes.router import router
from app.notifications.lifecycle import notify_deleted, format_money
from app.logistics.helpers import order_reference
from app.dashboard.logistics.calculations import total_logistics_cost
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from app.logistics.helpers import fetch_consignment
from app.logistics.serializers import serialize_consignment
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

@router.delete("/{consignment_id}")
def delete_consignment(
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # ADMIN ONLY. Deleting used to need `can_delete_*` plus ownership, so a
        # data-entry user could remove their own records; the business wants
        # removal to be one person's decision. `require_admin` is the same gate
        # reopen uses, and it is the SERVER-SIDE boundary — the list hiding the
        # button for everyone else is only UX.
        user = require_admin(user_payload, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        # Nothing is really deleted, only flagged
        consignment.is_deleted = True
        consignment.deleted_by_id = user.id
        consignment.deleted_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(consignment)

        # AFTER the commit, carrying enough to identify what vanished — the
        # row is hidden from every list from here on.
        notify_deleted(
            db, "logistics", consignment.id,
            reference=order_reference(consignment),
            party=consignment.customer_name or "unknown customer",
            value=format_money(total_logistics_cost(consignment)),
            deleted_by=user.username,
        )

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Order deleted",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.delete_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
