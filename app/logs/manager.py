#-----------------------------------------------------
# WHO IS WATCHING WHOSE LIVE LOG
#
# Kept in memory, on purpose. This is only the list of
# currently open admin screens, not the logs themselves,
# which live in the database. If the server restarts the
# open screens just reconnect.
#
# watchers maps a watched user id to the admin sockets
# currently looking at that user. When an action is logged
# for a user, everyone watching that user is sent it.
#-----------------------------------------------------

from fastapi import WebSocket


class LogManager:
    def __init__(self):
        self.watchers : dict[int, list[WebSocket]] = {}

    async def connect(self, watched_user_id, websocket):
        await websocket.accept()
        self.watchers.setdefault(watched_user_id, []).append(websocket)

    def disconnect(self, watched_user_id, websocket):
        sockets = self.watchers.get(watched_user_id, [])

        if websocket in sockets:
            sockets.remove(websocket)

    async def broadcast(self, watched_user_id, message):
        # A copy of the list, because a send that fails removes
        # the socket from the same list we are looping over.
        for websocket in list(self.watchers.get(watched_user_id, [])):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(watched_user_id, websocket)


# One shared instance for the whole app, so the middleware
# that writes logs and the websocket route that shows them
# are talking about the same set of open screens.
manager = LogManager()
