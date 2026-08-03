from app.accounts.models import User
from app.auth.create_token import create_token
from app.auth.router import router
from app.database import SessionLocal
from app.enums import LogAction
from app.logs.helpers import serialize_log, write_log
from app.logs.manager import manager
from fastapi import Response, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

#-------------------------------------------
# LOG IN AND GET A COOKIE
#
# The username and password come in, and if
# they match an active account a token is made
# and set as a cookie on the reply. The browser
# then sends that cookie back on its own with
# every request, so the client never has to
# hold the token itself.
#
# httponly keeps javascript from reading the
# cookie, which is the whole point of putting
# it in one. The password is compared as it is
# stored, matching how accounts are created
# today.
#-------------------------------------------

TOKEN_HOURS = 3


class LoginSchema(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(credentials: LoginSchema, response: Response):
    db = SessionLocal()

    try:
        user = db.execute(
            select(User).where(User.username == credentials.username)
        ).scalar_one_or_none()

        if user is None or user.password != credentials.password:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Account is inactive"
            )

        token = create_token(
            {
                "id": user.id, 
            }
        )

        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=TOKEN_HOURS * 60 * 60,
            path="/"
        )

        log = write_log(
            db, user.id, user.username, LogAction.LOGIN.value,
            method="POST", path="/auth/login", status_code=200,
            entity_type="auth", detail="Logged in"
        )

        await manager.broadcast(user.id, serialize_log(log))

        return {
            "status": 200,
            "message": "Logged in",
            "data": {"id": user.id, "username": user.username}
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
