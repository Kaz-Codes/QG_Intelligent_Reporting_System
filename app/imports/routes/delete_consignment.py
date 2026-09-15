from app.imports.routes.router import router
from app.notifications.lifecycle import notify_deleted, format_money
from app.imports.order_view import reference_label
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from app.imports.helpers import fetch_consignment, reconcile_allocation, AllocationError, sync_group_deleted_state
from app.imports.serializers import serialize_consignment
from datetime import datetime, timezone
import logging
from app.imports.order_view import order_branch_name, order_supplier_name

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
                detail="Consignment not found"
            )

        consignment.is_deleted = True
        consignment.deleted_by_id = user.id
        consignment.deleted_at = datetime.now(timezone.utc)

        # DELETING A BATCH RELEASES ITS ALLOCATION.
        #
        # `allocation_totals` counts only lines on LIVE batches, so this
        # recomputes the order's allocation without the batch just removed and
        # frees that quantity for whatever ships instead. Without it the
        # quantity would be stranded for ever - committed to a shipment nobody
        # can see and unavailable to its replacement - and `allocated_quantity`
        # would go on describing lines whose batch is gone.
        #
        # It also retires the order line if this was the last batch carrying
        # it, and it CANNOT refuse: removing lines only ever lowers a sum.
        #
        # THE NUMBER IS NOT RELEASED WITH IT. `batch_sequence` stays taken and
        # `batches_ever` is not decremented, so deleting 177-2 leaves 177-1 and
        # 177-3 with a gap and 177-1 does NOT revert to a bare 177. A number
        # that has been on an invoice must never come to mean a different
        # shipment (design section 3.5, decision A3).
        reconcile_allocation(db, consignment.batch_group_id)

        # AND THE ORDER GOES WITH THE LAST BATCH. Deleting a consignment used
        # to set the flag on the consignment alone, leaving the group's own
        # `is_deleted` untouched for ever - it had no writer in the
        # application at all. See sync_group_deleted_state.
        sync_group_deleted_state(db, consignment.batch_group_id)

        db.commit()
        db.refresh(consignment)

        # AFTER the commit, and carrying enough to identify what vanished —
        # the row is hidden from every list from here on, so a reader cannot
        # look any of this up for themselves.
        notify_deleted(
            db, "imports", consignment.id,
            reference=reference_label(consignment),
            party=order_supplier_name(consignment) or "unknown supplier",
            value=format_money(consignment.pkr_total),
            deleted_by=user.username,
            branch=order_branch_name(consignment),
        )

        return {
            "status_code":200,
            "detail":"Consignment deleted",
            "data":serialize_consignment(consignment, db)
        }

    except AllocationError as e:
        # Unreachable on this route - a delete only ever lowers the sum - but
        # present because the call is, and an unhandled one would surface as a
        # 500 on a delete that had already half-run.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.delete_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 