from typing import Optional

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.auth.authorize_user import authorize
from app.logs.helpers import serialize_log
from app.logs.models import ActivityLog
from app.logs.routes.router import router
from fastapi import Request, HTTPException
from sqlalchemy import select

#-------------------------------------------
# THE STORED LOG HISTORY (ADMIN ONLY)
#
# What the live feed shows is only what has
# happened since the screen was opened, so
# this loads the history that came before it,
# newest first.
#
# With no user id it returns everyone's
# actions. With one it returns just that
# user's, which is the individual per user
# view the admin asked for.
#-------------------------------------------

@router.get("/")
async def list_logs(request: Request,
                    user_id : Optional[int] = None,
                    limit : int = 100):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin"], db)

        if limit < 1 or limit > 500:
            limit = 100

        query = select(ActivityLog)

        if user_id is not None:
            query = query.where(ActivityLog.user_id == user_id)

        query = query.order_by(ActivityLog.id.desc()).limit(limit)

        logs = db.execute(query).scalars().all()

        return {
            "status": 200,
            "message": "Logs fetched",
            "data": [serialize_log(log) for log in logs]
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
