from app.dashboard.inventory.routes.router import router

# Importing the route module runs its @router.get decorator so the endpoint
# is registered on the shared router.
# Literal paths first: /inventory/references must register before any route
# that could capture 'references' as a path parameter.
from app.dashboard.inventory.routes import inventory_references
from app.dashboard.inventory.routes import inventory_dashboard
