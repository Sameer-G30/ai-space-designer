"""Turn a perception result into a scaled scene graph with a confidence on every dimension."""

# Annotations on Python 3.11.
from __future__ import annotations

# Numerical arrays for clamping object centres.
import numpy as np

# Room fit and frame helpers.
# Shared opening width floor.
from spacedesigner.perception.items import MIN_OPENING_M

# Locked schema types. Nothing here changes the contract.
from spacedesigner.schemas import Confidence, Opening, RoomDimensions, SceneGraph, SceneObject

# Dimension names a user may anchor.
AXES = ("length", "width", "height")

# Smallest object edge kept, in metres, so the schema's positive rule always holds.
MIN_EDGE_M = 0.1

# A scale factor outside this range means the typed length and the photo disagree badly.
SCALE_RANGE = (0.2, 5.0)


# Raised when the typed length cannot be used.
class InvalidMeasurement(ValueError):
    """The known length is not usable."""


# Pick the dimension the user measured, or none.
def apply_scale(
    room: dict, known_length_m: float | None, known_axis: str
) -> tuple[float, dict[str, Confidence]]:
    """Return the scale factor and a confidence per dimension."""
    # Start with depth-only geometry: every dimension is low.
    confidence = {axis: Confidence.low for axis in AXES}
    # No typed length: metric depth is used as is.
    if known_length_m is None:
        # Scale of one keeps the metric depth numbers.
        return 1.0, confidence
    # Axis must be one of the three.
    if known_axis not in AXES:
        # Reject a bad axis name.
        raise InvalidMeasurement(f"known_axis must be one of {', '.join(AXES)}")
    # A length must be a positive number.
    if not known_length_m > 0:
        # Reject zero and negatives.
        raise InvalidMeasurement("known_length_m must be greater than 0")
    # Estimated value of the anchored dimension.
    estimate = float(room[known_axis])
    # A zero estimate cannot be scaled.
    if estimate <= 0:
        # Reject it.
        raise InvalidMeasurement("the photo gave no usable size for that dimension")
    # Ratio between the user's number and the depth estimate.
    scale = known_length_m / estimate
    # Reject absurd disagreement.
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        # The typed length and the photo cannot both be right.
        raise InvalidMeasurement(
            f"the typed {known_axis} is {scale:.1f} times the photo estimate; check the number"
        )
    # Dimensions measured from visible planes inherit the user's anchor.
    for axis in AXES:
        # A height from the fallback (no ceiling) stays low.
        if axis == "height" and not room["ceiling_found"] and known_axis != "height":
            # Keep it low.
            continue
        # Anchored and scaled dimension.
        confidence[axis] = Confidence.high
    # Return the factor and the labels.
    return scale, confidence


# Lowest confidence among the dimensions, as the scene-level label.
def lowest(confidence: dict[str, Confidence]) -> Confidence:
    """Return the weakest confidence, so the optimizer margin applies when any dimension is low."""
    # Order from weakest to strongest.
    for level in (Confidence.low, Confidence.medium, Confidence.high):
        # First level present wins.
        if level in confidence.values():
            # Return it.
            return level
    # Unreachable for a non-empty mapping.
    return Confidence.low


# Build the scene graph and the per-dimension confidence for the response.
def build_scene(
    result: dict,
    scene_id: str,
    version: int,
    known_length_m: float | None = None,
    known_axis: str = "length",
) -> tuple[SceneGraph, dict[str, Confidence], float]:
    """Return (scene, per-dimension confidence, scale factor)."""
    # Room numbers from the worker, unscaled.
    room = result["room"]
    # Scale and confidences.
    scale, confidence = apply_scale(room, known_length_m, known_axis)
    # Scaled room size.
    length, width, height = (room[a] * scale for a in AXES)
    # Scene-level confidence: the weakest dimension.
    level = lowest(confidence)
    # Objects become scene objects centred in the room frame.
    objects: list[SceneObject] = []
    # Number each object per class so ids stay unique and readable.
    counts: dict[str, int] = {}
    # Walk the floor objects.
    for item in result["objects"]:
        # Footprint corners, scaled.
        x0, x1, y0, y1 = (v * scale for v in item["footprint"])
        # Edge lengths, floored at the minimum.
        size_x, size_y = max(x1 - x0, MIN_EDGE_M), max(y1 - y0, MIN_EDGE_M)
        # Centre clamped so the box sits inside the room.
        cx = float(np.clip((x0 + x1) / 2, size_x / 2, max(size_x / 2, length - size_x / 2)))
        # Second axis centre.
        cy = float(np.clip((y0 + y1) / 2, size_y / 2, max(size_y / 2, width - size_y / 2)))
        # Next index for this class.
        counts[item["type"]] = counts.get(item["type"], 0) + 1
        # Add the object. Seen surfaces only, so it is low confidence and not held in place.
        objects.append(
            SceneObject(
                id=f"{item['type']}_{counts[item['type']]}",
                type=item["type"],
                position=[cx, cy],
                rotation=0.0,
                dimensions=[size_x, size_y, max(item["height"] * scale, MIN_EDGE_M)],
                movable=True,
                must_keep=False,
                confidence=Confidence.low,
            )
        )
    # Openings are scaled along the wall.
    openings = [
        Opening(
            type=o["type"],
            wall=o["wall"],
            position=o["position"] * scale,
            width=max(o["width"] * scale, MIN_OPENING_M),
        )
        for o in result["openings"]
    ]
    # Assemble the locked scene graph.
    scene = SceneGraph(
        scene_id=scene_id,
        version=version,
        room_type=result["room_type"],
        dimensions=RoomDimensions(length=length, width=width, height=height, confidence=level),
        openings=openings,
        objects=objects,
    )
    # Return everything the route needs.
    return scene, confidence, scale
