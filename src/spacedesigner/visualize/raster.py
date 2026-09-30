"""Render depth, segmentation, and a changed-region mask from the scene graph.

The camera uses the solver frame: floor x is world X, floor y is world Z, height is world Y.
This is a software rasterizer so the maps do not need a GPU or a second 3D engine.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Degrees to radians for the vertical field of view.
import math

# One record per projected object.
from dataclasses import dataclass

# Image arrays.
import numpy as np

# Dilate the inpaint mask by a few pixels.
from scipy.ndimage import binary_dilation

# Locked scene and design records.
from spacedesigner.schemas import Design, SceneGraph, SceneObject

# Vertical field of view in degrees.
FOV_Y_DEG = 55.0

# Eye height in metres, clamped below the ceiling by the renderer.
EYE_HEIGHT_M = 1.45

# How far inside the south wall the camera stands, in metres.
CAMERA_INSET_M = 0.35

# Triangles closer than this are clipped, in metres.
NEAR_M = 0.05

# Label ids that are not furniture.
FLOOR = 1
WALL = 2
DOOR = 3
WINDOW = 4

# Furniture labels start here so they do not collide with the room labels.
FURNITURE_BASE = 10

# Flat colours for the room shell. Furniture uses the plan palette.
_SHELL_RGB = {
    FLOOR: (214, 211, 209),
    WALL: (120, 113, 108),
    DOOR: (155, 34, 38),
    WINDOW: (76, 201, 240),
}

# Same order as the 2D plan, as RGB triples.
_PALETTE = (
    (142, 202, 230),
    (255, 183, 3),
    (144, 190, 109),
    (242, 132, 130),
    (189, 178, 255),
    (132, 165, 157),
)


# One furniture object as it landed in the image.
@dataclass
class ProjectedObject:
    """Pixel box of one scene-graph object, plus how many pixels won the z-buffer."""

    # Object id from the design.
    object_id: str
    # Taxonomy class.
    category: str
    # Inclusive-exclusive pixel box [x1, y1, x2, y2].
    xyxy: tuple[float, float, float, float]
    # Pixels whose label is this object.
    visible_pixels: int
    # True when the optimizer added or moved this object.
    changed: bool


# All maps for one design.
@dataclass
class SceneRender:
    """Depth, segmentation, colour, and the inpaint mask."""

    # RGB render of the scene graph. This is not a diffusion image.
    rgb: np.ndarray
    # Depth as 8-bit, nearer brighter, empty pixels 0.
    depth_u8: np.ndarray
    # Semantic colours. Same class shares a colour.
    segmentation: np.ndarray
    # 255 where inpainting is allowed.
    mask: np.ndarray
    # Integer label per pixel.
    labels: np.ndarray
    # Projected furniture.
    projections: list[ProjectedObject]


# World-axis size of one object. 90 and 270 swap the floor edges.
def _world_size(obj: SceneObject) -> tuple[float, float, float]:
    """Return (size x, height, size z) in the solver frame."""
    # Quarter turn, matching the plan renderer and the checker.
    quarter = round(obj.rotation / 90.0) % 4
    # Odd turns put local width on x and local length on z.
    if quarter in {1, 3}:
        # Swapped footprint. Height is never swapped.
        return obj.dimensions[1], obj.dimensions[2], obj.dimensions[0]
    # Even turns keep local length on x.
    return obj.dimensions[0], obj.dimensions[2], obj.dimensions[1]


# True when the design object is the same pose as the stored scene object.
def _unchanged(obj: SceneObject, scene: SceneGraph) -> bool:
    """Return True when this object was not added or moved by the optimizer."""
    # Scene objects by id.
    by_id = {item.id: item for item in scene.objects}
    # Source pose, if this id existed before the solve.
    source = by_id.get(obj.id)
    # A new catalog object is a changed region.
    if source is None:
        # Inpaint it.
        return False
    # Category must agree.
    if source.type != obj.type:
        # The type change is a changed region.
        return False
    # Rotation tolerance for JSON round trips.
    if abs(source.rotation - obj.rotation) > 1e-3:
        # A turn is a changed region.
        return False
    # Pair the two centres.
    centre_shift = zip(source.position, obj.position, strict=True)
    # A move is a changed region.
    if any(abs(left - right) > 1e-3 for left, right in centre_shift):
        # A move is a changed region.
        return False
    # Pair the two size triples.
    size_shift = zip(source.dimensions, obj.dimensions, strict=True)
    # A resize is a changed region.
    if any(abs(left - right) > 1e-3 for left, right in size_shift):
        # A resize is a changed region.
        return False
    # Same pose as the scene. The mask must not cover it.
    return True


# Twelve triangles of an axis-aligned box, in world metres.
def _box_triangles(center: tuple[float, float, float], size: tuple[float, float, float]) -> list:
    """Return triangles as lists of three xyz vertices."""
    # Centre.
    cx, cy, cz = center
    # Half extents.
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    # Eight corners. Index is ix + 2*iy + 4*iz.
    corners = []
    # z, then y, then x, so the index formula holds.
    for iz in (-1.0, 1.0):
        # Vertical pair.
        for iy in (-1.0, 1.0):
            # Horizontal pair.
            for ix in (-1.0, 1.0):
                # One corner.
                point = (cx + ix * hx, cy + iy * hy, cz + iz * hz)
                # Store the corner.
                corners.append(np.array(point, dtype=np.float64))
    # Six faces, two triangles each. Both sides are drawn.
    quads = (
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
    )
    # Collected triangles.
    triangles = []
    # Split each quad.
    for a, b, c, d in quads:
        # First half.
        triangles.append((corners[a], corners[b], corners[c]))
        # Second half.
        triangles.append((corners[a], corners[c], corners[d]))
    # Twelve triangles.
    return triangles


# Solid spans of one wall after openings are removed.
def _solid_spans(wall_length: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return (start, end) pieces of wall that are not openings."""
    # Clip each opening to the wall.
    clipped = []
    # One opening.
    for start, end in cuts:
        # Clamp.
        left = max(0.0, min(wall_length, start))
        # Clamp the far end.
        right = max(0.0, min(wall_length, end))
        # Keep a real gap.
        if right > left:
            # Record it.
            clipped.append((left, right))
    # Walk from the start of the wall.
    clipped.sort()
    # Solid pieces.
    spans = []
    # Next free metre.
    cursor = 0.0
    # Leave a gap per opening.
    for start, end in clipped:
        # Solid before this opening.
        if start > cursor + 1e-9:
            # Record it.
            spans.append((cursor, start))
        # Move past the opening.
        cursor = max(cursor, end)
    # Solid after the last opening.
    if cursor < wall_length - 1e-9:
        # Record it.
        spans.append((cursor, wall_length))
    # Pieces to extrude.
    return spans


