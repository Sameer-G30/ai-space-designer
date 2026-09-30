"""Depth to room geometry: back-projection, RANSAC floor, ceiling, and wall fits (numpy only)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Plain dataclass holds the fitted room.
from dataclasses import dataclass, field

# Numerical arrays.
import numpy as np

# Default 35 mm equivalent focal length of a phone main camera (about a 69 degree wide view).
DEFAULT_FOCAL_35MM = 26.0

# Width of the 35 mm film frame in millimetres, used to turn a focal length into pixels.
FILM_WIDTH_MM = 36.0

# Plane inlier distance in metres for the floor and ceiling.
PLANE_TOLERANCE_M = 0.05

# Wall line inlier distance in metres.
WALL_TOLERANCE_M = 0.08

# Points lower than this above the floor are ignored when fitting walls (furniture lives here).
WALL_MIN_HEIGHT_M = 1.0

# Ceiling must be at least this far above the floor to count.
CEILING_MIN_M = 1.8

# Ceiling must be no higher than this to count.
CEILING_MAX_M = 5.0

# Height used (with low confidence) when no ceiling plane is found.
FALLBACK_HEIGHT_M = 2.6

# Maximum tilt of the floor normal from the camera up axis, in degrees.
FLOOR_MAX_TILT_DEG = 35.0

# Trim this percentile from each end of the wall-aligned extent, to ignore stray depth pixels.
EXTENT_TRIM_PCT = 1.0

# Random seed so every run gives the same answer.
SEED = 20260930

# Classes that stand on the floor and go on the scene graph as objects.
FLOOR_CLASSES = frozenset(
    {
        "bed",
        "sofa",
        "armchair",
        "chair",
        "stool",
        "bench",
        "ottoman",
        "table",
        "desk",
        "coffee_table",
        "side_table",
        "nightstand",
        "dresser",
        "cabinet",
        "shelf",
        "tv_stand",
    }
)


# One fitted room, in the camera-derived frame and in unscaled model metres.
@dataclass
class RoomFit:
    """Floor frame, wall angle, and extents of one view."""

    # Floor basis vectors (camera frame) that span the horizontal plane.
    e1: np.ndarray
    # Second floor basis vector.
    e2: np.ndarray
    # Floor normal pointing up (camera frame).
    normal: np.ndarray
    # Floor plane offset so height = normal . p + offset.
    offset: float
    # Wall direction angle in the (e1, e2) plane, radians.
    theta: float
    # Minimum of the wall-aligned coordinate along the long axis.
    min_long: float
    # Minimum of the wall-aligned coordinate along the short axis.
    min_short: float
    # True when the long axis is the wall-aligned "a" axis.
    long_is_a: bool
    # Room length (long side) in model metres.
    length: float
    # Room width (short side) in model metres.
    width: float
    # Room height in model metres.
    height: float
    # True when a ceiling plane was actually found.
    ceiling_found: bool
    # Notes for the response (what failed, what was assumed).
    warnings: list[str] = field(default_factory=list)


# Pixel focal length from an EXIF or default 35 mm equivalent value.
def focal_pixels(width_px: int, focal_35mm: float | None) -> float:
    """Return the focal length in pixels for an image of the given width."""
    # Use the default when the photo carries no focal length.
    mm = focal_35mm if focal_35mm else DEFAULT_FOCAL_35MM
    # Scale the film-frame focal length to the image width.
    return mm / FILM_WIDTH_MM * width_px


# Turn a depth map into camera-frame points with x right, y down, z forward.
def backproject(depth: np.ndarray, fx: float, fy: float, cx: float, cy: float) -> np.ndarray:
    """Return an (H, W, 3) array of metric points."""
    # Image height and width.
    height, width = depth.shape
    # Pixel grids.
    u, v = np.meshgrid(np.arange(width), np.arange(height))
    # Scale the normalized rays by depth.
    x = (u - cx) * depth / fx
    # Vertical component (down is positive).
    y = (v - cy) * depth / fy
    # Stack into one array.
    return np.stack([x, y, depth], axis=-1)


# RANSAC plane fit with an optional normal prior.
def ransac_plane(
    points: np.ndarray,
    rng: np.random.Generator,
    tolerance: float = PLANE_TOLERANCE_M,
    iterations: int = 400,
    prior: np.ndarray | None = None,
    max_angle_deg: float = 180.0,
) -> tuple[np.ndarray, float, np.ndarray] | None:
    """Return (unit normal, offset, inlier mask) of the best plane, or None."""
    # Three points are needed for a plane.
    if len(points) < 3:
        # Nothing to fit.
        return None
    # Smallest allowed cosine between the normal and the prior.
    min_cos = np.cos(np.radians(max_angle_deg))
    # Best plane so far.
    best: tuple[np.ndarray, float, int] | None = None
    # Try random triples.
    for _ in range(iterations):
        # Three distinct sample indices.
        sample = points[rng.choice(len(points), 3, replace=False)]
        # Plane normal from the cross product.
        normal = np.cross(sample[1] - sample[0], sample[2] - sample[0])
        # Length of the cross product.
        norm = np.linalg.norm(normal)
        # Skip collinear samples.
        if norm < 1e-9:
            # Try another triple.
            continue
        # Unit normal.
        normal = normal / norm
        # Enforce the prior direction and sign.
        if prior is not None:
            # Flip so the normal points the same way as the prior.
            if normal @ prior < 0:
                # Flip the sign.
                normal = -normal
            # Reject planes tilted too far.
            if normal @ prior < min_cos:
                # Try another triple.
                continue
        # Plane offset.
        offset = -float(normal @ sample[0])
        # Count points within the tolerance.
        count = int((np.abs(points @ normal + offset) < tolerance).sum())
        # Keep the plane with the most inliers.
        if best is None or count > best[2]:
            # Store the new best.
            best = (normal, offset, count)
    # No valid triple at all.
    if best is None:
        # Nothing found.
        return None
    # Refine with a least-squares fit over the inliers.
    normal, offset, _ = best
    # Inliers of the best plane.
    inliers = np.abs(points @ normal + offset) < tolerance
    # Enough inliers to refine.
    if inliers.sum() >= 10:
        # Centre of the inliers.
        centre = points[inliers].mean(axis=0)
        # Smallest singular vector is the plane normal.
        normal = np.linalg.svd(points[inliers] - centre, full_matrices=False)[2][-1]
        # Keep the orientation of the RANSAC normal.
        if normal @ best[0] < 0:
            # Flip the sign.
            normal = -normal
        # Offset through the centre.
        offset = -float(normal @ centre)
        # Recount the inliers.
        inliers = np.abs(points @ normal + offset) < tolerance
    # Return the refined plane.
    return normal, offset, inliers


# RANSAC line fit in two dimensions, used for the dominant wall direction.
def ransac_line_angle(
    points: np.ndarray, rng: np.random.Generator, tolerance: float = WALL_TOLERANCE_M
) -> float | None:
    """Return the angle of the line with the most inliers, in radians."""
    # Two points are needed.
    if len(points) < 10:
        # Nothing to fit.
        return None
    # Best angle and its inlier count.
    best_angle, best_count = None, -1
    # Try random pairs.
    for _ in range(500):
        # Two distinct samples.
        a, b = points[rng.choice(len(points), 2, replace=False)]
        # Direction between them.
        direction = b - a
        # Length of the direction.
        norm = np.linalg.norm(direction)
        # Skip near-identical points.
        if norm < 0.3:
            # Try another pair.
            continue
        # Unit normal of the line in 2-D.
        normal = np.array([-direction[1], direction[0]]) / norm
        # Count points within the tolerance of the line.
        count = int((np.abs((points - a) @ normal) < tolerance).sum())
        # Keep the line with the most inliers.
        if count > best_count:
            # Store the new best angle.
            best_angle, best_count = float(np.arctan2(direction[1], direction[0])), count
    # Return the best angle, or None.
    return best_angle


# Fit floor, ceiling, and walls to one depth map.
def fit_room(points: np.ndarray, valid: np.ndarray) -> RoomFit | None:
    """Return a RoomFit from camera-frame points, or None if no floor was found."""
    # Seeded generator makes every run repeatable.
    rng = np.random.default_rng(SEED)
    # Flatten to a point list and keep valid depths.
    flat = points.reshape(-1, 3)[valid.reshape(-1)]
    # Too few points to fit anything.
    if len(flat) < 500:
        # Report failure.
        return None
    # Subsample for speed.
    sample = flat[rng.choice(len(flat), min(len(flat), 30000), replace=False)]
    # Camera up axis (y points down in the camera frame).
    up = np.array([0.0, -1.0, 0.0])
    # Floor is the biggest plane whose normal is near the up axis.
    floor = ransac_plane(sample, rng, prior=up, max_angle_deg=FLOOR_MAX_TILT_DEG)
    # No floor plane at all.
    if floor is None:
        # Report failure.
        return None
    # Unpack the floor plane.
    normal, offset, floor_inliers = floor
    # Sign: height above the floor is positive for points above it; the camera sits above.
    if offset < 0:
        # Flip so the camera has positive height.
        normal, offset = -normal, -offset
    # Notes for the response.
    warnings: list[str] = []
    # Too few floor points means the floor is barely visible.
    if floor_inliers.mean() < 0.03:
        # Tell the user.
        warnings.append("the floor is barely visible, so the room size is uncertain")
    # Height of every sample above the floor.
    heights = sample @ normal + offset
    # Ceiling candidates lie well above the floor.
    high = sample[heights > CEILING_MIN_M]
    # Ceiling fit.
    ceiling = ransac_plane(high, rng, prior=normal, max_angle_deg=15.0) if len(high) > 200 else None
    # Room height starts as the fallback.
    height, ceiling_found = FALLBACK_HEIGHT_M, False
    # Accept a ceiling with enough support and a plausible height.
    if ceiling is not None and ceiling[2].sum() >= 0.01 * len(sample):
        # Ceiling height above the floor along the floor normal, using the inlier mean.
        ceiling_height = float((high[ceiling[2]] @ normal + offset).mean())
        # Plausible ceiling.
        if CEILING_MIN_M <= ceiling_height <= CEILING_MAX_M:
            # Use it.
            height, ceiling_found = ceiling_height, True
    # No ceiling: use the highest visible point if it is plausible.
    if not ceiling_found:
        # Top of the visible scene above the floor.
        top = float(np.percentile(heights, 99))
        # A plausible wall top is better than a blind default.
        if CEILING_MIN_M <= top <= CEILING_MAX_M:
            # Use the visible top.
            height = top
        # Explain the assumption.
        warnings.append("no ceiling plane was found, so the height is a visible-top estimate")
    # Basis of the horizontal plane.
    e1 = np.cross(normal, np.array([0.0, 0.0, 1.0]))
    # Fall back if the normal is parallel to the forward axis.
    if np.linalg.norm(e1) < 1e-6:
        # Use the right axis instead.
        e1 = np.cross(normal, np.array([1.0, 0.0, 0.0]))
    # Unit first basis vector.
    e1 = e1 / np.linalg.norm(e1)
    # Second basis vector completes the frame.
    e2 = np.cross(normal, e1)
    # Horizontal coordinates of the samples.
    uv = np.stack([sample @ e1, sample @ e2], axis=1)
    # Wall band: above furniture and below the ceiling.
    band = (heights > WALL_MIN_HEIGHT_M) & (heights < height - 0.1)
    # Not enough wall points: fall back to every point above the floor.
    if band.sum() < 300:
        # Use everything above 0.3 m.
        band = heights > 0.3
        # Explain the weaker fit.
        warnings.append("few wall points were visible, so the walls were fitted to all surfaces")
    # Dominant wall direction by RANSAC.
    theta = ransac_line_angle(uv[band], rng)
    # No line: fall back to the camera axes.
    if theta is None:
        # Axis-aligned.
        theta = 0.0
        # Explain the assumption.
        warnings.append("no wall line was found, so the room is aligned to the camera")
    # Rotate into wall-aligned coordinates.
    rot = np.array([[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]])
    # Wall-aligned (a, b) coordinates.
    ab = uv[band] @ rot.T
    # The floor and the camera are inside the room too. A view that only sees one wall still
    # shows how far the floor runs, so floor points and the camera foot join the extent.
    floor_uv = uv[np.abs(heights) < 2 * PLANE_TOLERANCE_M]
    # Camera position projected onto the floor plane is the origin of the (e1, e2) frame.
    extent_points = np.concatenate([ab, floor_uv @ rot.T])
    # Trimmed extent along a.
    lo_a, hi_a = np.percentile(extent_points[:, 0], [EXTENT_TRIM_PCT, 100 - EXTENT_TRIM_PCT])
    # Trimmed extent along b.
    lo_b, hi_b = np.percentile(extent_points[:, 1], [EXTENT_TRIM_PCT, 100 - EXTENT_TRIM_PCT])
    # The camera foot is the origin of the wall frame. A trim must not drop it, so extend to it.
    lo_a, hi_a = min(lo_a, 0.0), max(hi_a, 0.0)
    # Same for the second axis.
    lo_b, hi_b = min(lo_b, 0.0), max(hi_b, 0.0)
    # Extent sizes.
    size_a, size_b = float(hi_a - lo_a), float(hi_b - lo_b)
    # Long side is the room length.
    long_is_a = size_a >= size_b
    # Assemble the fit.
    return RoomFit(
        e1=e1,
        e2=e2,
        normal=normal,
        offset=float(offset),
        theta=float(theta),
        min_long=float(lo_a if long_is_a else lo_b),
        min_short=float(lo_b if long_is_a else lo_a),
        long_is_a=long_is_a,
        length=max(size_a, size_b),
        width=min(size_a, size_b),
        height=float(height),
        ceiling_found=ceiling_found,
        warnings=warnings,
    )


# Room-frame coordinates (x along length, y along width, z up) for camera-frame points.
def to_room_frame(fit: RoomFit, pts: np.ndarray) -> np.ndarray:
    """Return an (N, 3) array in the room frame, in unscaled model metres."""
    # Height above the floor.
    z = pts @ fit.normal + fit.offset
    # Horizontal coordinates.
    uv = np.stack([pts @ fit.e1, pts @ fit.e2], axis=1)
    # Rotation into the wall frame.
    cos, sin = np.cos(fit.theta), np.sin(fit.theta)
    # Rotation matrix.
    rot = np.array([[cos, sin], [-sin, cos]])
    # Wall-aligned coordinates.
    ab = uv @ rot.T
    # Pick which wall axis is the long one.
    long_c, short_c = (ab[:, 0], ab[:, 1]) if fit.long_is_a else (ab[:, 1], ab[:, 0])
    # Shift so the room corner is the origin.
    return np.stack([long_c - fit.min_long, short_c - fit.min_short, z], axis=1)
