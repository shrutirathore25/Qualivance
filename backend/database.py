"""Database connection (PostgreSQL via SQLAlchemy).
Reads DATABASE_URL from backend/.env. Tables are created automatically."""
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
log = logging.getLogger("db")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = None
if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_tables_ready = False


class DatabaseUnavailable(Exception):
    """Raised when no database is configured or it cannot be reached."""


def ensure_tables():
    """Create tables if they do not exist yet. Safe to call many times."""
    global _tables_ready
    if _tables_ready:
        return
    if engine is None:
        raise DatabaseUnavailable("DATABASE_URL is not set in backend/.env.")
    import models  # noqa: F401  (registers the table with Base)
    Base.metadata.create_all(engine)
    _tables_ready = True
    log.info("database tables ready")


def get_db():
    """FastAPI dependency: one session per request."""
    ensure_tables()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
