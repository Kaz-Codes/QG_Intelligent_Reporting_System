from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import json

from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = (
    f"postgresql+psycopg2://"
    f"{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
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