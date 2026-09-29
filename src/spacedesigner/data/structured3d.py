"""Extract room, plane, and dimension labels from the Structured3D annotation and bbox zips."""

# Annotations on Python 3.11.
from __future__ import annotations

# Parses annotation_3d.json and bbox_3d.json.
import json

# Scene folder names.
import re

# Reads members without unpacking.
import zipfile

# Tallies.
from collections import Counter

# Array math.
import numpy as np

# Convex hull for a footprint area estimate.
from scipy.spatial import ConvexHull, QhullError

# Shared helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    histogram,
    processed_dir,
    raw_dir,
    write_json,
    write_jsonl,
)

# Semantic types that are not rooms.
NON_ROOM_TYPES = {"door", "window", "outwall"}

# Plausible room limits in millimetres (Structured3D units).
MIN_SIDE_MM, MAX_SIDE_MM = 500.0, 30000.0

# Plausible ceiling heights in millimetres.
MIN_HEIGHT_MM, MAX_HEIGHT_MM = 1500.0, 6000.0

# Scene folder name pattern.
SCENE = re.compile(r"Structured3D/scene_(\d{5})/")


def official_split(scene_number: int) -> str:
    """Return the official split: 0-2999 train, 3000-3249 val, 3250-3499 test."""
    # Train range.
    if scene_number < 3000:
        # Train.
        return "train"
    # Val range.
    if scene_number < 3250:
        # Val.
        return "val"
    # Everything else is test.
    return "test"


def room_dimensions(annotation: dict) -> tuple[list[dict], Counter]:
    """Return per-room dimension rows and a Counter of drop reasons for one scene."""
    # Reasons rooms were dropped.
    dropped: Counter = Counter()
    # Rooms that pass every check.
    rooms: list[dict] = []
    # Planes by id.
    planes = {p["ID"]: p for p in annotation["planes"]}
    # Plane-to-line and line-to-junction incidence matrices.
    plane_line = np.array(annotation["planeLineMatrix"], dtype=bool)
    # Line to junction.
    line_junction = np.array(annotation["lineJunctionMatrix"], dtype=bool)
    # Junction coordinates.
    junction_ids = [j["ID"] for j in annotation["junctions"]]
    # Coordinates aligned with the matrix columns.
    coords = np.array(
        [j["coordinate"] for j in sorted(annotation["junctions"], key=lambda j: j["ID"])],
        dtype=float,
    )
    # Sanity: junction ids must run 0..N-1 to index the matrix.
    if sorted(junction_ids) != list(range(len(junction_ids))):
        # Cannot index the matrices.
        dropped["scene_bad_junction_ids"] += 1
        # No rooms.
        return [], dropped
    # Every semantic entry that is a room.
    for semantic in annotation["semantics"]:
        # Skip doors, windows, and the outer wall.
        if semantic["type"] in NON_ROOM_TYPES:
            # Next entry.
            continue
        # Wall planes of this room.
        wall_ids = [i for i in semantic["planeID"] if planes[i]["type"] == "wall"]
        # Need at least three walls.
        if len(wall_ids) < 3:
            # Count it.
            dropped["room_too_few_walls"] += 1
            # Next room.
            continue
        # Junctions touching any wall line of the room.
        lines = plane_line[wall_ids].any(axis=0)
        # Junction mask.
        mask = line_junction[lines].any(axis=0)
        # Coordinates of those junctions.
        pts = coords[mask]
        # Nothing found.
        if len(pts) < 3 or not np.all(np.isfinite(pts)):
            # Count it.
            dropped["room_bad_junctions"] += 1
            # Next room.
            continue
        # Extents in x, y and z (mm).
        extent = pts.max(axis=0) - pts.min(axis=0)
        # Walls are vertical, so the x-y positions of all wall junctions outline the footprint.
        floor_pts = np.unique(pts[:, :2], axis=0)
        # Convex hull area of the footprint (an upper bound for L-shaped rooms).
        try:
            # Hull of floor points.
            area_mm2 = float(ConvexHull(floor_pts).volume)
        except (QhullError, ValueError):
            # Collinear or too few points.
            dropped["room_degenerate_footprint"] += 1
            # Next room.
            continue
        # A hull smaller than the minimum room footprint is a degenerate outline.
        if area_mm2 < MIN_SIDE_MM * MIN_SIDE_MM:
            # Count it.
            dropped["room_degenerate_footprint"] += 1
            # Next room.
            continue
        # Width and length limits.
        if not (
            MIN_SIDE_MM <= extent[0] <= MAX_SIDE_MM and MIN_SIDE_MM <= extent[1] <= MAX_SIDE_MM
        ):
            # Count it.
            dropped["room_implausible_size"] += 1
            # Next room.
            continue
        # Height limits.
        if not (MIN_HEIGHT_MM <= extent[2] <= MAX_HEIGHT_MM):
            # Count it.
            dropped["room_implausible_height"] += 1
            # Next room.
            continue
        # Keep the room.
        rooms.append(
            {
                "room_id": semantic["ID"],
                "room_type": semantic["type"],
                "n_walls": len(wall_ids),
                "width_mm": round(float(extent[0]), 1),
                "length_mm": round(float(extent[1]), 1),
                "height_mm": round(float(extent[2]), 1),
                "hull_area_m2": round(area_mm2 / 1e6, 3),
            }
        )
    # Give both back.
    return rooms, dropped


