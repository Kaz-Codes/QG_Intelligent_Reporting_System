from app.accounts.routes.router import router
from app.accounts.schemas import UserSchema
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.accounts.helpers import serialize_user

#-------------------------------------------
# ADMIN CAN CREATE A NEW ACCOUNT
# THROUGH THIS API (ADMIN ONLY)
#-------------------------------------------

@router.post("/")
async def create_user(user_schema : UserSchema, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin"], db)

        # check whether username already exists
        user_exists = db.execute(
            select(User).where(User.username == user_schema.username)
        ).scalar_one_or_none()

        if user_exists:
            raise HTTPException(
                status_code=400,
                detail = "Username already exists"
            )

        # role on the schema is the role id itself, not an object
        user = User(
            username = user_schema.username,
            password = user_schema.password,
            role_id = user_schema.role
        )

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
