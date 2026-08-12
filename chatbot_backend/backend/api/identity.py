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

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

COOKIE_NAME = "access_token"
ALGORITHM = "HS256"
SECRET_KEY = os.getenv("JWT_SECRET_KEY")


def current_user_id(request) -> Optional[int]:
    """
    The signed-in user's id, or None when there is no valid session.

    Returns None rather than raising: the caller decides whether an anonymous
    request is acceptable. Signature and expiry are both verified - an expired
    token is treated exactly like no token, which is what makes the logout leak
    impossible to reproduce from a stale cookie.
    """
    if not SECRET_KEY:
        # No shared secret configured. Refusing to guess is the safe failure:
        # returning an id here would let anyone act as a user.
        return None

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    try:
        from jose import jwt

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        # Bad signature, expired, malformed - all mean "not signed in".
        return None

    user_id = payload.get("id")
    try:
        return int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        return None
