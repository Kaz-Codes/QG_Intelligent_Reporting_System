from app.accounts.routes.router import router
from app.database import SessionLocal
from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.accounts.helpers import serialize_user

#-------------------------------------------
# ADMIN CAN VIEW ALL USER ACCOUNTS
# THROUGH THIS API (ADMIN ONLY)
#
# Every account comes back with the name of
# its role, and with the password, since the
# admin is meant to be able to see everyone's
# password. The roles are loaded up front so
# the list does not fire a query per user.
#-------------------------------------------

@router.get("/")
async def get_all_users(request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin"], db)

        users = db.execute(
            select(User)
            .options(selectinload(User.role))
            .order_by(User.username)
        ).scalars().all()

        return {
            "status": 200,
            "message": "Users fetched",
            "data": [serialize_user(user) for user in users]
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
