from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import json

from dotenv import load_dotenv
import os

load_dotenv()


def _required(name):
    """A connection setting that must be given, and says so by name if it is not.

    WHY THIS IS NOT `os.getenv(name)` INLINE. It used to be, and a missing
    variable produced the literal string "None" inside the URL, which SQLAlchemy
    then failed to parse as a port:

        ValueError: invalid literal for int() with base 10: 'None'
                    ...sqlalchemy/engine/url.py:917

    That error names neither the variable nor the file, and it is raised at
    IMPORT time — so on a fresh checkout with no `.env` the pytest suite cannot
    even be COLLECTED, and the message points into SQLAlchemy rather than at the
    thing that is actually missing. CLAUDE.md says the suite "needs no
    database", which is true of connectivity and was never true of `.env`.

    DB_NAME, DB_USER and DB_HOST are deliberately NOT defaulted. A silently
    defaulted database NAME is a worse bug than the one this fixes: it would
    connect somewhere, and the somewhere would be wrong.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. The application reads its database settings "
            f"from a .env file in the project root (see .env.example); a fresh "
            f"checkout has none, because .env is not tracked."
        )
    return value


DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{_required('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD', '')}@"
    f"{_required('DB_HOST')}:"
    # The one with a sane default: 5432 is Postgres's port everywhere, and
    # getting it wrong fails loudly at connect time rather than quietly.
    f"{os.getenv('DB_PORT') or '5432'}/"
    f"{_required('DB_NAME')}"
)

# pool_pre_ping guards against connections the DB or a firewall dropped while
# idle overnight — without it the first request each morning gets a dead
# connection back from the pool and fails as a generic 500.
engine = create_engine(
    DATABASE_URL,
    json_serializer=lambda v: json.dumps(v, default=str),
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass