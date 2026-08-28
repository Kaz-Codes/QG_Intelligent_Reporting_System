from app.accounts.routes.router import router
from app.accounts.schemas import UserSchema
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import require_admin
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.accounts.helpers import (
    check_existence, serialize_user, apply_account_access,
    apply_notification_settings,
)
import logging

logger = logging.getLogger(__name__)

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
        # require_admin hands back the acting user, which
        # apply_notification_settings needs to decide whether the tier may be
        # changed — see the note in helpers.py.
        acting_user = require_admin(request_user_data, db)

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
        user.is_active = user_schema.is_active
        apply_account_access(db, user, user_schema.is_admin, user_schema.permissions)
        apply_notification_settings(db, user, user_schema, acting_user)

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
        logger.exception("Unhandled error in app.accounts.routes.edit_user")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
