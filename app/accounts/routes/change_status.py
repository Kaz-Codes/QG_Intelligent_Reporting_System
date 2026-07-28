from app.accounts.routes.router import router
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from fastapi import Request, HTTPException
from app.accounts.helpers import check_existence, serialize_user

#-------------------------------------------
# ADMIN CAN ACTIVATE OR DEACTIVATE AN ALREADY
# EXISTING USER
# THROUGH THIS API (ADMIN ONLY)
#
# The path is /users/{id}/status so it does not
# clash with the edit route, which is also a PUT
# on /users/{id}. is_active comes in as a plain
# true/false.
#-------------------------------------------

@router.put("/{id}/status")
async def change_status(id : int, is_active: bool, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin"], db)

        user = check_existence(id, User, db)
        user.is_active = is_active

        db.commit()
        db.refresh(user)

        return {
            "status":200,
            "message": "User status updated",
            "data": serialize_user(user)
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
