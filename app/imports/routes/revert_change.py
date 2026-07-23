from datetime import date, datetime, timezone

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import (
    apply_updates, from_json, get_change, get_consignment, get_item,
    get_payment, record_change,
)
from app.imports.models import Consignment, ConsignmentItem, Payment
from app.imports.permissions import CAN_REVERT, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# UNDO A CHANGE (ADMIN, MANAGER)
#
# The change history holds what every field
# was before somebody changed it, so undoing
# an edit means writing those old values back
# on top.
#
# Only the fields that actually changed were
# stored, so a revert puts back exactly what
# was touched and leaves everything edited
# since then alone.
#
# A change can only be undone once. The row is
# marked reverted so the same undo cannot be
# applied twice, and the revert itself is
# written to the history as a revert rather
# than disguised as a normal edit, so the
# trail reads honestly.
#
# Child rows were stored as "item.7.hs_code",
# which is how this knows which table and
# which row each old value belongs to.
#-------------------------------------------

def split_field(field):
    parts = field.split(".")

    if len(parts) == 3:
        return parts[0], int(parts[1]), parts[2]

    return "consignment", None, field


@router.post("/changes/{change_id}/revert")
async def revert_change(change_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_REVERT, db)

        change = get_change(change_id, db)

        if change.is_reverted:
            raise HTTPException(
                status_code=400,
                detail="This change has already been reverted"
            )

        if change.is_revert:
            raise HTTPException(
                status_code=400,
                detail="A revert cannot itself be reverted"
            )

        consignment = get_consignment(change.consignment_id, db, include_deleted=True)

        # Grouped by the row each old value belongs to, so
        # one item is updated once instead of once per field.
        grouped = {}

        for field, value in change.previous_values.items():
            table, row_id, column = split_field(field)
            grouped.setdefault((table, row_id), {})[column] = value

        previous_values = {}
        new_values = {}

        for (table, row_id), values in grouped.items():
            if table == "item":
                record = get_item(row_id, consignment.id, db)
                model_class = ConsignmentItem

            elif table == "payment":
                record = get_payment(row_id, consignment.id, db)
                model_class = Payment

            else:
                record = consignment
                model_class = Consignment

            restored = {
                column: from_json(model_class, column, value)
                for column, value in values.items()
            }

            row_previous, row_new = apply_updates(record, restored)

            for column in row_previous:
                if row_id is None:
                    key = column
                else:
                    key = table + "." + str(row_id) + "." + column

                previous_values[key] = row_previous[column]
                new_values[key] = row_new[column]

        change.is_reverted = True
        change.reverted_by_id = user.id
        change.reverted_at = datetime.now(timezone.utc)

        record_change(
            consignment.id, previous_values, new_values, user.id, db,
            is_revert=True
        )

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Change reverted",
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
