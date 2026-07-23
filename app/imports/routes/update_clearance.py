from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, record_change, sent_fields,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import ClearanceSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 6 OF THE WIZARD, CUSTOM CLEARANCE
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Clearing agent, GD number, free days, gate
# out and whatever demurrage was paid.
#
# Clearance time is not accepted here. It is
# gate out minus the day the status became
# "Arrived at port", read out of the status
# log, and it falls back to the ETA only while
# that status has not been recorded. Free days
# and detention are billed from a real
# arrival, not a predicted one, so the
# response also says which of the two the
# figures were worked out from.
#-------------------------------------------

@router.put("/{consignment_id}/clearance")
async def update_clearance(consignment_id : int,
                           clearance_schema : ClearanceSchema,
                           request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        updates = sent_fields(clearance_schema)

        previous_values, new_values = apply_updates(consignment, updates)
        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Clearance updated",
            "data": serialize_consignment(consignment, date.today())
        }

    except HTTPException:
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
