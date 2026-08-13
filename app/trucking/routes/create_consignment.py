from app.trucking.routes.router import router
from app.trucking.schemas import TruckingConsignmentSchema
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_TRUCKING
from app.trucking.helpers import (
    create_consignment_object, create_vehicle_object, fetch_consignment,
    resolve_transporter_id,
)
from app.trucking.serializers import serialize_consignment

@router.post("/")
def create_consignment(
        consignment_data : TruckingConsignmentSchema,
        request : Request
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_ADD_TRUCKING, db)

        # Create objects to add in database
        consignment = create_consignment_object(consignment_data, user)

        # The wizard sends a transporter name; the master link is derived
        # from it so the two can never disagree.
        resolve_transporter_id(consignment, db)

        consignment_vehicles = create_vehicle_object(consignment_data)

        consignment.vehicles = consignment_vehicles

        db.add(consignment)
        db.commit()
        db.refresh(consignment)

        consignment = fetch_consignment(db, consignment.id)

        return {
            "status_code":201,
            "detail":"Trucking job created",
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
