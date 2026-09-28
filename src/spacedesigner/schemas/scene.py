"""Scene-graph models taken from blueprint section 11."""

# Enum gives confidence a closed set of string labels.
from enum import Enum

# Field and field_validator express the numeric and list rules.
from pydantic import Field, field_validator

# SchemaModel rejects keys that are not part of this contract.
from spacedesigner.schemas.base import SchemaModel


# Confidence labels used on room dimensions and on each object.
class Confidence(str, Enum):
    # Depth-only geometry, before any user measurement.
    low = "low"
    # Estimate that is neither a tape measurement nor depth-only.
    medium = "medium"
    # Geometry anchored by a length the user supplied.
    high = "high"


# Room size in metres plus one confidence value for that size.
class RoomDimensions(SchemaModel):
    # Length of the room in metres.
    length: float = Field(gt=0)
    # Width of the room in metres.
    width: float = Field(gt=0)
    # Floor-to-ceiling height in metres.
    height: float = Field(gt=0)
    # How sure the system is about length, width, and height together.
    confidence: Confidence


# A door or window on one wall.
class Opening(SchemaModel):
    # Kind of opening, such as "window" or "door".
    type: str = Field(min_length=1)
    # Wall that holds the opening, such as "north".
    wall: str = Field(min_length=1)
    # Distance in metres from the start of the wall to the opening.
    position: float
    # Width of the opening in metres.
    width: float = Field(gt=0)


# One object recorded on the scene graph.
class SceneObject(SchemaModel):
    # Stable id referenced by must-keep requirements.
    id: str = Field(min_length=1)
    # Object category, such as "desk".
    type: str = Field(min_length=1)
    # Floor coordinates [x, y] in metres.
    position: list[float] = Field(min_length=2, max_length=2)
    # Rotation in degrees around the vertical axis.
    rotation: float
    # Size [length, width, height] in metres.
    dimensions: list[float] = Field(min_length=3, max_length=3)
    # True when the optimizer may move this object.
    movable: bool
    # True when the user requires this object to remain.
    must_keep: bool
    # Confidence for this object's own geometry.
    confidence: Confidence

    # Reject a size that is zero or negative on any axis.
    @field_validator("dimensions")
    @classmethod
    def dimensions_must_be_positive(cls, value: list[float]) -> list[float]:
        # Inspect each edge of the object's box.
        for edge in value:
            # A non-positive edge is not a physical size.
            if edge <= 0:
                # Fail validation with a stable message.
                raise ValueError("object dimensions must be positive")
        # Return the list unchanged when every edge is positive.
        return value


# Typed scene graph stored for one room.
class SceneGraph(SchemaModel):
    # Room identifier, such as "room_0091".
    scene_id: str = Field(min_length=1)
    # Version number of this scene graph, starting at 1.
    version: int = Field(ge=1)
    # Room category, such as "gaming_room".
    room_type: str = Field(min_length=1)
    # Overall room dimensions and their confidence.
    dimensions: RoomDimensions
    # Doors and windows that placement must respect.
    openings: list[Opening]
    # Objects currently recorded in the room.
    objects: list[SceneObject]

    # Keep object ids unique so a must-keep id points at one object.
    @field_validator("objects")
    @classmethod
    def object_ids_must_be_unique(cls, value: list[SceneObject]) -> list[SceneObject]:
        # Ids already seen in this scene.
        seen: set[str] = set()
        # Walk the objects in list order.
        for obj in value:
            # A duplicate id would make must-keep ambiguous.
            if obj.id in seen:
                # Fail validation with a stable message.
                raise ValueError("object ids must be unique")
            # Record this id before checking the next object.
            seen.add(obj.id)
        # Return the list unchanged when every id is unique.
        return value
