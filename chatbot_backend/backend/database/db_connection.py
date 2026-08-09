"""
Database connection for the Supply Chain app.

Uses SQLAlchemy (pandas' preferred connectable) and reads credentials from a
.env file so nothing sensitive is hardcoded in the source. The engine is
created once and reused.

Required .env file (in the project root, NOT committed to git):

    DB_HOST=localhost
    DB_NAME=supply_chain_db
    DB_USER=postgres
    DB_PASSWORD=0000
    DB_PORT=5432
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()  # read the .env file


@lru_cache(maxsize=1)
def get_engine():
    """Create the SQLAlchemy engine once and reuse it (cached)."""
    host = os.getenv("DB_HOST", "localhost")
    name = os.getenv("DB_NAME", "supply_chain_db")
    user = os.getenv("DB_USER", "postgres")
    pwd  = os.getenv("DB_PASSWORD", "")
    port = os.getenv("DB_PORT", "5432")

    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
    # pool_pre_ping avoids stale-connection errors after the DB idles
    return create_engine(url, pool_pre_ping=True)
