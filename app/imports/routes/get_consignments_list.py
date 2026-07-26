from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.imports.helpers import fetch_all_consignments
from app.imports.serializers import serialize_consignment
from typing import Optional

@router.get("/")
def get_consignments_list(
    request : Request,
    include_deleted : Optional[bool] = False
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this 
        # action)
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        consignments = fetch_all_consignments(db, include_deleted)

        # Serializeing all consignments
        serialized_consignments = [
            serialize_consignment(consignment, db) for consignment in consignments
        ]
      
        return {
            "status_code":200,
            "detail":"Consignments fetched",
            "data":serialized_consignments
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
 