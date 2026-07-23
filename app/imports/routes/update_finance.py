from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, get_consignment, get_item, prefix_fields, record_change,
    sent_fields,
)
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import FinanceSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 2 OF THE WIZARD, FINANCE
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# The payment instrument, the works, the
# exchange rate, and the unit price on every
# item line, saved together because that is
# how the screen is filled in.
#
# The rate is booked here with the date it was
# taken and where it came from. It is stored
# on the consignment on purpose. A stored
# foreign value is never re converted at a
# live rate, or the same record would show a
# different PKR figure every time somebody
# opened it and no printed report could be
# reconciled.
#
# The consignment total is never sent in. It
# is the sum of the item lines and is worked
# out on the way back.
#-------------------------------------------

@router.put("/{consignment_id}/finance")
async def update_finance(consignment_id : int,
                         finance_schema : FinanceSchema,
                         request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        updates = sent_fields(finance_schema, ignore=["item_prices"])

        previous_values, new_values = apply_updates(consignment, updates)

        for price in finance_schema.item_prices:
            item = get_item(price.item_id, consignment.id, db)

            item_previous, item_new = apply_updates(
                item, {"unit_price": price.unit_price}
            )

            previous_values.update(prefix_fields("item", item.id, item_previous))
            new_values.update(prefix_fields("item", item.id, item_new))

        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Finance updated",
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
