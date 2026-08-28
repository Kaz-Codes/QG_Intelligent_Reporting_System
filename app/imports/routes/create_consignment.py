from app.imports.routes.router import router
from app.notifications.lifecycle import notify_created
from app.imports.helpers import consignment_reference
from app.imports.schemas import ConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_IMPORTS
from app.imports.helpers import create_consignment_item_object, create_consignment_object, create_payment_object, stamp_landed_cost_audit, recompute_derived, apply_item_master_values

from app.imports.serializers import serialize_consignment
import logging

logger = logging.getLogger(__name__)

@router.post("/")
def create_consignment(
        consignment_data : ConsignmentSchema, 
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, CAN_ADD_IMPORTS, db)

        # Create objects to add in daatabase
        consignment = create_consignment_object(consignment_data, user)
        consignment_payments = create_payment_object(consignment_data)
        consignment_items = create_consignment_item_object(consignment_data)

        consignment.items = consignment_items
        consignment.payments = consignment_payments

        # Record who entered any landed-cost figure supplied at entry.
        for item in consignment_items:
            stamp_landed_cost_audit(item, user, item.elc is not None, item.alc is not None)

        # A line whose code is in the item master takes its name and
        # specification from there, whatever the payload said. The wizard
        # locks those inputs too; this is the part that actually guarantees it.
        apply_item_master_values(consignment, db)

        # Store the derived money totals + per-line variance.
        recompute_derived(consignment)

        db.add(consignment)
        db.commit()
        db.refresh(consignment)

        # AFTER the commit. The record is durable by this point, so nothing
        # the notification does can undo it — and emit() holds its own
        # session, so it could not reach this transaction even if it were
        # still open. Fires on the CREATE route only: the wizard saves the
        # same draft repeatedly through PUT, and only this first save is the
        # record starting.
        notify_created(
            db, "imports", consignment.id,
            reference=consignment_reference(consignment),
            party=consignment.supplier.name if consignment.supplier else "unknown supplier",
            branch=consignment.branch.name if consignment.branch else None,
        )

        return {
            "status_code":201,
            "detail":"Consignment created",
            "data":serialize_consignment(consignment, db)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.create_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 