from app.accounts.models import User
from app.auth.authenticate_user import authenticate
from app.auth.router import router
from app.database import SessionLocal
from app.enums import LogAction
from app.logs.helpers import serialize_log, write_log
from app.logs.manager import manager
from fastapi import Request, Response, HTTPException

#-------------------------------------------
# LOG OUT AND DROP THE COOKIE
#
# Records the logout, then clears the cookie
# so the token can no longer be used from this
# browser. The token itself just expires on
# its own an hour after it was made.
#-------------------------------------------

@router.post("/logout")
async def logout(request: Request, response: Response):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)

        if isinstance(request_user_data, dict):
            user_id = request_user_data.get("id")
        else:
            user_id = getattr(request_user_data, "id", None)

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
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
