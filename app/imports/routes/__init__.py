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
# Registered before get_consignment so GET /export and GET /filter-options are
# not captured by the GET /{consignment_id} route (which would 422 on the int).
from app.imports.routes import export_consignments
from app.imports.routes import filter_options
from app.imports.routes import get_consignment
from app.imports.routes import get_trucking_jobs
from app.imports.routes import get_consignments_list
from app.imports.routes import update_consignment
# POST /{consignment_id}/batches - a literal segment under a param path, so it
# cannot be shadowed by anything above; listed beside the other writes.
from app.imports.routes import create_batch
# GET on the same path. It shares the segment with the POST above and differs by
# method, so registration order does not matter between the two - but it must
# still come after `get_consignment`, because `/{consignment_id}` is registered
# there and FastAPI matches in registration order.
from app.imports.routes import get_batches
from app.imports.routes import submit_consignment
from app.imports.routes import reopen_consignment
from app.imports.routes import send_consignment
from app.imports.routes import delete_consignment
from app.imports.routes import undo_delete
from app.imports.routes import get_consignment_history_list
from app.imports.routes import get_consignment_history
from app.imports.routes import revert_update
