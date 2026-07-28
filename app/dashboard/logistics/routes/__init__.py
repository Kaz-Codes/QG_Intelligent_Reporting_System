#-----------------------------------------------------
# THE LOGISTICS DASHBOARD ROUTE
#
# The route file hangs itself off the router by importing
# it, so main.py only has to include one router.
#-----------------------------------------------------

from app.dashboard.logistics.routes.router import router

from app.dashboard.logistics.routes import logistics_dashboard
