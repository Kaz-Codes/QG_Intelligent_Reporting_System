from app.accounts.routes.router import router
from app.accounts.schemas import UserSchema
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.accounts.helpers import check_existence, serialize_user

#-------------------------------------------
# ADMIN CAN EDIT THE DETAILS OF AN ALREADY
# EXISTING USER
# THROUGH THIS API (ADMIN ONLY)
#-------------------------------------------

@router.put("/{id}")
async def edit_user(id : int, user_schema : UserSchema, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin"], db)

        user = check_existence(id, User, db)

        # the new username may already belong to a DIFFERENT
        # user. The one being edited is allowed to keep its
        # own name.
        clash = db.execute(
            select(User).where(
                User.username == user_schema.username,
                User.id != user.id
            )
        ).scalar_one_or_none()

        if clash:
            raise HTTPException(
                status_code=400,
                detail = "Username already exists"
            )

        user.username = user_schema.username
        user.password = user_schema.password
        user.role_id = user_schema.role

        db.commit()
        db.refresh(user)

        return {
            "status":200,
            "message": "User updated",
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
