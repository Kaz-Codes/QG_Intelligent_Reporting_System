import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _required(name):
    """A connection setting that must be given, and says so by name if it is not.

    WITHOUT THIS, a missing variable passes `None` straight to psycopg2.connect,
    which fails from inside the C driver with something like
    `OperationalError: connection to server ... failed: FATAL: role "None" does
    not exist` — naming neither the missing .env variable nor this file. This
    module also runs at IMPORT time (the connection below is opened as a module-
    level side effect), so that error is the first thing a fresh checkout with
    no `.env` sees, with no indication of what to fix.

    Mirrors app/database.py's `_required()` — the identical pattern was fixed
    there and flagged here rather than touched, since this file was someone
    else's that day; DB_NAME, DB_USER and DB_HOST are deliberately NOT
    defaulted there for the same reason they are not defaulted here: a
    silently defaulted database NAME would connect somewhere, and the
    somewhere would be wrong.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. The loading scripts read their database "
            f"settings from a .env file in the project root (see .env.example); "
            f"a fresh checkout has none, because .env is not tracked."
        )
    return value


connection = psycopg2.connect(
    host=_required("DB_HOST"),
    port=os.getenv("DB_PORT") or "5432",
    dbname=_required("DB_NAME"),
    user=_required("DB_USER"),
    password=os.getenv("DB_PASSWORD", ""),
)

print("Connected successfully!")

cursor = connection.cursor()