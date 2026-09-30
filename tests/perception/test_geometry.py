"""Geometry tests on a synthetic box room with known size. No model is involved."""

# Numerical arrays.
import numpy as np

# Code under test.
from spacedesigner.perception.geometry import focal_pixels
from spacedesigner.perception.pipeline import geometry_from_depth

# Synthetic room: length along z, width along x, height along y.
ROOM_Z, ROOM_X, ROOM_H = 5.0, 4.0, 2.6

# Camera height above the floor, looking straight ahead.
CAM_H = 1.4

# Image size of the synthetic render.
W, H = 320, 240


# Ray-cast the box room from the camera and return a depth map in metres.
def render_box(cam_x: float = 2.0, cam_z: float = 0.05, yaw: float = 0.0) -> np.ndarray:
    """Return z-depth for every pixel of a camera inside the box room."""
    # Focal length for a 26 mm equivalent lens.
    f = focal_pixels(W, 26.0)
    # Pixel grid.
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    # Ray directions in the camera frame (x right, y down, z forward).
    d = np.stack([(u - W / 2) / f, (v - H / 2) / f, np.ones_like(u, dtype=float)], axis=-1)
    # Rotate the rays about the vertical axis.
    c, s = np.cos(yaw), np.sin(yaw)
    # World directions: x = right, y = down, z = forward.
    dx, dy, dz = d[..., 0] * c + d[..., 2] * s, d[..., 1], -d[..., 0] * s + d[..., 2] * c
    # Camera position in world coordinates (y is down, so the floor is at +CAM_H).
    px, py, pz = cam_x, 0.0, cam_z
    # Distance to each of the six planes; invalid hits are infinite.
    hits = []
    # Walls at x = 0 and x = ROOM_X.
    for plane in (0.0, ROOM_X):
        # Ray parameter at the plane.
        t = np.where(np.abs(dx) > 1e-9, (plane - px) / np.where(dx == 0, 1e-9, dx), np.inf)
        # Only forward hits count.
        hits.append(np.where(t > 0, t, np.inf))
    # Walls at z = 0 and z = ROOM_Z.
    for plane in (0.0, ROOM_Z):
        # Ray parameter at the plane.
        t = np.where(np.abs(dz) > 1e-9, (plane - pz) / np.where(dz == 0, 1e-9, dz), np.inf)
        # Only forward hits count.
        hits.append(np.where(t > 0, t, np.inf))
    # Floor (y = +CAM_H) and ceiling (y = CAM_H - ROOM_H).
    for plane in (CAM_H, CAM_H - ROOM_H):
        # Ray parameter at the plane.
        t = np.where(np.abs(dy) > 1e-9, (plane - py) / np.where(dy == 0, 1e-9, dy), np.inf)
        # Only forward hits count.
        hits.append(np.where(t > 0, t, np.inf))
    # Nearest hit along the ray.
    t_min = np.min(np.stack(hits), axis=0)
    # Convert ray length to z-depth (the camera-frame z component).
    return (t_min * 1.0 * np.abs(d[..., 2]) / 1.0 * np.ones_like(t_min)).astype(np.float32)


# A camera near one end sees the whole room, which is measured within 30 cm.
def test_fit_recovers_box_room_size() -> None:
    """Length, width, and height come back close to the truth."""
    # Render and fit, using the same 26 mm lens.
    result = geometry_from_depth(render_box(), 26.0)
    # The floor must be found.
    assert result is not None
    # Room numbers in model metres.
    room = result["room"]
    # The ceiling plane is visible in this view.
    assert room["ceiling_found"] is True
    # Height within 15 cm.
    assert abs(room["height"] - ROOM_H) < 0.15
    # Long side within 30 cm.
    assert abs(room["length"] - ROOM_Z) < 0.3
    # Short side within 30 cm.
    assert abs(room["width"] - ROOM_X) < 0.3


# The fit is repeatable because the RANSAC seed is fixed.
def test_fit_is_deterministic() -> None:
    """Two runs give identical numbers."""
    # Same input twice.
    a = geometry_from_depth(render_box(), 26.0)
    # Second run.
    b = geometry_from_depth(render_box(), 26.0)
    # Identical rooms.
    assert a["room"] == b["room"]


# A turned camera still gives the same room because the wall direction is fitted.
def test_fit_handles_a_turned_camera() -> None:
    """A 20 degree yaw keeps the dimensions close."""
    # Turned render.
    result = geometry_from_depth(render_box(yaw=np.radians(20)), 26.0)
    # The floor must be found.
    assert result is not None
    # Height stays accurate.
    assert abs(result["room"]["height"] - ROOM_H) < 0.2
    # The long side stays within 50 cm.
    assert abs(result["room"]["length"] - ROOM_Z) < 0.5


# Flat depth has no floor plane at the camera-up orientation.
def test_fit_returns_none_for_a_blank_depth_map() -> None:
    """No valid depth means no room."""
    # All-zero depth is invalid everywhere.
    assert geometry_from_depth(np.zeros((H, W), dtype=np.float32), None) is None
