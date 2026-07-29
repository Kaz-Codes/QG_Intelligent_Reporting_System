#-----------------------------------------------------
# THE TRUCKING ROUTES
#
# Each route file hangs itself off the shared router by
# importing it, so nothing is registered until its file has
# been imported. They are all listed here so main.py only
# has to include one router.
#-----------------------------------------------------

from app.trucking.routes.router import router

from app.trucking.routes import create_consignment
from app.trucking.routes import get_consignment
from app.trucking.routes import get_consignments_list
from app.trucking.routes import update_consignment
from app.trucking.routes import delete_consignment
from app.trucking.routes import undo_delete
from app.trucking.routes import get_consignment_history_list
from app.trucking.routes import get_consignment_history
from app.trucking.routes import revert_update
