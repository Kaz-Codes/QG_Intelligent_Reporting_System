from fastapi import Request, HTTPException
from app.auth.verify_token import verify_token
from app.auth import session_activity

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

    payload = verify_token(token)

    # CHECKS idleness, never TOUCHES it - only /auth/heartbeat extends a
    # session, so an ordinary authenticated request (a click, a background
    # refetch, anything) can never silently keep an idle session alive. The
    # `if jti` guard matters: a token issued before this feature shipped
    # (still valid for up to 3 hours after deploy) has no jti claim - treat
    # that as "can't check idleness, fall back to the existing 3-hour expiry
    # only", not a crash.
    #
    # DELIBERATELY DOES NOT forget() here. A jti with no entry in
    # session_activity reads as "not idle" (see is_idle's docstring - that's
    # what lets a backend restart NOT mass-log-out everyone), so forgetting on
    # every idle detection would make this a one-time speed bump instead of a
    # lock: the FIRST request after going idle correctly 401s, but forgetting
    # the entry means the very NEXT request with the same cookie - no
    # re-login, no heartbeat - would find no entry and succeed again,
    # reviving a session that should stay dead until the JWT's own 3-hour cap.
    # Verified this concretely before fixing it. Leaving the stale timestamp
    # in place means every subsequent request keeps computing "way more than
    # 30 minutes old" and keeps failing, until a fresh login seeds a new jti.
    # forget() stays logout.py's job alone - that's an explicit "this session
    # is done for good," a different intent than "this one request is late."
    jti = payload.get("jti")
    if jti and session_activity.is_idle(jti):
        raise HTTPException(
            status_code=401,
            detail="Session expired due to inactivity"
        )

    return payload