"""Design-version record from blueprint section 25, plus design_id."""

# datetime is the type stored in the version timestamp column.
from datetime import datetime

# Any is the value type inside the unstructured diff object.
from typing import Any

# Field and field_validator express id, version, and timezone rules.
from pydantic import Field, field_validator

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel


# One append-only version of a design.
class DesignVersion(SchemaModel):
    # Design this version belongs to.
    design_id: str = Field(min_length=1)
    # Scene this version belongs to.
    scene_id: str = Field(min_length=1)
    # Version number within the design, starting at 1.
    version: int = Field(ge=1)
    # Previous version number, omitted for the first version.
    parent_version: int | None = None
    # Structured diff payload. Its keys are defined in a later phase.
    diff: dict[str, Any]
    # Score stored with this version.
    score: float
    # Time this version was recorded.
    timestamp: datetime

    # A parent version, when present, uses the same numbering as version.
    @field_validator("parent_version")
    @classmethod
    def parent_version_must_be_positive(cls, value: int | None) -> int | None:
        # The first version has no parent.
        if value is None:
            # Keep the field empty.
            return value
        # Version numbers start at 1.
        if value < 1:
            # Fail validation with a stable message.
            raise ValueError("parent_version must be at least 1")
        # Keep a parent pointer that is a real version number.
        return value

    # Require an offset so the timestamp maps cleanly to timestamptz.
    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        # A naive datetime has no known offset.
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            # Fail validation with a stable message.
            raise ValueError("timestamp must include a timezone")
        # Keep a timezone-aware timestamp.
        return value
