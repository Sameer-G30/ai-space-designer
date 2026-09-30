"""Turn detections lifted to 3-D into floor objects and wall openings (numpy only)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Numerical arrays.
import numpy as np

# Room fit and frame helpers.
from spacedesigner.perception.geometry import FLOOR_CLASSES, RoomFit, to_room_frame

# Smallest door or window width kept, in metres.
MIN_OPENING_M = 0.4

# Fewest 3-D points a detection needs to become an object or an opening.
MIN_POINTS = 50

# Most objects kept on the scene graph, highest detector score first.
MAX_OBJECTS = 12


# Choose the wall whose line is closest to an opening centre.
def nearest_wall(x: float, y: float, length: float, width: float) -> str:
    """Return south, north, west, or east for a point in the room frame."""
    # Distance to each wall line.
    distances = {"south": y, "north": width - y, "west": x, "east": length - x}
    # The smallest distance wins.
    return min(distances, key=distances.get)


# Extract floor objects and openings from detections already lifted to 3-D.
def extract_items(
    fit: RoomFit, detections: list[tuple[str, float, np.ndarray]]
) -> tuple[list[dict], list[dict]]:
    """Return (objects, openings) in the room frame and unscaled model metres."""
    # Objects to return.
    objects: list[dict] = []
    # Openings to return.
    openings: list[dict] = []
    # Walk detections from the most confident.
    for name, score, pts in sorted(detections, key=lambda d: -d[1]):
        # Too few points: the mask is too small or had no valid depth.
        if len(pts) < MIN_POINTS:
            # Skip it.
            continue
        # Lift the points into the room frame.
        room = to_room_frame(fit, pts)
        # Doors and windows become openings on the nearest wall.
        if name in ("door", "window"):
            # Robust centre of the opening.
            cx, cy = np.median(room[:, 0]), np.median(room[:, 1])
            # Wall it sits on.
            wall = nearest_wall(float(cx), float(cy), fit.length, fit.width)
            # Along-wall coordinate and wall length.
            along, wall_len = (
                (room[:, 0], fit.length) if wall in ("north", "south") else (room[:, 1], fit.width)
            )
            # Trimmed extent along the wall.
            lo, hi = np.percentile(along, [5, 95])
            # Opening width, at least the minimum.
            span = max(float(hi - lo), MIN_OPENING_M)
            # Start inside the wall.
            start = float(np.clip(lo, 0.0, max(0.0, wall_len - span)))
            # Record the opening; the width never exceeds the wall.
            openings.append(
                {"type": name, "wall": wall, "position": start, "width": min(span, wall_len)}
            )
            # Next detection.
            continue
        # Only floor-standing furniture becomes an object.
        if name not in FLOOR_CLASSES:
            # Skip wall art, curtains, lamps, and the like.
            continue
        # Footprint extents with trimming.
        x0, x1 = np.percentile(room[:, 0], [5, 95])
        # Second footprint axis.
        y0, y1 = np.percentile(room[:, 1], [5, 95])
        # Height is the high percentile above the floor.
        top = float(np.percentile(room[:, 2], 95))
        # Record the object with its detector score.
        objects.append(
            {
                "type": name,
                "score": float(score),
                "footprint": [float(x0), float(x1), float(y0), float(y1)],
                "height": top,
            }
        )
    # Keep the best detections only.
    return objects[:MAX_OBJECTS], openings
