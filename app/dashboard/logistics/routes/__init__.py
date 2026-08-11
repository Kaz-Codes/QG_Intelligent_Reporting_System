from app.dashboard.logistics.routes.router import router

# Importing the route module runs its @router.get decorators so the three tab
# endpoints register on the shared router.
# Literal paths first: /logistics/references must register before any
# route that could capture 'references' as a path parameter.
from app.dashboard.logistics.routes import logistics_references
from app.dashboard.logistics.routes import logistics_dashboard
