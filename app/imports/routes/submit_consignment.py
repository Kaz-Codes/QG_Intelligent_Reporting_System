from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.permissions import CAN_EDIT, allow
from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.imports.helpers import get_consignment
from app.imports.permissions import CAN_EDIT, allow, check_owner

@router.put("/submit/{consignment_id}")
def submit_consignment(consignment_id : int, request:Request):
    db = SessionLocal()
    try:
        request_user_data = authenticate(request)
        user, role_name = allow(request_user_data, CAN_EDIT, db)
        
        consignment = get_consignment(consignment_id, db)
        check_owner(user, role_name, consignment)
        consignment.is_draft = False
        db.commit()
        db.refresh(consignment)

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

