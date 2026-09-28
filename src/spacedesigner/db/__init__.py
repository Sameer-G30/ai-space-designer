"""Database package: models, metadata, and session helpers."""

# Declarative base shared by the tables.
from spacedesigner.db.base import Base

# Mapped table classes.
from spacedesigner.db.models import (
    CatalogItemRow,
    DesignRow,
    DesignVersionRow,
    ExplanationRow,
    RagChunkRow,
    RequirementRow,
    SceneRow,
)

# Connection helpers.
from spacedesigner.db.session import get_database_url, get_engine, get_session_factory

# Names re-exported from the database package.
__all__ = [
    "Base",
    "CatalogItemRow",
    "DesignRow",
    "DesignVersionRow",
    "ExplanationRow",
    "RagChunkRow",
    "RequirementRow",
    "SceneRow",
    "get_database_url",
    "get_engine",
    "get_session_factory",
]
