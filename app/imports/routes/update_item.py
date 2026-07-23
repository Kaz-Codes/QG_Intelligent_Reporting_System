from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, get_item, prefix_fields, record_change,
    sent_fields,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import ConsignmentItemUpdateSchema
from app.imports.serializers import serialize_item
from fastapi import Request, HTTPException

#-------------------------------------------
# EDIT AN ITEM LINE
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Every field is optional, so the inline edit
# on the wizard can send only what the user
# actually touched. A field that was not sent
# is left exactly as it was rather than being
# blanked.
#
# Item changes are written to the same change
# history as the header, named "item.7.hs_code"
# so one readable trail per consignment covers
# the lot.
#-------------------------------------------

@router.put("/{consignment_id}/items/{item_id}")
async def update_item(consignment_id : int,
                      item_id : int,
                      item_schema : ConsignmentItemUpdateSchema,
                      request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        item = get_item(item_id, consignment.id, db)

        updates = sent_fields(item_schema)
        previous_values, new_values = apply_updates(item, updates)

        record_change(
            consignment.id,
            prefix_fields("item", item.id, previous_values),
            prefix_fields("item", item.id, new_values),
            user.id,
            db
        )

        db.commit()
        db.refresh(item)

        return {
            "status": 200,
            "message": "Item updated",
            "data": serialize_item(item)
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