# Openings on one wall, as start/end metres.
def _cuts(scene: SceneGraph, wall: str) -> list[tuple[float, float]]:
    """Return opening spans whose wall name matches."""
    # Collected spans.
    cuts = []
    # Every opening.
    for opening in scene.openings:
        # This wall only.
        if opening.wall.lower() != wall:
            # Next opening.
            continue
        # Position is the start.
        cuts.append((opening.position, opening.position + opening.width))
    # Spans for the solid-wall cutter.
    return cuts


# Room shell boxes: floor, walls, and opening marks. Furniture is separate.
def _shell_boxes(
    scene: SceneGraph,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], int]]:
    """Return (centre, size, label) for the room, in the solver frame."""
    # Room length, world X.
    length = scene.dimensions.length
    # Room width, world Z.
    width = scene.dimensions.width
    # Room height, world Y.
    height = scene.dimensions.height
    # Visual thickness, outside the floor so it does not cover furniture.
    thick = 0.08
    # Collected boxes.
    boxes = []
    # Floor, a hair below y = 0.
    boxes.append(((length / 2, -0.02, width / 2), (length, 0.04, width), FLOOR))
    # South wall, outside z = 0.
    for start, end in _solid_spans(length, _cuts(scene, "south")):
        # Span length.
        size_x = end - start
        # One solid piece.
        boxes.append(((start + size_x / 2, height / 2, -thick / 2), (size_x, height, thick), WALL))
    # North wall.
    for start, end in _solid_spans(length, _cuts(scene, "north")):
        # Span length.
        size_x = end - start
        # One solid piece.
        boxes.append(
            ((start + size_x / 2, height / 2, width + thick / 2), (size_x, height, thick), WALL)
        )
    # West wall.
    for start, end in _solid_spans(width, _cuts(scene, "west")):
        # Span length along z.
        size_z = end - start
        # One solid piece.
        boxes.append(((-thick / 2, height / 2, start + size_z / 2), (thick, height, size_z), WALL))
    # East wall.
    for start, end in _solid_spans(width, _cuts(scene, "east")):
        # Span length along z.
        size_z = end - start
        # One solid piece.
        boxes.append(
            ((length + thick / 2, height / 2, start + size_z / 2), (thick, height, size_z), WALL)
        )
    # Door and window marks in the gaps.
    for opening in scene.openings:
        # Window or door.
        kind = WINDOW if opening.type.lower() == "window" else DOOR
        # Vertical size of the mark. This is a drawing, not a solver input.
        mark_h = min(2.05, height) if kind == DOOR else max(0.0, min(height - 0.15, 2.15) - 0.9)
        # Skip a mark that does not fit.
        if mark_h <= 0.05:
            # Next opening.
            continue
        # Centre height.
        center_y = mark_h / 2 if kind == DOOR else 0.9 + mark_h / 2
        # Which wall.
        wall = opening.wall.lower()
        # Along-wall length.
        along = width if wall in {"east", "west"} else length
        # Clip the opening.
        start = max(0.0, opening.position)
        # Far end.
        end = min(along, opening.position + opening.width)
        # Visible span.
        span = end - start
        # Missed the wall.
        if span <= 1e-6:
            # Next opening.
            continue
        # Midpoint along the wall.
        mid = start + span / 2
        # South.
        if wall == "south":
            # Mark.
            boxes.append(((mid, center_y, -thick / 2), (span, mark_h, thick), kind))
        # North.
        elif wall == "north":
            # Mark.
            boxes.append(((mid, center_y, width + thick / 2), (span, mark_h, thick), kind))
        # West.
        elif wall == "west":
            # Mark.
            boxes.append(((-thick / 2, center_y, mid), (thick, mark_h, span), kind))
        # East.
        elif wall == "east":
            # Mark.
            boxes.append(((length + thick / 2, center_y, mid), (thick, mark_h, span), kind))
    # Shell only.
    return boxes


