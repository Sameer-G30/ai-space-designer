"""Shared Pydantic settings for every PhotoSpace contract model."""

# ConfigDict holds model-wide validation settings.
from pydantic import BaseModel, ConfigDict


# Base for schema models so unknown keys are rejected everywhere.
class SchemaModel(BaseModel):
    # Forbid extra fields so the integration contract cannot grow silently.
    model_config = ConfigDict(extra="forbid")
