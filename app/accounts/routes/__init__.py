#-----------------------------------------------------
# THE ACCOUNTS ROUTES
#
# Each route file hangs itself off the shared router by
# importing it, so nothing is registered until its file has
# been imported. They are all listed here so main.py only
# has to include one router.
#-----------------------------------------------------

from app.accounts.routes.router import router

from app.accounts.routes import get_users
from app.accounts.routes import create_user
from app.accounts.routes import edit_user
from app.accounts.routes import change_status