# Clip a triangle to the near plane. Returns zero, one, or two triangles.
def _clip_near(verts: list[np.ndarray]) -> list[list[np.ndarray]]:
    """Keep the part of the triangle with camera z >= NEAR_M."""
    # Polygon after clipping.
    output: list[np.ndarray] = []
    # Walk the edges.
    for index, current in enumerate(verts):
        # Previous vertex.
        previous = verts[index - 1]
        # Which ends are in front.
        current_in = float(current[2]) >= NEAR_M
        # Previous end.
        previous_in = float(previous[2]) >= NEAR_M
        # The edge crosses the near plane.
        if current_in != previous_in:
            # Interpolation factor.
            delta = float(current[2] - previous[2])
            # Avoid a zero divide on a grazing edge.
            factor = 0.0 if abs(delta) < 1e-12 else (NEAR_M - float(previous[2])) / delta
            # Point on the plane.
            output.append(previous + factor * (current - previous))
        # Keep the vertex that is in front.
        if current_in:
            # Add it.
            output.append(current)
    # Not enough for a triangle.
    if len(output) < 3:
        # Drop it.
        return []
    # One triangle.
    if len(output) == 3:
        # Keep it.
        return [output]
    # A quad becomes two triangles.
    return [[output[0], output[i], output[i + 1]] for i in range(1, len(output) - 1)]


