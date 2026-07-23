from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from jose import jwt
import os

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"


def create_token(data: dict):

    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(hours=1)

    payload["exp"] = expire

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )