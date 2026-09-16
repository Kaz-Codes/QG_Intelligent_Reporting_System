from app.accounts.models import User
from app.auth.verify_token import verify_token
from app.auth import session_activity
from app.auth.router import router
from app.database import SessionLocal
from app.enums import LogAction
from app.logs.helpers import serialize_log, write_log
from app.logs.manager import manager
from fastapi import Request, Response, HTTPException
import logging

logger = logging.getLogger(__name__)

#-------------------------------------------
# LOG OUT AND DROP THE COOKIE
#
# Records the logout, then clears the cookie
# so the token can no longer be used from this
# browser. The token itself just expires on
# its own an hour after it was made.
#
# DELIBERATELY NOT authenticate() here, unlike every other route. That call
# now 401s on an idle session (see authenticate_user.py) - going through it
# here would mean a user who is past the idle threshold and clicks "Log out"
# gets a 401 instead of a clean logout, and the cookie is never cleared
# (response.delete_cookie below would never run). verify_token() only checks
# the JWT signature/expiry, so logout always succeeds for any token this app
# ever issued, idle or not - which is what "log out" should mean.
#-------------------------------------------

@router.post("/logout")
async def logout(request: Request, response: Response):
    db = SessionLocal()

    try:
        token = request.cookies.get("access_token")
        payload = verify_token(token) if token else None

        user_id = payload.get("id") if payload else None
        jti = payload.get("jti") if payload else None

        if jti:
            session_activity.forget(jti)

        user = db.get(User, user_id) if user_id is not None else None

        response.delete_cookie(key="access_token", path="/")

        log = write_log(
            db, user_id, user.username if user else None,
            LogAction.LOGOUT.value,
            method="POST", path="/auth/logout", status_code=200,
            entity_type="auth", detail="Logged out"
        )

        if user_id is not None:
            await manager.broadcast(user_id, serialize_log(log))

        return {
            "status": 200,
            "message": "Logged out"
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.auth.logout")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