# Draw one camera-space triangle into the z-buffer.
def _raster_triangle(
    verts: list[np.ndarray],
    label: int,
    zbuf: np.ndarray,
    labels: np.ndarray,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
) -> None:
    """Write nearer pixels of one triangle. verts are camera-space xyz."""
    # Project.
    pixels = []
    # One vertex.
    for vertex in verts:
        # Camera z is positive in front.
        depth = float(vertex[2])
        # Behind the near plane should already have been clipped.
        if depth <= NEAR_M * 0.5:
            # Skip the triangle.
            return
        # Pixel x.
        u = cx + fx * float(vertex[0]) / depth
        # Pixel y, image origin at the top.
        v = cy - fy * float(vertex[1]) / depth
        # Remember pixel and depth.
        pixels.append((u, v, depth))
    # Image size.
    height, width = zbuf.shape
    # Bounding box.
    min_u = max(int(math.floor(min(p[0] for p in pixels))), 0)
    # Far x.
    max_u = min(int(math.ceil(max(p[0] for p in pixels))), width)
    # Near y.
    min_v = max(int(math.floor(min(p[1] for p in pixels))), 0)
    # Far y.
    max_v = min(int(math.ceil(max(p[1] for p in pixels))), height)
    # Off screen or empty.
    if max_u <= min_u or max_v <= min_v:
        # Nothing to draw.
        return
    # Pixel centres.
    xs = np.arange(min_u, max_u, dtype=np.float64) + 0.5
    # Rows.
    ys = np.arange(min_v, max_v, dtype=np.float64) + 0.5
    # Grid.
    uu, vv = np.meshgrid(xs, ys)
    # Triangle corners in pixels.
    ax, ay = pixels[0][0], pixels[0][1]
    # Second.
    bx, by = pixels[1][0], pixels[1][1]
    # Third.
    cx0, cy0 = pixels[2][0], pixels[2][1]
    # Twice the signed area.
    denom = (by - cy0) * (ax - cx0) + (cx0 - bx) * (ay - cy0)
    # Degenerate.
    if abs(denom) < 1e-8:
        # Skip.
        return
    # Barycentric weights.
    w0 = ((by - cy0) * (uu - cx0) + (cx0 - bx) * (vv - cy0)) / denom
    # Second weight.
    w1 = ((cy0 - ay) * (uu - cx0) + (ax - cx0) * (vv - cy0)) / denom
    # Third weight.
    w2 = 1.0 - w0 - w1
    # Inside the triangle, with a small edge tolerance.
    inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    # Perspective-correct depth.
    inv = w0 / pixels[0][2] + w1 / pixels[1][2] + w2 / pixels[2][2]
    # Avoid a zero divide on a bad pixel.
    depth = np.divide(1.0, inv, out=np.full(inv.shape, np.inf), where=np.abs(inv) > 1e-12)
    # Current buffer window.
    window = zbuf[min_v:max_v, min_u:max_u]
    # Nearer than what is already stored.
    closer = inside & (depth < window) & np.isfinite(depth)
    # Write depth.
    window[closer] = depth[closer]
    # Write the label.
    labels[min_v:max_v, min_u:max_u][closer] = label


