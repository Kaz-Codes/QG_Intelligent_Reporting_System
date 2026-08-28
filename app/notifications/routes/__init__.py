#-----------------------------------------------------
# THE NOTIFICATION ROUTES
#
# Each route file hangs itself off the shared router by importing it, and is
# imported here so one include_router wires the whole module — the same shape
# every other module's routes package uses.
#
# ORDERING. The literal paths are imported before the parameterised one, the
# same rule the other modules follow: FastAPI matches in registration order,
# so /unread-count and /read-all must be registered before /{delivery_id}/read
# can shadow them. Nothing currently collides — the parameterised route is two
# segments and both literals are one — but the ordering costs nothing and
# stops the next route added here from becoming a 422 on an int parameter.
#
# ALL OF THESE AUTHENTICATE AND NONE OF THEM AUTHORIZE. That is deliberate and
# is explained in app/notifications/helpers.py — the permission gate is applied
# when a delivery row is CREATED, not when it is read.
#-----------------------------------------------------

from app.notifications.routes.router import router

from app.notifications.routes import unread_count
from app.notifications.routes import mark_all_read
from app.notifications.routes import list_notifications
from app.notifications.routes import mark_read
from app.notifications.routes import live_notifications
