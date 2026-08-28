from app.logistics.routes.router import router
from app.notifications.lifecycle import notify_created
from app.logistics.helpers import order_reference
from app.logistics.schemas import LogisticsConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_LOGISTICS
from app.logistics.helpers import (
    create_consignment_object, create_child_objects, fetch_consignment,
    resolve_customer_id,
)
from app.logistics.models import LogisticsItem, LogisticsPackage, LogisticsContainer
from app.logistics.serializers import serialize_consignment
import logging

logger = logging.getLogger(__name__)

@router.post("/")
def create_consignment(
        consignment_data : LogisticsConsignmentSchema,
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_ADD_LOGISTICS, db)

        # Create the header and its line objects
        consignment = create_consignment_object(consignment_data, user)

        # The wizard sends a customer name; the master link is derived from it
        # so the two can never disagree.
        resolve_customer_id(consignment, db)

        consignment.items = create_child_objects(consignment_data.items, LogisticsItem)
        consignment.packages = create_child_objects(consignment_data.packages, LogisticsPackage)
        consignment.containers = create_child_objects(consignment_data.containers, LogisticsContainer)

        db.add(consignment)
        db.commit()
        db.refresh(consignment)

        # AFTER the commit, and on the CREATE route only — the wizard PUTs the
        # same draft repeatedly and only this first save is the order starting.
        notify_created(
            db, "logistics", consignment.id,
            reference=order_reference(consignment),
            party=consignment.customer_name or "unknown customer",
        )

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":201,
            "detail":"Order created",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.create_consignment")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
