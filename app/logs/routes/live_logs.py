from app.auth.verify_token import verify_token
from app.database import SessionLocal
from app.auth.authorize_user import require_admin
from app.logs.manager import manager
from app.logs.routes.router import router
from fastapi import WebSocket, WebSocketDisconnect

#-------------------------------------------
# THE LIVE LOG FEED (ADMIN ONLY)
#
# An admin opens one of these against a user
# id and, from then on, every action that user
# takes is pushed down the socket the moment it
# is logged. This is the live part of the log
# screen. The history that came before is
# loaded once over the normal GET route.
#
# The socket authenticates from the same cookie
# as everything else. Only an admin gets in,
# and anyone else is closed straight away.
#-------------------------------------------

def _is_admin(token):
    if not token:
        return False

    db = SessionLocal()

    try:
        payload = verify_token(token)
        # require_admin raises unless the caller is an active admin
        require_admin(payload, db)
        return True

    except Exception:
        return False

    finally:
        db.close()


@router.websocket("/ws/{user_id}")
async def live_logs(websocket: WebSocket, user_id: int):
    token = websocket.cookies.get("access_token")

    if not _is_admin(token):
        # Refused before the handshake is accepted, so a
        # non-admin simply cannot open the socket.
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)

    try:
        # Nothing is expected from the client. This just waits,
        # and notices when the admin closes the screen.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)

    except Exception:
        manager.disconnect(user_id, websocket)
