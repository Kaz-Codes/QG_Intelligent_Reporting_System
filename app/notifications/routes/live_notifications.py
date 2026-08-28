import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.auth.authorize_user import _load_active_user
from app.auth.verify_token import verify_token
from app.database import SessionLocal
from app.notifications.manager import manager
from app.notifications.routes.router import router

logger = logging.getLogger(__name__)

#-------------------------------------------
# THE LIVE NOTIFICATION FEED
#
# A user opens one of these when the panel mounts and, from then on, every
# notification fanned out to THEM is pushed down the socket the moment the
# delivery row is written. The history that came before is loaded once over
# the normal GET route — the same split as the activity log's live feed.
#
# AUTH IS THE SAME PATTERN AS /logs/ws: read the cookie by hand (a websocket
# handshake carries no Authorization header and cannot use the HTTP
# dependency), resolve it in a short-lived session, and close with 1008 before
# accepting the handshake if it does not resolve. A caller that fails auth
# never gets an accepted socket.
#
# WHAT DIFFERS FROM THE LOG FEED, AND IT IS THE WHOLE POINT: /logs/ws checks
# require_admin and then subscribes the socket to EVERYTHING. This one takes
# no id from the client at all — the socket is bound to the id in the caller's
# own token, so a user can only ever subscribe to their own feed. There is no
# path parameter to tamper with, and no admin variant that sees all of them:
# see manager.py on why a global watcher list would be a permission bypass.
#-------------------------------------------

def _authenticated_user_id(token):
    """The caller's user id from the cookie, or None if it does not resolve."""
    if not token:
        return None

    db = SessionLocal()

    try:
        payload = verify_token(token)
        # Loaded rather than trusted from the token: the same active-account
        # check every authorize() makes, so a disabled account cannot hold a
        # live socket open on a token issued before it was disabled.
        user = _load_active_user(payload, db)
        return user.id

    except Exception:
        return None

    finally:
        db.close()


@router.websocket("/ws")
async def live_notifications(websocket: WebSocket):
    token = websocket.cookies.get("access_token")
    user_id = _authenticated_user_id(token)

    if user_id is None:
        # Refused before the handshake is accepted.
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)

    try:
        # Nothing is expected from the client. This just waits, and notices
        # when the panel is closed.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

    except Exception:
        manager.disconnect(user_id, websocket)
