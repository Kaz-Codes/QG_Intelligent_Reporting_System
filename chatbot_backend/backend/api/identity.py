"""
Who is asking. Read from the ERP's own session cookie.

The chatbot runs as a separate service on :8010 but is only ever reached
through the ERP backend's /chatbot/* proxy, which forwards every header except
the hop-by-hop ones - so the browser's `access_token` cookie arrives here
intact. Both services load the same JWT_SECRET_KEY, so this can verify it
without a round trip.

Until this existed, NOTHING on the chatbot knew who was asking:

  * every conversation was anonymous, so there was no audit trail of who asked
    what of the company's data;
  * /chat/{thread_id}/history replayed ANY thread to ANYONE holding the id;
  * and a thread id left in a browser's localStorage survived logout, so the
    next person to sign in on that machine was handed the previous user's
    conversation.

The token is the ERP's: HS256, payload {"id": <user id>, "exp": ...}, issued by
app/auth/create_token.py and set as an httponly cookie named `access_token`.
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

COOKIE_NAME = "access_token"
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET_KEY")

log = logging.getLogger(__name__)

# A token that arrives and FAILS to verify is the single most expensive silent
# failure in this system, so it is reported - once, not per request, because a
# broken secret breaks every request and would otherwise bury the log.
#
# What it looks like when it happens: nothing. Answers keep working, because a
# question can be answered anonymously. But user_id is None everywhere, so
# conversations are never stored, none are ever restored, audit rows land with a
# null user, and terms taught by one person cannot be attributed. Every one of
# those reads as a separate bug, and none of them points at the cause.
#
# The cause is almost always that JWT_SECRET_KEY here does not match the ERP's.
# The ERP signs the cookie; this only verifies it. .env is gitignored, so the
# two drift the moment the app is deployed or copied to another machine.
_warned_bad_token = False
_warned_no_secret = False


def current_user_id(request) -> Optional[int]:
    """
    The signed-in user's id, or None when there is no valid session.

    Returns None rather than raising: the caller decides whether an anonymous
    request is acceptable. Signature and expiry are both verified - an expired
    token is treated exactly like no token, which is what makes the logout leak
    impossible to reproduce from a stale cookie.
    """
    global _warned_bad_token, _warned_no_secret

    if not SECRET_KEY:
        # No shared secret configured. Refusing to guess is the safe failure:
        # returning an id here would let anyone act as a user.
        if not _warned_no_secret:
            _warned_no_secret = True
            log.error(
                "JWT_SECRET_KEY is not set, so no user can ever be identified. "
                "Conversations will not be saved or restored and audit rows "
                "will have no user. Set it in chatbot_backend/.env to the SAME "
                "value as the ERP's JWT_SECRET_KEY."
            )
        return None

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    try:
        from jose import jwt

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as exc:
        # Bad signature, expired, malformed - all mean "not signed in". But a
        # token that ARRIVED and failed is worth saying out loud once: the
        # browser had a session, and this service could not read it.
        if not _warned_bad_token:
            _warned_bad_token = True
            log.error(
                "An access_token cookie was sent but could not be verified (%s). "
                "Every request will look anonymous: conversations will not be "
                "saved or restored. The usual cause is that JWT_SECRET_KEY in "
                "chatbot_backend/.env differs from the ERP's - the ERP signs "
                "the cookie, this service only verifies it, and .env is not in "
                "git so the two drift between machines.",
                type(exc).__name__,
            )
        return None

    user_id = payload.get("id")
    try:
        return int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        return None
