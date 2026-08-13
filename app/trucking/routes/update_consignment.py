from app.trucking.routes.router import router
from app.trucking.schemas import TruckingConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_EDIT_TRUCKING
from app.trucking.helpers import (
    updated_fields, verify_entry_ownership, apply_updates, new_vehicles_to_add,
    updated_vehicles, delete_missing, add_in_consignment_change_history,
    fetch_consignment, resolve_transporter_id,
)
from app.trucking.models import TruckingVehicle
from app.trucking.serializers import serialize_consignment, serialize_many

@router.put("/{consignment_id}")
def update_consignment(
        consignment_data : TruckingConsignmentSchema,
        request : Request,
        consignment_id : int
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_EDIT_TRUCKING, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None:
            raise HTTPException(
                status_code=404,
                detail="Trucking job not found"
            )

        # A closed job (every vehicle delivered) is locked for everyone until
        # an admin reopens it.
        if consignment.is_locked:
            raise HTTPException(
                status_code=423,
                detail="This trucking job is closed. An admin must reopen it before it can be edited."
            )

        verify_entry_ownership(consignment, user, db)

        updation_dict = updated_fields(consignment, consignment_data, db)
        new_vehicles = new_vehicles_to_add(consignment, consignment_data)
        vehicle_updates = updated_vehicles(consignment, consignment_data, db)

        # Deleting vehicles that are no longer in the request body
        present_vehicle_ids = [
            vehicle.id
            for vehicle in consignment_data.vehicles
            if vehicle.id is not None
        ]

        deleted_vehicles = delete_missing(consignment, present_vehicle_ids, TruckingVehicle.id, db, TruckingVehicle)

        # Adding new vehicles
        created_vehicles = []
        for vehicle_schema in new_vehicles:
            vehicle_dict = vehicle_schema.model_dump(exclude_none=True)
            vehicle = TruckingVehicle(**vehicle_dict)
            consignment.vehicles.append(vehicle)
            created_vehicles.append(vehicle)

        db.flush()

        # Adding changes in change history
        add_in_consignment_change_history(updation_dict, serialize_many(created_vehicles), deleted_vehicles, vehicle_updates, consignment, user, db)

        # Applying updates on the job
        apply_updates(updation_dict, consignment)

        # Re-derive the master link AFTER the header updates, so a changed
        # transporter name moves transporter_id with it.
        resolve_transporter_id(consignment, db)

        consignment_vehicles_map = {vehicle.id : vehicle for vehicle in consignment.vehicles}

        # Applying updates on the existing vehicles. The id is read, not
        # popped, so the change history's copy of this dict keeps its id and a
        # revert can still find the vehicle.
        for updated_vehicle in vehicle_updates:
            vehicle_id = updated_vehicle.get("id")
            old_vehicle = consignment_vehicles_map.get(vehicle_id)
            if old_vehicle:
                apply_updates(updated_vehicle, old_vehicle)

        # A plain draft save never closes a job, even if this update marks the
        # last vehicle delivered on an already-submitted record — submission is
        # what closes it (see submit_consignment.py), not merely saving while
        # both conditions happen to be true. Only /submit locks. Mirrors
        # imports and logistics.

        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":200,
            "detail":"Trucking job updated",
            "data":serialize_consignment(consignment)
        }

    except HTTPException:
        db.rollback()
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
