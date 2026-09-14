"""
Database connection setup. One place that owns the engine/session - everything
else (models.py, crud.py, main.py) imports SessionLocal from here.

DATABASE_URL is read from a .env file (via python-dotenv) or a real environment
variable. If neither is set, it falls back to a dev default - but that default
is almost certainly WRONG for your machine (it assumes port 5432 and a specific
password), so you should always have a real .env file with your actual values.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()  # reads .env in the project root and puts its values into os.environ

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://pondapp:pondapp_dev@localhost:5432/ponddb",  # fallback only - set .env instead
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency - yields a session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
