from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, get_item, prefix_fields, record_change,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import LandedCostSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 7 OF THE WIZARD, LANDED COST
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Estimated and actual landed cost, per item,
# in PKR. Both are typed in by a user and
# nothing in this system works either of them
# out. Duty, freight, port handling and
# clearing agent fees are not tracked here at
# all.
#
# The goods value, bank charges and demurrage
# that come back alongside are reference
# figures only, to sanity check what somebody
# typed. They are never summed into ELC or
# ALC.
#
# ELC and ALC are usually entered weeks apart
# by different people. Only what changed is
# written to the change history, so it stays
# obvious from one row which of the two
# somebody actually touched.
#-------------------------------------------

@router.put("/{consignment_id}/landed-cost")
async def update_landed_cost(consignment_id : int,
                             landed_cost_schema : LandedCostSchema,
                             request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        previous_values = {}
        new_values = {}

        for line in landed_cost_schema.items:
            item = get_item(line.item_id, consignment.id, db)

            updates = line.model_dump(exclude_unset=True)
            updates.pop("item_id", None)

            item_previous, item_new = apply_updates(item, updates)

            previous_values.update(prefix_fields("item", item.id, item_previous))
            new_values.update(prefix_fields("item", item.id, item_new))

        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Landed cost updated",
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
