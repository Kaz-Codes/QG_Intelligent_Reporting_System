from app.accounts.models import User
from app.auth.verify_token import verify_token
from app.database import SessionLocal
from app.logs.helpers import (
    classify_action, parse_entity, serialize_log, write_log,
)
from app.logs.manager import manager

#-----------------------------------------------------
# LOG EVERY ACTION IN ONE PLACE
#
# Instead of a logging line in all twenty-odd routes, this
# sits in front of them and writes a log for anything that
# changes data. A read (GET) is not an action, so it is left
# alone. Login and logout write their own logs, so they are
# skipped here too.
#
# The acting user is read from the same cookie the routes
# use. If there is no valid token there is nobody to pin the
# action on, so nothing is logged.
#
# Whatever it writes, it also sends straight to any admin
# who happens to be watching that user's live feed.
#-----------------------------------------------------

LOGGED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Handled by the login and logout routes themselves.
SKIP_PATHS = ("/auth/login", "/auth/logout")


def _read_token(request):
    token = request.cookies.get("access_token")

    if not token:
        header = request.headers.get("Authorization")

        if header:
            token = header.replace("Bearer ", "")

    return token


def _read_user(token):
    try:
        payload = verify_token(token)
    except Exception:
        return None

    if isinstance(payload, dict):
        return payload.get("id")

    return getattr(payload, "id", None)


async def log_requests(request, call_next):
    # Let the route run first, so the log can record how it
    # turned out.
    response = await call_next(request)

    try:
        should_log = (
            request.method in LOGGED_METHODS
            and not request.url.path.startswith(SKIP_PATHS)
        )

        if should_log:
            token = _read_token(request)
            user_id = _read_user(token) if token else None

            if user_id is not None:
                db = SessionLocal()

                try:
                    user = db.get(User, user_id)
                    username = user.username if user else None

                    entity_type, entity_id = parse_entity(request.url.path)
                    action = classify_action(request.method, request.url.path)

                    log = write_log(
                        db, user_id, username, action,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        detail=request.method + " " + request.url.path
                    )

                    await manager.broadcast(user_id, serialize_log(log))

                finally:
                    db.close()

    except Exception as e:
        # Logging must never take a request down with it.
        print(e)

    return response
