#-----------------------------------------------------
# THE IMPORTS DASHBOARD ROUTE
#
# The route file hangs itself off the router by importing
# it, so main.py only has to include one router.
#-----------------------------------------------------

from app.dashboard.imports.routes.router import router

# Literal paths first: /imports/references must register before any route
# that could capture 'references' as a path parameter.
from app.dashboard.imports.routes import imports_references
from app.dashboard.imports.routes import imports_dashboard
