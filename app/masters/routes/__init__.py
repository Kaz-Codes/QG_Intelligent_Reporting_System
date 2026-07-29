#-----------------------------------------------------
# EVERY MASTERS ROUTE
#
# One set of routes serves all six master lists, keyed by
# the {master} word in the url. Each file hangs itself off
# the shared router by importing it, so main.py only has to
# include one router.
#
# The review queue is imported before the single row read,
# so GET /masters/review-queue is matched before it can be
# read as GET /masters/{master}/{id}.
#-----------------------------------------------------

from app.masters.routes.router import router

#--- reading ---
# item_search and review_queue are imported before list_masters so their
# literal paths win over the generic /masters/{master} list route.
from app.masters.routes import review_queue
from app.masters.routes import item_search
from app.masters.routes import list_masters
from app.masters.routes import get_master

#--- writing ---
from app.masters.routes import create_master
from app.masters.routes import inline_create
from app.masters.routes import update_master
from app.masters.routes import verify_master
from app.masters.routes import set_active
