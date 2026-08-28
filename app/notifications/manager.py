#-----------------------------------------------------
# WHO HAS A NOTIFICATION PANEL OPEN
#
# The same shape as app/logs/manager.py — in-memory, one list of sockets per
# key, a copy taken before every broadcast because a failed send removes the
# socket from the list being looped over. Kept in memory on purpose: this is
# only the set of currently open panels, not the notifications themselves,
# which live in the database. A restart just means the panels reconnect.
#
# ONE DIFFERENCE FROM LogManager, AND IT IS A SECURITY ONE: there is NO
# global watcher list here.
#
# The log feed has one because it is admin-only — an admin is allowed to see
# everything, so a socket that receives every event is exactly right. The
# notification panel is the opposite: a delivery row IS the permission
# boundary, decided per user by routing.user_receives, and the whole point is
# that two users watching at the same time see different things. A global
# feed would push every event to every open socket and hand somebody imports
# data — supplier names, values, GD numbers, all rendered into the body —
# without CAN_VIEW_IMPORTS. Do not add one.
#
# So the key here is the RECIPIENT's user id, not a watched user id: sockets
# are indexed by who is looking, and a message is pushed only to the users the
# fan-out actually created a delivery for.
#-----------------------------------------------------

from fastapi import WebSocket


class NotificationManager:
    def __init__(self):
        # recipient user id -> their open panels (a user may have several
        # tabs, or a phone and a desktop, so it is a list and not one socket).
        self.watchers: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id, websocket):
        await websocket.accept()
        self.watchers.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id, websocket):
        sockets = self.watchers.get(user_id, [])

        if websocket in sockets:
            sockets.remove(websocket)

        # Drop the empty list too. Without this the dict grows one permanent
        # key per user who has ever connected, for the life of the process.
        if not sockets:
            self.watchers.pop(user_id, None)

    #--------------------------------
    # PUSH ONE EVENT TO ITS RECIPIENTS
    #
    # Takes the user ids the fan-out just wrote deliveries for, so the socket
    # push and the database rows always agree about who was told. Nobody else
    # is reachable: a user with no delivery row has no socket entry consulted.
    #--------------------------------

    async def broadcast(self, user_ids, message):
        for user_id in user_ids:
            # A copy of each list, because a send that fails removes the
            # socket from the same list we are looping over.
            for websocket in list(self.watchers.get(user_id, [])):
                try:
                    await websocket.send_json(message)
                except Exception:
                    self.disconnect(user_id, websocket)


# One shared instance for the whole app, so the worker that fans out
# deliveries and the websocket route that shows them are talking about the
# same set of open panels.
manager = NotificationManager()
