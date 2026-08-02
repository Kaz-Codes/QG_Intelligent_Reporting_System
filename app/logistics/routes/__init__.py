#-----------------------------------------------------
# THE LOGISTICS ROUTES
#
# Each route file hangs itself off the shared router by
# importing it, so nothing is registered until its file has
# been imported. They are all listed here so main.py only
# has to include one router.
#-----------------------------------------------------

from app.logistics.routes.router import router

from app.logistics.routes import create_consignment
# Registered before get_consignment so GET /export is not captured by the
# GET /{consignment_id} route.
from app.logistics.routes import export_consignments
from app.logistics.routes import get_consignment
from app.logistics.routes import get_trucking_jobs
from app.logistics.routes import get_consignments_list
from app.logistics.routes import update_consignment
from app.logistics.routes import submit_consignment
from app.logistics.routes import reopen_consignment
from app.logistics.routes import delete_consignment
from app.logistics.routes import undo_delete
from app.logistics.routes import get_consignment_history_list
from app.logistics.routes import get_consignment_history
from app.logistics.routes import revert_update
