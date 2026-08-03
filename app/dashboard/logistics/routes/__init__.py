from app.dashboard.logistics.routes.router import router

# Importing the route module runs its @router.get decorators so the three tab
# endpoints register on the shared router.
from app.dashboard.logistics.routes import logistics_dashboard
