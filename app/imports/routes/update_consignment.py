from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, record_change, sent_fields,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 1 OF THE WIZARD, ON AN EXISTING
# CONSIGNMENT (ADMIN, MANAGER, OWN ENTRIES
# FOR AN ENTRY OPERATOR)
#
# Only the header is touched here. Item lines
# have their own calls, because the wizard
# adds and edits them one at a time rather
# than resubmitting the whole set.
#
# Whatever a field held before the change is
# written to the change history, which is what
# makes the edit revertable later.
#-------------------------------------------

@router.put("/{consignment_id}")
async def update_consignment(consignment_id : int,
                             consignment_schema : ConsignmentSchema,
                             request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        updates = sent_fields(consignment_schema, ignore=["items"])

        previous_values, new_values = apply_updates(consignment, updates)
        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Consignment updated",
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
