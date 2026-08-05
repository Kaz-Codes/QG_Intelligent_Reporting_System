from app.accounts.routes.router import router
from app.accounts.schemas import UserSchema
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.accounts.helpers import serialize_user, apply_account_access

#-------------------------------------------
# ADMIN CAN CREATE A NEW ACCOUNT
# THROUGH THIS API (ADMIN ONLY)
#-------------------------------------------

@router.post("/")
async def create_user(user_schema : UserSchema, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        require_admin(request_user_data, db)

        # check whether username already exists
        user_exists = db.execute(
            select(User).where(User.username == user_schema.username)
        ).scalar_one_or_none()

        if user_exists:
            raise HTTPException(
                status_code=400,
                detail = "Username already exists"
            )

        user = User(
            username = user_schema.username,
            password = user_schema.password,
        )
        # Checkbox -> admin (no permissions), otherwise the chosen permissions.
        apply_account_access(db, user, user_schema.is_admin, user_schema.permissions)

        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "status":201,
            "message": "User created",
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
