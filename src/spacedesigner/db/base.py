"""Declarative base shared by every SQLAlchemy model."""

# DeclarativeBase is the SQLAlchemy 2 superclass for mapped tables.
from sqlalchemy.orm import DeclarativeBase


# Metadata container Alembic reads when it builds migrations.
class Base(DeclarativeBase):
    """Base class for PhotoSpace tables."""
