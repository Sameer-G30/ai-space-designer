"""Database engine and session helpers. Nothing connects at import time."""

# os reads DATABASE_URL from the environment.
import os

# Engine is the connection factory. Session is one unit of work.
from sqlalchemy import Engine, create_engine

# sessionmaker builds sessions bound to that engine.
from sqlalchemy.orm import Session, sessionmaker

# Engine created on the first call and reused after that.
_engine: Engine | None = None


# Read the connection string Phase 0 stores in .env.
def get_database_url() -> str:
    """Return DATABASE_URL or raise if it is missing."""
    # Look up the variable without requiring it at import time.
    database_url = os.environ.get("DATABASE_URL")
    # Fail with a setup hint when the variable was not exported.
    if not database_url:
        # Stop before SQLAlchemy tries to connect with an empty URL.
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")
    # Return the URL the caller can pass to SQLAlchemy.
    return database_url


# Build one engine for the process.
def get_engine() -> Engine:
    """Return a shared SQLAlchemy engine."""
    # The module-level engine is assigned inside this function.
    global _engine
    # Create the engine only on the first request.
    if _engine is None:
        # pool_pre_ping drops connections that died when Postgres restarted.
        _engine = create_engine(get_database_url(), pool_pre_ping=True)
    # Return the existing engine on later calls.
    return _engine


# Build a session factory bound to the shared engine.
def get_session_factory() -> sessionmaker[Session]:
    """Return a sessionmaker for the shared engine."""
    # Each call creates a factory; the engine underneath is shared.
    return sessionmaker(bind=get_engine(), class_=Session)
