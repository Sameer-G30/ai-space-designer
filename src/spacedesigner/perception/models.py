"""Response models for the photo route."""

# Annotations on Python 3.11.
from __future__ import annotations

# Locked scene graph and confidence labels.
from spacedesigner.schemas import Confidence, SceneGraph

# Base that rejects unknown keys.
from spacedesigner.schemas.base import SchemaModel


# One room type guess.
class RoomGuess(SchemaModel):
    """A room type and its classifier probability."""

    # One of the 15 locked room types.
    room_type: str
    # Softmax probability.
    probability: float


# Confidence for each dimension, kept beside the locked scene (its schema has one label).
class DimensionConfidence(SchemaModel):
    """Per-dimension confidence."""

    # Confidence of the room length.
    length: Confidence
    # Confidence of the room width.
    width: Confidence
    # Confidence of the room height.
    height: Confidence


# Everything POST /scenes/photo returns.
class PhotoSceneResponse(SchemaModel):
    """The stored scene plus how it was estimated."""

    # Scene graph saved with the existing versioning.
    scene: SceneGraph
    # Confidence on every dimension.
    dimension_confidence: DimensionConfidence
    # "user_length" when the user typed a length, else "metric_depth".
    scale_source: str
    # Factor applied to the metric depth estimate (1.0 without a typed length).
    scale_factor: float
    # Three best room types.
    room_guesses: list[RoomGuess]
    # Detected class names with scores, for display.
    detections: list[str]
    # Faces blurred before any model ran.
    faces_blurred: int
    # Plain-language notes on what was assumed.
    warnings: list[str]
