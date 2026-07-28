from app.logistics.routes.router import router
from app.logistics.schemas import LogisticsConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.logistics.helpers import (
    updated_fields, verify_entry_ownership, apply_updates,
    add_in_consignment_change_history, add_in_status_change_history,
    fetch_consignment,
)
from app.logistics.serializers import serialize_consignment

@router.put("/{consignment_id}")
def update_consignment(
        consignment_data : LogisticsConsignmentSchema,
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, ["admin", "manager", "entry operator"], db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        verify_entry_ownership(consignment, user, db)

        updation_dict = updated_fields(consignment, consignment_data, db)

        # Adding changes in change history and status history
        add_in_consignment_change_history(updation_dict, consignment, user, db)
        add_in_status_change_history(updation_dict, consignment, user, db)

        # Applying updates
        apply_updates(updation_dict, consignment)

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Order updated",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
