from app.dashboard.inventory.routes.router import router

# Importing the route module runs its @router.get decorator so the endpoint
# is registered on the shared router.
from app.dashboard.inventory.routes import inventory_dashboard
