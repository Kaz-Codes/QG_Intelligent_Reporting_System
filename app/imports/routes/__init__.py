#-----------------------------------------------------
# THE IMPORTS (CONSIGNMENTS) ROUTES
#
# Each route file hangs itself off the shared router by
# importing it, so nothing is registered until its file has
# been imported. They are all listed here so main.py only
# has to include one router.
#-----------------------------------------------------

from app.imports.routes.router import router

from app.imports.routes import create_consignment
from app.imports.routes import get_consignment
from app.imports.routes import get_consignments_list
from app.imports.routes import update_consignment
from app.imports.routes import delete_consignment
from app.imports.routes import undo_delete
from app.imports.routes import get_consignment_history_list
from app.imports.routes import get_consignment_history
from app.imports.routes import revert_update
