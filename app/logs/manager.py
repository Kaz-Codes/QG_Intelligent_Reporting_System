#-----------------------------------------------------
# WHO IS WATCHING WHOSE LIVE LOG
#
# Kept in memory, on purpose. This is only the list of
# currently open admin screens, not the logs themselves,
# which live in the database. If the server restarts the
# open screens just reconnect.
#
# There are two kinds of watcher:
#
#   * per user  — watchers maps a watched user id to the admin
#     sockets looking at that one user. Used by the per-account
#     log panel.
#   * global    — everyone watching ALL activity, whoever caused
#     it. Used by the User Management page's live feed.
#
# Every logged action is sent to both: the sockets watching that
# particular user, and every global socket.
#-----------------------------------------------------

from fastapi import WebSocket


class LogManager:
    def __init__(self):
        self.watchers : dict[int, list[WebSocket]] = {}
        self.global_watchers : list[WebSocket] = []

    #--------------------------------
    # PER USER
    #--------------------------------

    async def connect(self, watched_user_id, websocket):
        await websocket.accept()
        self.watchers.setdefault(watched_user_id, []).append(websocket)

    def disconnect(self, watched_user_id, websocket):
        sockets = self.watchers.get(watched_user_id, [])

        if websocket in sockets:
            sockets.remove(websocket)

    #--------------------------------
    # EVERYTHING (ADMIN OVERVIEW)
    #--------------------------------

    async def connect_global(self, websocket):
        await websocket.accept()
        self.global_watchers.append(websocket)

    def disconnect_global(self, websocket):
        if websocket in self.global_watchers:
            self.global_watchers.remove(websocket)

    #--------------------------------
    # SEND ONE LOG OUT
    #--------------------------------

    async def broadcast(self, watched_user_id, message):
        # A copy of each list, because a send that fails removes
        # the socket from the same list we are looping over.
        for websocket in list(self.watchers.get(watched_user_id, [])):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(watched_user_id, websocket)

        for websocket in list(self.global_watchers):
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect_global(websocket)


# One shared instance for the whole app, so the middleware
# that writes logs and the websocket route that shows them
# are talking about the same set of open screens.
manager = LogManager()
