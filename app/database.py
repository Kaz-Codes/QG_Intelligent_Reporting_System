from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import json

DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/imports_db"

engine = create_engine(DATABASE_URL, json_serializer=lambda v: json.dumps(v, default=str))

SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass