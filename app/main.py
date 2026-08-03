import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.loading.scripts.load_all import call_load

# Importing the model modules registers every table on Base.metadata, so
# create_all below knows about all of them. Nothing is created until this
# import has run.
import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.logs.models
import app.loading.schemas.stores_schemas
import app.reports.models

from app.accounts.models import Role, User

# Importing each routes package runs the route files, which is what hangs
# the endpoints off their router. Then the router objects are included below.
from app.accounts.routes import router as accounts_router
from app.masters.routes import router as masters_router
from app.imports.routes import router as imports_router
from app.logistics.routes import router as logistics_router
from app.trucking.routes import router as trucking_router
from app.logs.routes import router as logs_router
from app.dashboard.imports.routes import router as imports_dashboard_router
from app.dashboard.logistics.routes import router as logistics_dashboard_router
# from app.dashboard.whole.routes import router as overview_dashboard_router
from app.dashboard.purchases.routes import router as purchases_dashboard_router
from app.dashboard.inventory.routes import router as inventory_dashboard_router
from app.reports.routes import router as reports_router

# The auth package has no populated __init__, so its two route files are
# imported by hand to attach them to the auth router.
from app.auth.router import router as auth_router
import app.auth.login
import app.auth.logout

from app.logs.middleware import log_requests

load_dotenv()


#-----------------------------------------------------
# SETTING UP THE DATABASE
#
# When the server starts every model becomes a table (if it does not exist
# already), the four roles the whole system is built around are put in, and
# a first admin account is created from the credentials in the .env file so
# there is somebody to log in as.
#-----------------------------------------------------

ROLES = ["admin", "manager", "entry operator", "viewer"]


def create_tables():
    Base.metadata.create_all(bind=engine)


def seed_roles():
    db = SessionLocal()

    try:
        for name in ROLES:
            exists = db.execute(
                select(Role).where(Role.name == name)
            ).scalar_one_or_none()

            if not exists:
                db.add(Role(name=name))

        db.commit()

    except Exception as e:
        print(e)
        db.rollback()

    finally:
        db.close()


def seed_admin():
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_username or not admin_password:
        return

    db = SessionLocal()

    try:
        admin_exists = db.execute(
            select(User).where(User.username == admin_username)
        ).scalar_one_or_none()

        if admin_exists:
            return

        admin_role = db.execute(
            select(Role).where(Role.name == "admin")
        ).scalar_one_or_none()

        if admin_role is None:
            return

        # Password is stored as it is, the same way create_user stores it and
        # login compares it.
        db.add(
            User(
                username=admin_username,
                password=admin_password,
                role_id=admin_role.id,
                is_active=True
            )
        )

        db.commit()

    except Exception as e:
        print(e)
        db.rollback()

    finally:
        db.close()



#-----------------------------------------------------
# THE APP
#-----------------------------------------------------

app = FastAPI(title="Supply Chain ERP")

# CORS. The token lives in a cookie, so the browser only sends it when the
# request carries credentials, and that in turn means the allowed origins
# have to be named exactly (a wildcard is refused by the browser once
# credentials are allowed). Add the front end's real address here.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logs every data-changing request against the acting user and pushes it to
# any admin watching the live feed.
app.middleware("http")(log_requests)

# Every module's routes, each already carrying its own url prefix.
app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(masters_router)
app.include_router(imports_router)
app.include_router(logistics_router)
app.include_router(trucking_router)
app.include_router(logs_router)
app.include_router(imports_dashboard_router)
app.include_router(logistics_dashboard_router)
# app.include_router(overview_dashboard_router)
app.include_router(purchases_dashboard_router)
app.include_router(inventory_dashboard_router)
app.include_router(reports_router)


@app.get("/")
def root():
    return {
        "status_code": 200,
        "detail": "Supply Chain ERP API is running"
    }


# Build the tables and seed the roles and the admin as the server module
# loads, so a fresh database is ready the moment the server starts.

create_tables()
seed_roles()
seed_admin()

# Load stores data
call_load()
