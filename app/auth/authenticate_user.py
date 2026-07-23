from fastapi import Request, HTTPException
from app.auth.verify_token import verify_token

def authenticate(request: Request):

    # The token is kept in a cookie now, so that is checked
    # first. The Authorization header is still accepted as a
    # fallback so anything that was calling with a Bearer
    # token keeps working.
    token = request.cookies.get("access_token")

    if not token:
        auth_header = request.headers.get("Authorization")

        if auth_header:
            token = auth_header.replace("Bearer ", "")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing token"
        )

    return verify_token(token)