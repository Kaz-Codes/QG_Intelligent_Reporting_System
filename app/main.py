import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.database import Base, SessionLocal, engine

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
import app.notifications.models

from app.accounts.models import User, Permission
from app.accounts.permissions import ALL_PERMISSIONS

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

from app.dashboard.whole.routes import router as overview_dashboard_router
from app.dashboard.purchases.routes import router as purchases_dashboard_router
from app.dashboard.inventory.routes import router as inventory_dashboard_router
from app.reports.routes import router as reports_router
from app.notifications.routes import router as notifications_router
from app.chatbot_proxy import router as chatbot_proxy_router

# The auth package has no populated __init__, so its two route files are
# imported by hand to attach them to the auth router.
from app.auth.router import router as auth_router
import app.auth.login
import app.auth.logout

from app.logs.middleware import log_requests
from app.notifications.worker import background_loop, liveness as worker_liveness

logger = logging.getLogger(__name__)

load_dotenv()


#-----------------------------------------------------
# SETTING UP THE DATABASE
#
# When the server starts every model becomes a table (if it does not exist
# already), the four roles the whole system is built around are put in, and
# a first admin account is created from the credentials in the .env file so
# there is somebody to log in as.
#
# create_all only ever creates a MISSING table — it never alters a column on
# one that already exists, so it's kept here only to boot a brand-new empty
# database. Alembic (alembic/) is the source of truth for schema changes now
# — see "Database migrations" in CLAUDE.md.
#-----------------------------------------------------

#-----------------------------------------------------
# STARTUP MUST NOT DEPEND ON WINNING A RACE WITH POSTGRES
#
# This used to be a bare create_all(). It runs at IMPORT time, so a database
# that was not yet accepting connections raised straight out of the module and
# uvicorn exited — and on a server where the ERP service and PostgreSQL start
# together at boot, which of them is ready first is a coin toss. The ERP would
# come up after some reboots and not others, with nothing retrying it and
# nothing but a traceback to say why.
#
# So: a few attempts with a short backoff, and if the database is still not
# there, LOG IT AND CARRY ON.
#
# STARTING WITHOUT A DATABASE IS THE BETTER FAILURE. The alternative is a
# process that refuses to exist, which cannot serve a health check, cannot be
# inspected, and needs somebody to notice and restart it by hand. A process
# that is up and failing per request stays visible, and pool_pre_ping
# (app/database.py) means the very next request after Postgres appears gets a
# live connection rather than a dead pooled one — so it recovers on its own,
# without a restart.
#
# The two seeds below already worked this way. This only makes the first step
# consistent with them.
#-----------------------------------------------------

CREATE_TABLES_ATTEMPTS = 5
CREATE_TABLES_BACKOFF_SECONDS = 2


def create_tables():
    """Create any missing tables, retrying while the database wakes up.

    Returns True if the schema was reached, False if every attempt failed —
    the caller does not act on it, but it makes the outcome testable and
    keeps the function honest about what happened.
    """
    for attempt in range(1, CREATE_TABLES_ATTEMPTS + 1):
        try:
            Base.metadata.create_all(bind=engine)

            if attempt > 1:
                # Worth saying out loud: this is the boot-order race resolving
                # itself, and knowing it happened explains a slow start.
                logger.info(
                    "Database reachable on attempt %s; schema is ready", attempt
                )

            return True

        except Exception:
            last = attempt == CREATE_TABLES_ATTEMPTS

            if not last:
                # WARNING, not exception: a retry that is about to succeed is
                # not an error, and a full traceback per attempt would bury
                # the one that matters.
                logger.warning(
                    "Database not reachable on attempt %s of %s; retrying in "
                    "%ss", attempt, CREATE_TABLES_ATTEMPTS,
                    CREATE_TABLES_BACKOFF_SECONDS,
                )
                time.sleep(CREATE_TABLES_BACKOFF_SECONDS)
                continue

            # ERROR with the traceback, once, on the attempt that gave up.
            logger.exception(
                "Could not reach the database after %s attempts over %ss. "
                "The server is STARTING ANYWAY and will fail per request until "
                "the database is available; pool_pre_ping means it recovers "
                "without a restart once it is. If this persists, check that "
                "PostgreSQL is running and that DB_HOST/DB_PORT/DB_NAME/"
                "DB_USER/DB_PASSWORD in .env are correct.",
                CREATE_TABLES_ATTEMPTS,
                CREATE_TABLES_ATTEMPTS * CREATE_TABLES_BACKOFF_SECONDS,
            )

    return False


