from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import get_consignment, prefix_fields, record_change, to_json
from app.imports.models import ConsignmentItem
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import ConsignmentItemSchema
from app.imports.serializers import serialize_item
from fastapi import Request, HTTPException

#-------------------------------------------
# ADD AN ITEM LINE TO A CONSIGNMENT
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# One consignment carries many items, and it
# can carry a Store item and an Engineering
# item together, which is why the requisition
# details sit on the line and not on the
# header.
#
# The code, name, specification and unit are
# whatever the caller sends. The frontend
# copies them off the item master when the
# item is picked, and the line keeps its own
# copy from then on.
#-------------------------------------------

@router.post("/{consignment_id}/items")
async def add_item(consignment_id : int,
                   item_schema : ConsignmentItemSchema,
                   request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        item = ConsignmentItem(
            consignment_id=consignment.id,
            item_id=item_schema.item_id,
            item_code=item_schema.item_code,
            item_name=item_schema.item_name,
            specification=item_schema.specification,
            hs_code=item_schema.hs_code,
            quantity=item_schema.quantity,
            unit_price=item_schema.unit_price,
            unit_of_measurement=item_schema.unit_of_measurement,
            batch_no=item_schema.batch_no,
            requisition_type=item_schema.requisition_type,
            reference_number=item_schema.reference_number,
            job_number=item_schema.job_number,
            mo_number=item_schema.mo_number,
            description=item_schema.description
        )

        db.add(item)
        db.flush()

        record_change(
            consignment.id,
            {},
            prefix_fields("item", item.id, {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "quantity": to_json(item.quantity)
            }),
            user.id,
            db
        )

        db.commit()
        db.refresh(item)

        return {
            "status": 201,
            "message": "Item added",
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
