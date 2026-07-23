from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.enums import Status
from app.imports.models import Consignment, ConsignmentItem, StatusUpdateHistory
from app.imports.permissions import CAN_CREATE, allow
from app.imports.routes.router import router
from app.imports.schemas import ConsignmentSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 1 OF THE WIZARD
# CREATE A NEW CONSIGNMENT WITH ITS ITEM
# LINES (ADMIN, MANAGER, ENTRY OPERATOR)
#
# This is the only call that makes a
# consignment. Everything after it updates one
# that already exists, because each wizard
# step saves on its own and users are
# interrupted halfway through constantly.
#
# The item lines copy the code, name,
# specification and unit off the item master
# on the way in and then keep their own copy.
# Editing that master next year must not
# rewrite what a consignment cleared under
# last year.
#-------------------------------------------

@router.post("/")
async def create_consignment(consignment_schema : ConsignmentSchema, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_CREATE, db)

        consignment = Consignment(
            branch_id=consignment_schema.branch_id,
            supplier_id=consignment_schema.supplier_id,
            origin=consignment_schema.origin,
            currency=consignment_schema.currency,
            consignment_type=consignment_schema.consignment_type,
            po_date=consignment_schema.po_date,
            current_status=Status.TT_LC_IN_PROCESS.value,
            created_by_id=user.id
        )

        db.add(consignment)
        db.flush()

        for item_schema in consignment_schema.items:
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

        # The first status is an event like every other one,
        # so the stage ageing report has a day to count from
        # rather than a consignment that appears out of
        # nowhere already in progress.
        db.add(
            StatusUpdateHistory(
                consignment_id=consignment.id,
                previous_status=None,
                new_status=Status.TT_LC_IN_PROCESS.value,
                effective_date=date.today(),
                remarks="Consignment created",
                user_id=user.id
            )
        )

        db.commit()
        db.refresh(consignment)

        return {
            "status": 201,
            "message": "Consignment created",
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
