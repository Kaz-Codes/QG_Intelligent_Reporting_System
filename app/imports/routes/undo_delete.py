from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from app.imports.helpers import fetch_consignment, reconcile_allocation, AllocationError, sync_group_deleted_state
from app.imports.serializers import serialize_consignment
import logging

logger = logging.getLogger(__name__)

@router.post("/undo-delete/{consignment_id}")
def undo_delete(
        consignment_id : int, 
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # ADMIN ONLY, and necessarily so: the only way to see a deleted record
        # is the admin-only `include_deleted` view, so nobody else could reach
        # this in the first place.
        user = require_admin(user_payload, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        consignment.is_deleted = False
        consignment.deleted_by_id = None
        consignment.deleted_at = None

        # UNDOING A DELETE RE-CLAIMS THE QUANTITY, AND THAT CAN FAIL.
        #
        # This is the mirror of the release in the delete route and it is the
        # one direction that can refuse. Deleting a batch frees its allocation;
        # if a REPLACEMENT batch has since been created for that quantity,
        # bringing the original back pushes the order past what it bought -
        # order 250, batch A deleted at 150, batch B created for 150, undo A
        # and the order is committed to 300.
        #
        # Before this, undo-delete was a bare flag flip with no check of any
        # kind, so that state was reachable and silent: the CHECK constraint
        # only ever sees `allocated_quantity`, which nothing recomputed here.
        # The refusal names the item and the overage, so the admin can see that
        # the quantity has been re-committed and decide which batch should
        # actually hold it.
        # THE ORDER COMES BACK WITH THE BATCH, and it has to come back
        # BEFORE the allocation is reconciled - a restored batch under an order
        # still marked deleted is the state that made the batch route refuse to
        # add anything to it. Found by driving that route, not by reading this
        # one.
        sync_group_deleted_state(db, consignment.batch_group_id)

        reconcile_allocation(db, consignment.batch_group_id)

        db.commit()
        db.refresh(consignment)

        return {
            "status_code":200,
            "detail":"Consignment reverted",
            "data":serialize_consignment(consignment, db)
        }

    except AllocationError as e:
        # THE REAL PATH, not a formality: restoring a batch whose quantity has
        # been re-allocated elsewhere is refused here, with the overage named.
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.undo_delete")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 