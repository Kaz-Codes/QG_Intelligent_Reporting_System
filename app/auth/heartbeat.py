from fastapi import Request
from app.auth.authenticate_user import authenticate
from app.auth import session_activity
from app.auth.router import router

#-------------------------------------------
# THE ONLY CALLER OF session_activity.touch()
#
# The frontend calls this in response to real interaction events (mousemove,
# keydown, click, scroll, touchstart), throttled to roughly once a minute -
# never on a timer independent of user activity. That is what makes this the
# one and only place that counts as "the user is still here"; every other
# route just CHECKS idleness via authenticate() without extending it.
#
# Deliberately tiny - no DB call, no logging, nothing but the touch - since
# it gets called frequently-ish and needs to stay cheap.
#-------------------------------------------

@router.post("/heartbeat")
async def heartbeat(request: Request):
    payload = authenticate(request)   # 401s here exactly like any other route
    jti = payload.get("jti")
    if jti:
        session_activity.touch(jti)
    return {"status": 200}
