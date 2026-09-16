from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from jose import jwt
from uuid import uuid4
import os

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"


def create_token(data: dict):
    """Returns (token, jti). `jti` is a per-login session id used by
    session_activity to track idle time - keyed separately from `id` (the
    user) so logging in on a second device doesn't reset the first session's
    idle clock. `setdefault` lets a caller pass its own jti explicitly, though
    nothing in this codebase does today."""

    payload = data.copy()
    payload.setdefault("jti", uuid4().hex)

    expire = datetime.now(timezone.utc) + timedelta(hours=3)

    payload["exp"] = expire

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token, payload["jti"]