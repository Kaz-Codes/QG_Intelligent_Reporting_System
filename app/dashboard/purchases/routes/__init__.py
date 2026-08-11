from app.dashboard.purchases.routes.router import router

# Importing the route module runs its @router.get decorator so the endpoint
# is registered on the shared router.
# Literal paths first: /purchases/references must register before any route
# that could capture 'references' as a path parameter.
from app.dashboard.purchases.routes import purchases_references
from app.dashboard.purchases.routes import purchases_dashboard