def run() -> dict:
    """Read both zips and write scene and room tables. Return the stats."""
    # Output folder (gitignored).
    out = processed_dir("structured3d")
    # Annotation zip.
    annotation_zip = zipfile.ZipFile(raw_dir("structured3d") / "Structured3D_annotation_3d.zip")
    # Bbox zip.
    bbox_zip = zipfile.ZipFile(raw_dir("structured3d") / "Structured3D_bbox.zip")
    # Bbox member names for counts.
    bbox_names = bbox_zip.namelist()
    # Instance render counts per scene, from names only.
    instance_renders: Counter = Counter()
    # Scenes that have a bbox_3d.json.
    bbox_scenes: set[int] = set()
    # One pass over the bbox member names.
    for name in bbox_names:
        # Scene number in the path.
        match = SCENE.match(name)
        # Skip the root folder.
        if not match:
            # Next name.
            continue
        # Scene number.
        number = int(match.group(1))
        # Count instance renders (perspective instance masks only).
        if name.endswith("/perspective/full/instance.png") or (
            "/perspective/full/" in name and name.endswith("/instance.png")
        ):
            # Tally.
            instance_renders[number] += 1
        # Record scenes with bbox files.
        if name.endswith("/bbox_3d.json"):
            # Remember the scene.
            bbox_scenes.add(number)
    # Scene rows and room rows.
    scenes: list[dict] = []
    # Room rows.
    room_rows: list[dict] = []
    # Drop reasons.
    dropped: Counter = Counter()
    # Scene json members.
    members = sorted(n for n in annotation_zip.namelist() if n.endswith("/annotation_3d.json"))
    # Process every scene.
    for member in members:
        # Scene number.
        number = int(SCENE.match(member).group(1))
        # Parse the annotation.
        try:
            # JSON load.
            annotation = json.loads(annotation_zip.read(member))
        except ValueError:
            # Corrupt JSON.
            dropped["scene_bad_json"] += 1
            # Next scene.
            continue
        # Plane type counts.
        plane_types = Counter(p["type"] for p in annotation["planes"])
        # Room rows for the scene.
        rooms, reasons = room_dimensions(annotation)
        # Add to the tally.
        dropped.update(reasons)
        # Bbox count and sizes, if the scene has a bbox file.
        n_boxes = None
        # Only when present.
        if number in bbox_scenes:
            # Load the file.
            n_boxes = len(
                json.loads(bbox_zip.read(f"Structured3D/scene_{number:05d}/bbox_3d.json"))
            )
        # Scene row.
        scenes.append(
            {
                "scene": f"scene_{number:05d}",
                "split": official_split(number),
                "n_rooms": len(rooms),
                "n_planes": len(annotation["planes"]),
                "n_walls": plane_types.get("wall", 0),
                "n_doors": sum(1 for s in annotation["semantics"] if s["type"] == "door"),
                "n_windows": sum(1 for s in annotation["semantics"] if s["type"] == "window"),
                "n_bbox_3d": n_boxes,
                "n_perspective_instance_masks": instance_renders.get(number, 0),
                "has_perspective_rgb": False,
                "has_depth": False,
                "complete_for_photo_or_depth_check": False,
            }
        )
        # Attach the scene to each of its rooms.
        for room in rooms:
            # Room row with the scene id and split.
            room_rows.append(
                {"scene": f"scene_{number:05d}", "split": official_split(number), **room}
            )
    # Tables.
    write_jsonl(out / "scenes.jsonl", scenes)
    # Room table.
    write_jsonl(out / "rooms.jsonl", room_rows)
    # Area statistics.
    areas = np.array([r["hull_area_m2"] for r in room_rows]) if room_rows else np.zeros(1)
    # Stats for the report.
    stats = {
        "scenes_in_annotation_zip": len(members),
        "scenes_exported": len(scenes),
        "scenes_with_bbox_3d": len(bbox_scenes),
        "scenes_without_bbox_3d": len(scenes)
        - sum(1 for s in scenes if s["n_bbox_3d"] is not None),
        "split_scenes": histogram([s["split"] for s in scenes]),
        "rooms_exported": len(room_rows),
        "rooms_dropped_by_reason": dict(sorted(dropped.items())),
        "room_type_histogram": histogram([r["room_type"] for r in room_rows]),
        "room_split_histogram": histogram([r["split"] for r in room_rows]),
        "hull_area_m2_percentiles": {
            str(q): round(float(np.percentile(areas, q)), 2) for q in (5, 25, 50, 75, 95)
        },
        "perspective_instance_masks_in_bbox_zip": sum(instance_renders.values()),
        "scenes_with_perspective_rgb": 0,
        "scenes_with_depth": 0,
        "scenes_complete_for_photo_or_depth_check": 0,
        "note": (
            "Perspective RGB and depth zips are not on disk. Phase 7b cannot run Structured3D "
            "photo or depth checks until perspective parts are added."
        ),
    }
    # Persist the stats.
    write_json(cleaning_dir() / "structured3d_summary.json", stats)
    # Give the stats back.
    return stats
