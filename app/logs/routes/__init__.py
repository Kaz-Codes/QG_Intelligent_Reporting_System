#-----------------------------------------------------
# THE LOG ROUTES
#
# A history list for the admin's log screen, and the live
# websocket feed that keeps it updating. Each file hangs
# itself off the shared router by importing it.
#-----------------------------------------------------

from app.logs.routes.router import router

from app.logs.routes import list_logs
from app.logs.routes import live_logs
