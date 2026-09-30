"""Diff detector boxes against the furniture projected from the scene graph."""

# Annotations on Python 3.11.
from __future__ import annotations

# Frozen records for one detection and one match result.
from dataclasses import dataclass


# One box the detector returned, in image pixels.
@dataclass
class Detection:
    """A furniture box from the saved detector, or from a test double."""

    # Taxonomy class.
    category: str
    # Detector score in [0, 1].
    score: float
    # Pixel box [x1, y1, x2, y2].
    xyxy: tuple[float, float, float, float]


# One object the rasterizer could see.
@dataclass
class ExpectedBox:
    """A scene-graph object projected into the same image."""

    # Scene-graph object id.
    object_id: str
    # Taxonomy class.
    category: str
    # Pixel box of the projected footprint.
    xyxy: tuple[float, float, float, float]


# Result of one comparison. The design is not changed by this result.
@dataclass
class ConsistencyResult:
    """Whether the detections match the projected scene graph."""

    # True only when every expected box is matched and no detection is left over.
    matched: bool
    # Expected boxes that found a same-class detection.
    matched_count: int
    # Expected boxes that were passed in.
    expected_count: int
    # Detections that matched no expected box.
    extra_count: int
    # Short sentence for the API note.
    note: str


# Intersection over union of two pixel boxes.
def _iou(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    """Return the IoU, or 0 when the boxes do not overlap."""
    # Overlap on x.
    x1 = max(left[0], right[0])
    # Overlap on y.
    y1 = max(left[1], right[1])
    # Far x of the overlap.
    x2 = min(left[2], right[2])
    # Far y of the overlap.
    y2 = min(left[3], right[3])
    # Positive width.
    width = max(0.0, x2 - x1)
    # Positive height.
    height = max(0.0, y2 - y1)
    # Overlap area.
    intersection = width * height
    # No overlap.
    if intersection <= 0:
        # IoU is zero.
        return 0.0
    # Area of the first box.
    area_left = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    # Area of the second box.
    area_right = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    # Union.
    union = area_left + area_right - intersection
    # A degenerate box does not match.
    if union <= 0:
        # IoU is zero.
        return 0.0
    # Standard IoU.
    return intersection / union


# Greedy same-class match. Rough position means IoU at or above the threshold.
def match_detections(
    expected: list[ExpectedBox],
    detections: list[Detection],
    iou_min: float = 0.1,
    placed_count: int = 0,
) -> ConsistencyResult:
    """Return whether class and rough position agree. This does not edit a design."""
    # Furniture was placed, but none of it landed in the picture.
    if not expected and placed_count > 0:
        # An empty wall is not a match.
        return ConsistencyResult(
            matched=False,
            matched_count=0,
            expected_count=0,
            extra_count=len(detections),
            note="camera did not see the placed furniture",
        )
    # Detections not yet claimed.
    pool = list(detections)
    # How many expected boxes found a partner.
    matched_count = 0
    # Walk the projected objects in order.
    for box in expected:
        # Best remaining detection of the same class.
        best_index = -1
        # Its IoU.
        best_iou = 0.0
        # Search the pool.
        for index, detection in enumerate(pool):
            # Class must agree. The detector vocabulary is the locked taxonomy.
            if detection.category != box.category:
                # A different class cannot satisfy this object.
                continue
            # Rough position.
            overlap = _iou(box.xyxy, detection.xyxy)
            # Keep the closest class match.
            if overlap > best_iou:
                # Remember it.
                best_iou = overlap
                # Remember which detection.
                best_index = index
        # Claim it when the overlap is enough.
        if best_index >= 0 and best_iou >= iou_min:
            # Remove it so a second object cannot reuse it.
            pool.pop(best_index)
            # Count the pair.
            matched_count += 1
    # Anything left over is an extra piece of furniture.
    extra_count = len(pool)
    # Every projected object matched, and the detector did not add another.
    matched = matched_count == len(expected) and extra_count == 0
    # Sentence stored on the response.
    note = (
        f"matched {matched_count} of {len(expected)} projected objects; "
        f"{extra_count} extra detections"
    )
    # The loop in the service reads matched and may try another seed.
    return ConsistencyResult(
        matched=matched,
        matched_count=matched_count,
        expected_count=len(expected),
        extra_count=extra_count,
        note=note,
    )
