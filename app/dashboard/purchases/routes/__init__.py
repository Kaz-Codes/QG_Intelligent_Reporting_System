from app.dashboard.purchases.routes.router import router

# Importing the route module runs its @router.get decorator so the endpoint
# is registered on the shared router.
from app.dashboard.purchases.routes import purchases_dashboard
