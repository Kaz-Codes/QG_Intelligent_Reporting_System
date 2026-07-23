from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.calculations import ETA_TYPE, ETA_WORKS_TYPE
from app.imports.helpers import (
    apply_updates, get_consignment, record_change, sent_fields,
)
from app.imports.models import EtaRevisionHistory
from app.imports.permissions import CAN_EDIT, allow, check_owner
from app.imports.routes.router import router
from app.imports.schemas import ShippingSchema
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# STEP 3 OF THE WIZARD, SHIPPING
# (ADMIN, MANAGER, OWN ENTRIES FOR AN ENTRY
# OPERATOR)
#
# Mode, ports, readiness date and the three
# dates. Transit time is not accepted here,
# it is ETA minus ETD and is worked out on the
# way back.
#
# The ETA is never simply overwritten. Moving
# it appends a row to the revision history
# with who moved it, when and why, and a
# reason is insisted on. That log is what the
# "1st ETA was X, 2nd was Y" line in reports
# is built from, and it is what makes slippage
# on the list view mean anything. Storing it
# as a text field would destroy the delay
# analytics and could be overwritten by a user
# edit.
#
# Setting an ETA for the very first time is
# not a revision, so no reason is asked for.
#-------------------------------------------

def log_eta_revision(consignment_id, eta_type, previous_eta, new_eta,
                     cause_of_revision, user_id, db):

    if previous_eta is not None and not cause_of_revision:
        raise HTTPException(
            status_code=400,
            detail="A cause is required when the ETA is revised"
        )

    db.add(
        EtaRevisionHistory(
            consignment_id=consignment_id,
            eta_type=eta_type,
            previous_eta=previous_eta,
            new_eta=new_eta,
            cause_of_revision=cause_of_revision,
            user_id=user_id
        )
    )


@router.put("/{consignment_id}/shipping")
async def update_shipping(consignment_id : int,
                          shipping_schema : ShippingSchema,
                          request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)

        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)

        updates = sent_fields(shipping_schema, ignore=["cause_of_revision"])

        # Read before the update is applied, otherwise the
        # old date is gone by the time it is logged.
        old_eta = consignment.eta
        old_eta_works = consignment.eta_works

        eta_changed = "eta" in updates and updates["eta"] != old_eta and updates["eta"] is not None
        eta_works_changed = (
            "eta_works" in updates
            and updates["eta_works"] != old_eta_works
            and updates["eta_works"] is not None
        )

        previous_values, new_values = apply_updates(consignment, updates)

        if eta_changed:
            log_eta_revision(
                consignment.id, ETA_TYPE, old_eta, consignment.eta,
                shipping_schema.cause_of_revision, user.id, db
            )

        if eta_works_changed:
            log_eta_revision(
                consignment.id, ETA_WORKS_TYPE, old_eta_works, consignment.eta_works,
                shipping_schema.cause_of_revision, user.id, db
            )

        record_change(consignment.id, previous_values, new_values, user.id, db)

        db.commit()
        db.refresh(consignment)

        return {
            "status": 200,
            "message": "Shipping updated",
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
