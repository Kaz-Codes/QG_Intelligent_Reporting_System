from app.dashboard.whole.routes.router import router

# Importing the route module runs its @router.get decorator so the endpoint
# is registered on the shared router.
# Literal paths first: /overview/references must be registered before
# anything that could capture it as a path parameter.
from app.dashboard.whole.routes import overview_references
from app.dashboard.whole.routes import overview_dashboard