def seed_permissions():
    # Upsert the permission catalogue: every name in ALL_PERMISSIONS that is not
    # already a row is added. Idempotent, so it is safe on every start.
    db = SessionLocal()

    try:
        existing = {name for (name,) in db.execute(select(Permission.name)).all()}

        for name in ALL_PERMISSIONS:
            if name not in existing:
                db.add(Permission(name=name))

        db.commit()

    except Exception as e:
        logger.exception("Unhandled error in app.main.seed_permissions")
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

        # The default admin passes every check via is_admin — no permissions to
        # assign. Password is stored as-is, the same way create_user stores it
        # and login compares it.
        db.add(
            User(
                username=admin_username,
                password=admin_password,
                is_admin=True,
                is_active=True
            )
        )

        db.commit()

    except Exception as e:
        logger.exception("Unhandled error in app.main.seed_admin")
        db.rollback()

    finally:
        db.close()



#-----------------------------------------------------
# THE APP
#-----------------------------------------------------

#-----------------------------------------------------
# BACKGROUND WORKERS
#
# One task runs BOTH notification jobs: fan-out every 10s, and the
# threshold scanner every 15 minutes. Neither runs inside the request that
# caused it, so a consignment save never pays for routing to every recipient,
# and sharing one task keeps the two from holding pooled connections at the
# same moment — see app/notifications/worker.py for the full reasoning.
#
# The task is cancelled on shutdown and awaited, so uvicorn's reload does not
# leave an orphaned loop polling the database behind the new process.
#-----------------------------------------------------

# The running task, so the health endpoint can ask whether it is still alive.
# Module-level rather than on app.state because that is where the other
# process-wide handles in this file live, and there is exactly one of these.
_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    worker = asyncio.create_task(background_loop())
    _worker_task = worker

    try:
        yield

    finally:
        worker.cancel()

        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Supply Chain ERP", lifespan=lifespan)

# CORS. The token lives in a cookie, so the browser only sends it when the
# request carries credentials, and that in turn means the allowed origins
# have to be named exactly (a wildcard is refused by the browser once
# credentials are allowed) — allow_origins=["*"] with allow_credentials=True
# would let any origin ride the cookie into an authenticated request. Set
# ALLOWED_ORIGINS in .env to a comma-separated list of the front end's real
# addresses; an empty/unset var means no origin is allowed.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
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
app.include_router(overview_dashboard_router)
app.include_router(purchases_dashboard_router)
app.include_router(inventory_dashboard_router)
app.include_router(reports_router)
app.include_router(notifications_router)
app.include_router(chatbot_proxy_router)


#-----------------------------------------------------
# LIVENESS
#
# Reports the notification worker alongside the app, because the two can fail
# independently: the API answers perfectly well with a dead worker, and
# nothing else would ever say so - notifications just stop, quietly (see the
# note in app/notifications/worker.py).
#
# `running` is the task itself; `last_poll_at` is what actually proves it is
# working. A task can be alive and wedged, so a timestamp older than a couple
# of poll intervals means as much as running=false.
#
# UNAUTHENTICATED, like the root route it extends. It returns no business data
# - a timestamp, a count and two booleans - and a health check that needs a
# login cannot be polled by the thing most likely to need it.
#-----------------------------------------------------

def _worker_health() -> dict:
    state = worker_liveness()

    task = _worker_task
    running = task is not None and not task.done()

    failure = None
    if task is not None and task.done():
        # Only safe to ask once done(); on a live task this raises.
        try:
            exc = task.exception()
            failure = repr(exc) if exc else "stopped"
        except asyncio.CancelledError:
            failure = "cancelled"

    def iso(value):
        return value.isoformat() if value else None

    return {
        "running": running,
        "started_at": iso(state["started_at"]),
        "last_poll_at": iso(state["last_poll_at"]),
        "last_scan_at": iso(state["last_scan_at"]),
        "polls": state["polls"],
        # Only present when the task has ended, so its absence is not a claim
        # that nothing went wrong - `running` is.
        "stopped_because": failure,
    }


@app.get("/")
def root():
    return {
        "status_code": 200,
        "detail": "Supply Chain ERP API is running",
        "notification_worker": _worker_health(),
    }


@app.get("/health")
def health():
    """The same thing under the name a monitor would look for."""
    return {
        "status_code": 200,
        "detail": "Supply Chain ERP API is running",
        "notification_worker": _worker_health(),
    }


# Build the tables and seed the roles and the admin as the server module
# loads, so a fresh database is ready the moment the server starts.

create_tables()
seed_permissions()
seed_admin()

# Loading the source workbooks is NOT done here — it is a destructive full
# reload and must be run explicitly, not on every server start (which is what
# duplicated purchases_data):
#     python -m app.loading.scripts.load_all
