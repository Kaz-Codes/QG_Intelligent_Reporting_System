#-----------------------------------------------------
# EVERY IMPORTS ROUTE, IN THE ORDER OF THE WIZARD
#
# Each route lives in its own file and hangs itself off the
# shared router by importing it. Nothing registers a route
# until its file has been imported, so they are all listed
# here and main.py only has to include one router.
#
# Order matters in one place only: list_consignments has to
# be imported before get_consignment, so that a plain
# GET /consignments/ is not swallowed by /consignments/{id}.
#-----------------------------------------------------

from app.imports.routes.router import router

#--- reading ---
from app.imports.routes import list_consignments
from app.imports.routes import get_consignment
from app.imports.routes import get_history
from app.imports.routes import get_changes

#--- step 1, consignment ---
from app.imports.routes import create_consignment
from app.imports.routes import update_consignment
from app.imports.routes import add_item
from app.imports.routes import update_item

#--- step 2, finance ---
from app.imports.routes import update_finance

#--- step 3, shipping ---
from app.imports.routes import update_shipping

#--- step 4, payments ---
from app.imports.routes import add_payment
from app.imports.routes import update_payment

#--- step 5, status and remarks ---
from app.imports.routes import change_status

#--- step 6, clearance ---
from app.imports.routes import update_clearance

#--- step 7, landed cost ---
from app.imports.routes import update_landed_cost

#--- undoing things ---
from app.imports.routes import delete_consignment
from app.imports.routes import restore_consignment
from app.imports.routes import revert_change