# Right, up, and forward for a camera that looks at a target. +Z in camera space is forward.
def _camera_basis(
    camera: np.ndarray, target: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return unit right, up, and forward axes."""
    # Direction from the camera to the furniture.
    forward = target - camera
    # Length of that direction.
    length = float(np.linalg.norm(forward))
    # A zero look direction falls back to looking north.
    if length < 1e-6:
        # World +Z.
        forward = np.array([0.0, 0.0, 1.0])
    else:
        # Unit forward.
        forward = forward / length
    # World up, unless the camera is looking straight up or down.
    world_up = np.array([0.0, 1.0, 0.0])
    # Image-right axis.
    right = np.cross(world_up, forward)
    # Looking vertically makes that cross product vanish.
    if float(np.linalg.norm(right)) < 1e-6:
        # Use north as the helper up instead.
        world_up = np.array([0.0, 0.0, 1.0])
        # Recompute right.
        right = np.cross(world_up, forward)
    # Unit right.
    right = right / float(np.linalg.norm(right))
    # Up, perpendicular to forward and right.
    up = np.cross(forward, right)
    # Unit up.
    up = up / float(np.linalg.norm(up))
    # Right, up, and the look direction.
    return right, up, forward


# Where to stand so the placed furniture is in frame, and what to look at.
def _view_pose(scene: SceneGraph, design: Design) -> tuple[np.ndarray, np.ndarray]:
    """Return (camera position, look target) in the solver frame."""
    # Room length, world X.
    length = scene.dimensions.length
    # Room width, world Z.
    width = scene.dimensions.width
    # Stay off the walls.
    margin = min(CAMERA_INSET_M, length * 0.2, width * 0.2)
    # No furniture: look at the middle of the room.
    if not design.objects:
        # Room centre.
        target = np.array([length / 2, 0.4, width / 2], dtype=np.float64)
    else:
        # Mean footprint centre.
        focus_x = sum(obj.position[0] for obj in design.objects) / len(design.objects)
        # Floor y is world Z.
        focus_z = sum(obj.position[1] for obj in design.objects) / len(design.objects)
        # Look at about half the average height, so the boxes are not on the floor line.
        focus_y = sum(obj.dimensions[2] for obj in design.objects) / len(design.objects) * 0.5
        # The aim point.
        target = np.array([focus_x, max(0.2, focus_y), focus_z], dtype=np.float64)
    # Step back toward the south wall, far enough to see a desk.
    back = max(1.1, min(width * 0.4, 2.4))
    # Prefer standing south of the cluster.
    cam_z = float(target[2]) - back
    # Camera x stays near the cluster, inside the room.
    cam_x = min(max(float(target[0]), margin), length - margin)
    # Not enough floor south of the furniture: stand to the north instead.
    if cam_z < margin:
        # North of the cluster.
        cam_z = min(width - margin, float(target[2]) + back)
    # Still inside the walls.
    cam_z = min(max(cam_z, margin), width - margin)
    # Above the furniture, under the ceiling, so the view looks down.
    cam_y = min(scene.dimensions.height - 0.15, max(EYE_HEIGHT_M, float(target[1]) + 1.1))
    # Do not sit on the floor.
    cam_y = max(cam_y, 0.8)
    # The eye.
    camera = np.array([cam_x, cam_y, cam_z], dtype=np.float64)
    # Eye and aim point.
    return camera, target


# Draw every triangle of one world box.
def _draw_box(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    label: int,
    camera: np.ndarray,
    basis: tuple[np.ndarray, np.ndarray, np.ndarray],
    zbuf: np.ndarray,
    labels: np.ndarray,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
) -> None:
    """Rasterize one box from the given camera."""
    # Image right, up, and forward.
    right, up, forward = basis
    # Each triangle.
    for triangle in _box_triangles(center, size):
        # Rotate into camera space. +Z is toward the furniture, not world north.
        cam_verts = []
        # One corner.
        for vertex in triangle:
            # Offset from the eye.
            delta = vertex - camera
            # Camera coordinates.
            cam_verts.append(
                np.array(
                    [
                        float(np.dot(delta, right)),
                        float(np.dot(delta, up)),
                        float(np.dot(delta, forward)),
                    ]
                )
            )
        # Clip and draw.
        for clipped in _clip_near(cam_verts):
            # One front piece.
            _raster_triangle(clipped, label, zbuf, labels, fx, fy, cx, cy)


# Colour for a label.
def _color(label: int, class_index: dict[int, int]) -> tuple[int, int, int]:
    """Return an RGB triple for a z-buffer label."""
    # Room shell.
    if label in _SHELL_RGB:
        # Fixed shell colour.
        return _SHELL_RGB[label]
    # Furniture palette, stable for a class index.
    return _PALETTE[class_index.get(label, 0) % len(_PALETTE)]


# Render one design.
def render_scene(scene: SceneGraph, design: Design, size: int = 512) -> SceneRender:
    """Return depth, segmentation, colour, and the changed-region mask."""
    # Square image. Diffusion later requires a multiple of 8.
    if size < 32 or size % 8 != 0:
        # Refuse a size the inpainter could not use.
        raise ValueError("render size must be a multiple of 8 and at least 32")
    # Eye above the south or north side, aimed at the placed furniture.
    camera, target = _view_pose(scene, design)
    # Axes for that aim. World +Z is no longer assumed to be forward.
    basis = _camera_basis(camera, target)
    # Focal length from the vertical field of view.
    fy = (size / 2) / math.tan(math.radians(FOV_Y_DEG) / 2)
    # Square pixels.
    fx = fy
    # Principal point.
    cx = size / 2
    # Principal point.
    cy = size / 2
    # Z-buffer starts empty.
    zbuf = np.full((size, size), np.inf, dtype=np.float64)
    # Labels start empty.
    labels = np.zeros((size, size), dtype=np.int32)
    # Room shell first.
    for center, box_size, label in _shell_boxes(scene):
        # Draw it.
        _draw_box(center, box_size, label, camera, basis, zbuf, labels, fx, fy, cx, cy)
    # Class index for stable colours.
    class_index: dict[int, int] = {}
    # Which furniture labels the optimizer changed.
    changed_labels: set[int] = set()
    # Projection records, filled after the z-buffer is done.
    pending: list[tuple[int, SceneObject, bool]] = []
    # Furniture in design order.
    for index, obj in enumerate(design.objects):
        # Label for this instance.
        label = FURNITURE_BASE + index
        # Colour index by category name so one class stays one colour.
        class_index[label] = sum(ord(ch) for ch in obj.type) % len(_PALETTE)
        # World size.
        size_x, size_y, size_z = _world_size(obj)
        # Skip a non-positive box.
        if min(size_x, size_y, size_z) <= 0:
            # Next object.
            continue
        # Centre. The box sits on the floor.
        center = (obj.position[0], size_y / 2, obj.position[1])
        # Draw it.
        _draw_box(
            # World centre.
            center,
            # World size.
            (size_x, size_y, size_z),
            # Instance label.
            label,
            # Eye.
            camera,
            # Look axes.
            basis,
            # Depth buffer.
            zbuf,
            # Label buffer.
            labels,
            # Focal length x.
            fx,
            # Focal length y.
            fy,
            # Principal x.
            cx,
            # Principal y.
            cy,
        )
        # Whether the mask may cover it.
        changed = not _unchanged(obj, scene)
        # Remember for the projection list.
        pending.append((label, obj, changed))
        # Changed labels become the inpaint mask.
        if changed:
            # Allow inpainting here.
            changed_labels.add(label)
    # Colour images.
    rgb = np.full((size, size, 3), 228, dtype=np.uint8)
    # Segmentation starts as the same empty colour.
    segmentation = np.full((size, size, 3), 228, dtype=np.uint8)
    # Paint each used label.
    for label in np.unique(labels):
        # Empty stays the background.
        if int(label) == 0:
            # Next label.
            continue
        # Pixels of this label.
        paint = labels == label
        # RGB triple.
        colour = _color(int(label), class_index)
        # Base render.
        rgb[paint] = colour
        # Semantic map uses the same colours.
        segmentation[paint] = colour
    # Valid depths.
    valid = np.isfinite(zbuf) & (labels > 0)
    # 8-bit depth, empty stays 0, nearer is brighter.
    depth_u8 = np.zeros((size, size), dtype=np.uint8)
    # Only when something was drawn.
    if np.any(valid):
        # Near and far of the visible surfaces.
        near = float(np.min(zbuf[valid]))
        # Far.
        far = float(np.max(zbuf[valid]))
        # Span.
        span = max(far - near, 1e-6)
        # Invert so nearer is 255.
        scaled = (far - zbuf[valid]) / span
        # Write 1..255 so 0 remains empty.
        depth_u8[valid] = np.clip(np.rint(1 + 254 * scaled), 1, 255).astype(np.uint8)
    # Instance mask before dilation.
    if changed_labels:
        # Pixels of changed furniture.
        raw_mask = np.isin(labels, list(changed_labels))
    # No changed object.
    else:
        # Empty mask.
        raw_mask = np.zeros((size, size), dtype=bool)
    # A few pixels of context around the changed furniture.
    radius = max(1, size // 128)
    # Dilate.
    dilated = binary_dilation(raw_mask, iterations=radius) if np.any(raw_mask) else raw_mask
    # Walls, doors, windows, and unchanged furniture stay pixel-locked.
    protected = np.isin(labels, [WALL, DOOR, WINDOW])
    # Unchanged furniture labels.
    for label, _obj, changed in pending:
        # Keep these pixels out of the mask even after dilation.
        if not changed:
            # Add them to the lock.
            protected = protected | (labels == label)
    # Final mask. Floor pixels next to a new object may be inpainted.
    mask_bool = dilated & ~protected
    # 8-bit mask, 255 means the inpainter may edit.
    mask = np.where(mask_bool, 255, 0).astype(np.uint8)
    # Projections from the winning pixels.
    projections: list[ProjectedObject] = []
    # One object.
    for label, obj, changed in pending:
        # Pixels of this instance.
        pixels = np.argwhere(labels == label)
        # Fully hidden.
        if len(pixels) == 0:
            # Still record an empty box so the caller can ignore it.
            projections.append(
                ProjectedObject(obj.id, obj.type, (0.0, 0.0, 0.0, 0.0), 0, changed)
            )
            # Next object.
            continue
        # Rows and columns. argwhere returns (row, col).
        rows = pixels[:, 0]
        # Columns.
        cols = pixels[:, 1]
        # Pixel box.
        box = (float(cols.min()), float(rows.min()), float(cols.max() + 1), float(rows.max() + 1))
        # Record it.
        projections.append(ProjectedObject(obj.id, obj.type, box, int(len(pixels)), changed))
    # All maps.
    return SceneRender(
        rgb=rgb,
        depth_u8=depth_u8,
        segmentation=segmentation,
        mask=mask,
        labels=labels,
        projections=projections,
    )


# Copy the base image onto every pixel the mask does not allow the model to edit.
def lock_unchanged(base: np.ndarray, edited: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return edited pixels only where mask is 255. Everywhere else stays base."""
    # The three arrays must line up.
    if base.shape != edited.shape or mask.shape != base.shape[:2]:
        # Refuse a bad composite.
        raise ValueError("lock_unchanged inputs must share a height and width")
    # Start from the locked render.
    output = base.copy()
    # Editable pixels.
    editable = mask > 127
    # Replace only those.
    output[editable] = edited[editable]
    # Unchanged regions are byte-identical to the base.
    return output
