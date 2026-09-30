"""Photo pipeline: privacy, room type, detection, masks, depth, plane fits (needs .venv-train)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Numerical arrays.
import numpy as np

# Pillow image type.
from PIL import Image

# Back-projection and room fitting.
from spacedesigner.perception.geometry import (
    backproject,
    fit_room,
    focal_pixels,
)

# Item extraction from detections and masks.
from spacedesigner.perception.items import extract_items

# Privacy helpers.
from spacedesigner.perception.privacy import blur_faces

# Depth values outside this range (metres) are treated as invalid.
DEPTH_RANGE_M = (0.3, 12.0)


# Lift the pixels under each mask to camera-frame points.
def mask_points(points: np.ndarray, valid: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return the (N, 3) camera-frame points under a boolean mask."""
    # Only pixels with a valid depth count.
    keep = mask & valid
    # Index the point grid.
    return points[keep]


# Fit the room from a depth map, with optional detections and masks.
def geometry_from_depth(
    depth: np.ndarray,
    focal_35mm: float | None,
    detections: list[tuple[str, float, np.ndarray]] | None = None,
    masks: list[np.ndarray] | None = None,
) -> dict | None:
    """Return the unscaled room dictionary, or None when no floor was found."""
    # Image height and width.
    height, width = depth.shape
    # Focal length in pixels; square pixels are assumed.
    focal = focal_pixels(width, focal_35mm)
    # Camera-frame points.
    points = backproject(depth, focal, focal, width / 2, height / 2)
    # Valid depth mask.
    valid = np.isfinite(depth) & (depth > DEPTH_RANGE_M[0]) & (depth < DEPTH_RANGE_M[1])
    # Fit floor, ceiling, and walls.
    fit = fit_room(points, valid)
    # Report failure to the caller.
    if fit is None:
        # No floor found.
        return None
    # Lift detections with masks into 3-D.
    lifted = [
        (name, score, mask_points(points, valid, mask))
        for (name, score, _), mask in zip(detections or [], masks or [], strict=False)
    ]
    # Objects and openings in the room frame.
    objects, openings = extract_items(fit, lifted)
    # Collect the result the API needs.
    return {
        "room": {
            "length": fit.length,
            "width": fit.width,
            "height": fit.height,
            "ceiling_found": fit.ceiling_found,
        },
        "objects": objects,
        "openings": openings,
        "warnings": list(fit.warnings),
        "focal_pixels": focal,
    }


# Run every stage in order on an already metadata-free image.
def run_pipeline(image: Image.Image, focal_35mm: float | None = None) -> dict:
    """Return the unscaled perception result as plain JSON-ready data."""
    # Stage functions import torch, so load them here.
    from spacedesigner.perception import stages

    # Peak VRAM per stage.
    vram: dict[str, float] = {}
    # Privacy first: blur faces before any other model sees the pixels.
    image, faces = blur_faces(image)
    # Room type.
    rooms, vram["room_classifier"] = stages.classify_room(image)
    # Furniture boxes.
    detections, vram["detector"] = stages.detect_furniture(image)
    # Masks for those boxes.
    masks, vram["sam2"] = stages.segment_boxes(image, [d[2] for d in detections])
    # Metric depth.
    depth, vram["depth"] = stages.predict_depth(image)
    # Plane fits and assembly inputs.
    geometry = geometry_from_depth(depth, focal_35mm, detections, masks)
    # No floor: the caller shows the manual form.
    if geometry is None:
        # Signal failure with a readable reason.
        raise ValueError("no floor was found in the photo; enter the room by hand")
    # Attach the rest of the result.
    geometry.update(
        {
            "room_type": rooms[0][0],
            "room_type_scores": [[name, prob] for name, prob in rooms],
            "image": {"width": image.width, "height": image.height},
            "faces_blurred": faces,
            "detections": [[n, round(s, 3)] for n, s, _ in detections],
            "vram_mib": {k: round(v, 1) for k, v in vram.items()},
        }
    )
    # Return it.
    return geometry
