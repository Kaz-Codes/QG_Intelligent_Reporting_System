#-----------------------------------------------------
# THE NOTIFICATION ROUTES
#
# Each route file hangs itself off the shared router by importing it, and is
# imported here so one include_router wires the whole module — the same shape
# every other module's routes package uses.
#
# EMPTY FOR NOW, deliberately. The schema and the catalogue land first; the
# panel, the unread count and the live feed come with the UI task. The router
# exists so those files have something to attach to, and so the module is
# mounted in one place rather than being retro-fitted later.
#-----------------------------------------------------

from app.notifications.routes.router import router
