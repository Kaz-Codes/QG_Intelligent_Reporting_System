from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import apply_updates, get_consignment, record_change
from app.imports.models import StatusUpdateHistory
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import StatusChangeSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 5 OF THE WIZARD, MOVE THE CONSIGNMENT
# TO A NEW STAGE
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# The status is not just written over the top
# of the old one. Every change appends a row
# to the status log, which is what gives the
# audit trail and makes stage ageing questions
# like "how long do we typically sit under
# examination" answerable at all.
#
# effective_date is the day the stage actually
# changed, which is usually not the day
# somebody got round to entering it. Clearance
# timing counts from the effective date of the
# "Arrived at port" row, so this date matters
# more than it looks.
#
# Going backwards a stage is allowed. It
# happens, and refusing it would just mean
# somebody enters the wrong thing instead. It
# stays visible in the history.
#-------------------------------------------

@router.post("/{consignment_id}/status")
async def change_status(consignment_id : int,
                        status_schema : StatusChangeSchema,
                        request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        previous_status = consignment.current_status
        new_status = status_schema.new_status.value

        if previous_status == new_status:
            raise HTTPException(
                status_code=400,
                detail="Consignment is already at this status"
            )

        db.add(
            StatusUpdateHistory(
                consignment_id=consignment.id,
                previous_status=previous_status,
                new_status=new_status,
                effective_date=status_schema.effective_date,
                remarks=status_schema.remarks,
                user_id=user.id
            )
        )

        previous_values, new_values = apply_updates(
            consignment, {"current_status": new_status}
        )

        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Status updated",
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
