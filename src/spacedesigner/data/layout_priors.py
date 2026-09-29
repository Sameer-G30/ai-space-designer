"""Mine layout priors from data already on disk: SUN RGB-D 3D boxes, Structured3D, CubiCasa5K.

No 3D-FRONT is used. Every published prior carries its sample count and the minimum count it had
to reach; anything below the minimum is omitted and listed in `omitted`.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Parses the SUN annotation files.
import json

# Reads members without unpacking.
import zipfile

# Tallies.
from collections import Counter, defaultdict

# Array math.
import numpy as np

# Paths and JSONL helpers, plus the shared taxonomy.
from spacedesigner.data.common import (
    cleaning_dir,
    processed_dir,
    raw_dir,
    read_jsonl,
    write_json,
)
from spacedesigner.data.taxonomy import ROOM_TYPES, map_furniture, normalize_label

# Minimum samples before any single-class statistic is published.
MIN_CLASS_SAMPLES = 30

# Minimum samples before a per-room-type statistic is published.
MIN_ROOM_SAMPLES = 30

# Minimum scenes in which the "given A" class appears before a pair statistic is published.
MIN_PAIR_SCENES = 20

# Rooms with fewer mapped objects than this are dropped (ATISS-style "too few objects").
MIN_OBJECTS = 3

# Rooms with more mapped objects than this are dropped (ATISS-style "too many objects").
MAX_OBJECTS = 40

# Object edges outside this range in metres are not physical furniture.
MIN_EDGE_M, MAX_EDGE_M = 0.05, 4.0

# Two boxes overlapping by more than this 3D IoU are a heavy overlap.
MAX_IOU = 0.5

# Structured3D room names to room types. Names that are not listed are dropped as unmapped.
S3D_ROOM_TO_TYPE: dict[str, str] = {
    "bedroom": "bedroom",  # 5817 rooms
    "living room": "living_room",  # 3081 rooms
    "kitchen": "kitchen",  # 2287 rooms
    "bathroom": "bathroom",  # 3611 rooms
    "dining room": "dining_room",  # 165 rooms
    "study": "home_office",  # 699 rooms
    "office": "home_office",  # 3 rooms
    "corridor": "corridor",  # 307 rooms
    "balcony": "balcony",  # 2639 rooms
    "laundry room": "utility_room",  # 1 room
}

# CubiCasa5K room classes to room types.
CUBICASA_ROOM_TO_TYPE: dict[str, str] = {
    "Bedroom": "bedroom",  # bedrooms
    "LivingRoom": "living_room",  # living rooms
    "Kitchen": "kitchen",  # kitchens
    "Bath": "bathroom",  # bathrooms
    "Dining": "dining_room",  # dining rooms
    "Office": "home_office",  # offices
    "Closet": "closet",  # closets
    "Entry": "entrance_hall",  # entries
    "Basement": "basement",  # basements
    "Utility": "utility_room",  # utility rooms
    "Storage": "utility_room",  # storage rooms
}


def polygon_points(polygon: dict) -> np.ndarray:
    """Return a (n, 2) array of floor points [X, Z] from one SUN polygon entry."""
    # X and Z are the two horizontal axes; Y is vertical in SUN RGB-D.
    return np.column_stack([np.asarray(polygon["X"], float), np.asarray(polygon["Z"], float)])


def point_in_polygon(point: np.ndarray, poly: np.ndarray) -> bool:
    """Ray casting test: True when the point lies inside the polygon."""
    # Start outside.
    inside = False
    # Walk every edge with the previous vertex.
    for i in range(len(poly)):
        # Edge from vertex j to vertex i.
        x1, y1 = poly[i - 1]
        # Second endpoint.
        x2, y2 = poly[i]
        # Count a crossing when the horizontal ray from the point cuts the edge.
        if (y1 > point[1]) != (y2 > point[1]):
            # X where the edge crosses the ray.
            cross = (x2 - x1) * (point[1] - y1) / (y2 - y1) + x1
            # Flip the state on each crossing to the right of the point.
            if point[0] < cross:
                # Toggle.
                inside = not inside
    # Final parity.
    return inside


def distance_to_polygon_edges(point: np.ndarray, poly: np.ndarray) -> float:
    """Shortest distance from a point to any edge of a polygon."""
    # Best distance so far.
    best = float("inf")
    # Check every edge.
    for i in range(len(poly)):
        # Edge start.
        a = poly[i - 1]
        # Edge end.
        b = poly[i]
        # Edge vector.
        ab = b - a
        # Squared length, guarding zero-length edges.
        denom = float(ab @ ab)
        # Projection parameter clamped to the segment.
        t = 0.0 if denom == 0 else float(np.clip(((point - a) @ ab) / denom, 0.0, 1.0))
        # Distance to the closest point on the segment.
        best = min(best, float(np.linalg.norm(point - (a + t * ab))))
    # Give the best back.
    return best


def box_from_object(obj: dict) -> dict | None:
    """Turn one SUN 3D object into a measured box, or None when it is not a 4-point rectangle."""
    # Objects can carry several polygons; use the first.
    polygons = obj.get("polygon") or []
    # No polygon at all.
    if not polygons:
        # Nothing to measure.
        return None
    # The first polygon holds the footprint and the vertical extent.
    polygon = polygons[0]
    # Floor points of the footprint.
    pts = polygon_points(polygon)
    # A box footprint has exactly four corners.
    if len(pts) != 4 or not np.all(np.isfinite(pts)):
        # Not a box.
        return None
    # The two edge lengths of the rectangle.
    e1 = float(np.linalg.norm(pts[1] - pts[0]))
    # Second edge.
    e2 = float(np.linalg.norm(pts[2] - pts[1]))
    # Vertical extent in metres.
    top, bottom = float(polygon["Ymin"]), float(polygon["Ymax"])
    # Give back the measured box.
    return {
        "name": obj["name"],
        "corners": pts,
        "centre": pts.mean(axis=0),
        "length": max(e1, e2),
        "width": min(e1, e2),
        "height": bottom - top,
        "y_min": top,
        "y_max": bottom,
    }


def box_iou_3d(a: dict, b: dict) -> float:
    """IoU of the axis-aligned 3D extents of two boxes (a cheap heavy-overlap test)."""
    # Horizontal extents.
    a_lo, a_hi = a["corners"].min(axis=0), a["corners"].max(axis=0)
    # Second box.
    b_lo, b_hi = b["corners"].min(axis=0), b["corners"].max(axis=0)
    # Horizontal overlap per axis.
    overlap_xz = np.clip(np.minimum(a_hi, b_hi) - np.maximum(a_lo, b_lo), 0, None)
    # Vertical overlap.
    overlap_y = max(0.0, min(a["y_max"], b["y_max"]) - max(a["y_min"], b["y_min"]))
    # Intersection volume.
    inter = float(overlap_xz[0] * overlap_xz[1] * overlap_y)
    # Volumes of the two extents.
    vol_a = float(np.prod(a_hi - a_lo) * a["height"])
    # Second volume.
    vol_b = float(np.prod(b_hi - b_lo) * b["height"])
    # Union, guarding an empty box.
    union = vol_a + vol_b - inter
    # IoU.
    return inter / union if union > 0 else 0.0


def clean_scene_boxes(objects: list[dict], layout: np.ndarray | None) -> tuple[list[dict], Counter]:
    """Apply the ATISS-style object filters to one image's 3D boxes. Returns (kept, reasons)."""
    # Reasons for dropped objects.
    reasons: Counter = Counter()
    # Boxes that pass the per-object checks.
    boxes: list[dict] = []
    # Check each object.
    for obj in objects:
        # Some annotation entries are null placeholders.
        if not obj:
            # Count it.
            reasons["null_entry"] += 1
            # Next object.
            continue
        # Map the raw label to the taxonomy; unmapped objects are not layout furniture.
        category = map_furniture(obj.get("name", ""))
        # Not one of the 26 classes.
        if category is None:
            # Count it.
            reasons["unmapped_class"] += 1
            # Next object.
            continue
        # Build the measured box.
        box = box_from_object(obj)
        # Not a rectangle footprint.
        if box is None:
            # Count it.
            reasons["not_a_box_footprint"] += 1
            # Next object.
            continue
        # Tag with the class.
        box["category"] = category
        # Edges must be positive and physical.
        edges = (box["length"], box["width"], box["height"])
        # Non-finite or out-of-range edges.
        if not all(np.isfinite(e) and MIN_EDGE_M <= e <= MAX_EDGE_M for e in edges):
            # Count it.
            reasons["implausible_size"] += 1
            # Next object.
            continue
        # With a layout polygon, the object centre has to be on the floor.
        if layout is not None and not point_in_polygon(box["centre"], layout):
            # Count it.
            reasons["outside_floor"] += 1
            # Next object.
            continue
        # Passed.
        boxes.append(box)
    # Heavy overlap: keep the larger box of any pair above the IoU limit.
    kept: list[dict] = []
    # Largest first so the small duplicate is the one dropped.
    for box in sorted(boxes, key=lambda b: -(b["length"] * b["width"] * b["height"])):
        # Compare with the boxes already kept.
        if any(box_iou_3d(box, other) > MAX_IOU for other in kept):
            # Count it.
            reasons["heavy_overlap"] += 1
            # Next box.
            continue
        # Keep it.
        kept.append(box)
    # Give both back.
    return kept, reasons


def percentiles(values: list[float]) -> dict[str, float]:
    """Return p05, p25, p50, p75, and p95 rounded to 3 decimals."""
    # Compute the five quantiles in one call.
    q = np.percentile(np.asarray(values, float), [5, 25, 50, 75, 95])
    # Label them.
    return {k: round(float(v), 3) for k, v in zip(("p05", "p25", "p50", "p75", "p95"), q)}


def mine_sun_rgbd() -> dict:
    """Read the SUN RGB-D 3D boxes and layouts and return the object-level priors."""
    # Cleaned manifest tells us which images survived Phase 2a and their room type.
    manifest = read_jsonl(processed_dir("sun_rgbd") / "manifest.jsonl")
    # Open the zip once.
    archive = zipfile.ZipFile(raw_dir("sun_rgbd") / "SUNRGBD.zip")
    # Member names for existence checks.
    names = set(archive.namelist())
    # Drop reasons for whole rooms (images).
    room_drops: Counter = Counter()
    # Drop reasons for single objects.
    object_drops: Counter = Counter()
    # Per-class measured sizes.
    sizes: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    # Per-class wall distances (metres), object centre to the nearest layout edge.
    wall: dict[str, list[float]] = defaultdict(list)
    # Per room type: number of kept rooms.
    room_count: Counter = Counter()
    # Per room type, per class: counts per kept room.
    per_room: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    # Per room type, per class pair: number of rooms where both appear.
    pair_rooms: dict[str, Counter] = defaultdict(Counter)
    # Per room type, per class: rooms where it appears.
    class_rooms: dict[str, Counter] = defaultdict(Counter)
    # Kept objects total.
    kept_objects = 0
    # Walk every cleaned image.
    for record in manifest:
        # Only images with a mapped room type give room-level priors.
        room_type = record.get("room_type")
        # Folder inside the zip.
        prefix = f"{record['sequence']}/"
        # 3D annotation members.
        final_name = f"{prefix}annotation3Dfinal/index.json"
        # Layout member.
        layout_name = f"{prefix}annotation3Dlayout/index.json"
        # No 3D annotation for this image.
        if final_name not in names:
            # Count it.
            room_drops["no_3d_annotation"] += 1
            # Next image.
            continue
        # Parse the object annotation.
        try:
            # JSON load.
            objects = json.loads(archive.read(final_name)).get("objects", [])
        except ValueError:
            # Corrupt JSON.
            room_drops["bad_json"] += 1
            # Next image.
            continue
        # Layout polygon, when the layout file has one.
        layout = None
        # Only when the file exists.
        if layout_name in names:
            # Try to parse it.
            try:
                # JSON load.
                layout_objects = json.loads(archive.read(layout_name)).get("objects", [])
            except ValueError:
                # Treat as no layout.
                layout_objects = []
            # A room polygon has at least three floor points.
            for item in layout_objects:
                # The layout object is named room.
                if item and item.get("name") == "room" and item.get("polygon"):
                    # Floor outline.
                    outline = polygon_points(item["polygon"][0])
                    # Need a real polygon.
                    if len(outline) >= 3 and np.all(np.isfinite(outline)):
                        # Keep it.
                        layout = outline
                    # First room polygon only.
                    break
        # Filter the objects.
        kept, reasons = clean_scene_boxes(objects, layout)
        # Add object reasons to the tally.
        object_drops.update(reasons)
        # Too few objects.
        if len(kept) < MIN_OBJECTS:
            # Count it.
            room_drops["too_few_objects"] += 1
            # Next image.
            continue
        # Too many objects.
        if len(kept) > MAX_OBJECTS:
            # Count it.
            room_drops["too_many_objects"] += 1
            # Next image.
            continue
        # Sizes count for every kept room, whether or not the scene has a room type.
        for box in kept:
            # Record the measured box.
            sizes[box["category"]].append((box["length"], box["width"], box["height"]))
            # Wall distance needs both a footprint and a layout wall.
            if layout is not None:
                # Centre-to-wall distance.
                wall[box["category"]].append(distance_to_polygon_edges(box["centre"], layout))
        # Count kept objects.
        kept_objects += len(kept)
        # Room-type priors need a mapped room type.
        if room_type is None:
            # Count it.
            room_drops["no_mapped_room_type"] += 1
            # Next image.
            continue
        # One more kept room of this type.
        room_count[room_type] += 1
        # Instances per class in this room.
        counts = Counter(box["category"] for box in kept)
        # Record the counts and co-occurrence.
        for category, n in counts.items():
            # Per-room count list (only for rooms where the class appears).
            per_room[room_type][category].append(n)
            # Room where the class appears.
            class_rooms[room_type][category] += 1
        # Every ordered pair of distinct classes in the room.
        for a in counts:
            # Second class.
            for b in counts:
                # Distinct classes only.
                if a != b:
                    # One more room with both.
                    pair_rooms[room_type][(a, b)] += 1
    # Assemble the published priors with minimum sample counts.
    return assemble_sun_priors(
        sizes,
        wall,
        room_count,
        per_room,
        pair_rooms,
        class_rooms,
        room_drops,
        object_drops,
        len(manifest),
        kept_objects,
    )


def assemble_sun_priors(
    sizes,
    wall,
    room_count,
    per_room,
    pair_rooms,
    class_rooms,
    room_drops,
    object_drops,
    n_images,
    kept_objects,
) -> dict:
    """Apply the minimum sample counts and split the results into published and omitted."""
    # Omitted priors with their reason.
    omitted: list[dict] = []
    # Published size priors.
    size_priors: dict[str, dict] = {}
    # Every taxonomy class is checked so the omissions are explicit.
    for category in sorted(set(sizes) | set(wall)):
        # Measured sizes of this class.
        rows = sizes.get(category, [])
        # Enough samples.
        if len(rows) >= MIN_CLASS_SAMPLES:
            # Arrays per axis.
            arr = np.asarray(rows, float)
            # Publish the percentiles of each edge.
            size_priors[category] = {
                "n": len(rows),
                "min_n": MIN_CLASS_SAMPLES,
                "length_m": percentiles(arr[:, 0].tolist()),
                "width_m": percentiles(arr[:, 1].tolist()),
                "height_m": percentiles(arr[:, 2].tolist()),
                "source": "SUNRGBD.zip annotation3Dfinal",
            }
        else:
            # Omit with the count.
            omitted.append(
                {
                    "prior": f"object_size:{category}",
                    "n": len(rows),
                    "min_n": MIN_CLASS_SAMPLES,
                    "missing": "SUNRGBD.zip annotation3Dfinal has too few boxes for this class",
                }
            )
    # Published wall-distance priors.
    wall_priors: dict[str, dict] = {}
    # Check each class with a wall distance.
    for category, values in sorted(wall.items()):
        # Enough samples.
        if len(values) >= MIN_CLASS_SAMPLES:
            # Publish percentiles.
            wall_priors[category] = {
                "n": len(values),
                "min_n": MIN_CLASS_SAMPLES,
                "centre_to_wall_m": percentiles(values),
                "source": "SUNRGBD.zip annotation3Dfinal + annotation3Dlayout (visible walls only)",
            }
        else:
            # Omit with the count.
            omitted.append(
                {
                    "prior": f"wall_distance:{category}",
                    "n": len(values),
                    "min_n": MIN_CLASS_SAMPLES,
                    "missing": "too few boxes with both a footprint and a layout wall",
                }
            )
    # Published co-occurrence priors per room type.
    cooccurrence: dict[str, dict] = {}
    # Check each room type.
    for room_type in ROOM_TYPES:
        # Kept rooms of this type.
        n_rooms = room_count.get(room_type, 0)
        # Not enough rooms.
        if n_rooms < MIN_ROOM_SAMPLES:
            # Omit with the count.
            omitted.append(
                {
                    "prior": f"cooccurrence:{room_type}",
                    "n": n_rooms,
                    "min_n": MIN_ROOM_SAMPLES,
                    "missing": "SUNRGBD.zip has too few 3D-annotated rooms of this type",
                }
            )
            # Next room type.
            continue
        # Presence probability and mean count per class.
        classes: dict[str, dict] = {}
        # Every class that appears in at least one room.
        for category, n_present in sorted(class_rooms[room_type].items()):
            # Counts where present.
            counts = per_room[room_type][category]
            # Record presence and mean count.
            classes[category] = {
                "rooms_with_class": n_present,
                "p_present": round(n_present / n_rooms, 4),
                "mean_count_when_present": round(float(np.mean(counts)), 3),
            }
        # Conditional probabilities P(b | a) where a has enough rooms.
        conditional: dict[str, dict[str, float]] = {}
        # Every class a.
        for a, n_a in sorted(class_rooms[room_type].items()):
            # Skip rare a.
            if n_a < MIN_PAIR_SCENES:
                # Next a.
                continue
            # P(b | a) for each partner.
            conditional[a] = {
                b: round(pair_rooms[room_type][(a, b)] / n_a, 4)
                for b in sorted(class_rooms[room_type])
                if b != a and pair_rooms[room_type][(a, b)] > 0
            }
        # Publish this room type.
        cooccurrence[room_type] = {
            "n_rooms": n_rooms,
            "min_n": MIN_ROOM_SAMPLES,
            "min_pair_rooms": MIN_PAIR_SCENES,
            "classes": classes,
            "p_b_given_a": conditional,
            "source": "SUNRGBD.zip annotation3Dfinal + scene.txt",
        }
    # Everything mined from SUN.
    return {
        "images_considered": n_images,
        "objects_kept": kept_objects,
        "room_drops": dict(sorted(room_drops.items())),
        "object_drops": dict(sorted(object_drops.items())),
        "rooms_kept_by_type": dict(sorted(room_count.items())),
        "object_size": size_priors,
        "wall_distance": wall_priors,
        "cooccurrence": cooccurrence,
        "omitted": omitted,
    }


def mine_structured3d_rooms() -> dict:
    """Room-size distributions per room type from rooms.jsonl (exact dimensions in metres)."""
    # Rooms table from Phase 2a.
    rows = read_jsonl(processed_dir("structured3d") / "rooms.jsonl")
    # Drop reasons.
    drops: Counter = Counter()
    # Values by room type.
    by_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # Walk every room.
    for row in rows:
        # Map the name.
        room_type = S3D_ROOM_TO_TYPE.get(row["room_type"])
        # Names like undefined, garden, studio, store room are not in the taxonomy.
        if room_type is None:
            # Count it.
            drops[f"unmapped_room_type:{normalize_label(row['room_type'])}"] += 1
            # Next room.
            continue
        # Long and short bounding edges in metres.
        long_edge = max(row["width_mm"], row["length_mm"]) / 1000.0
        # Short edge.
        short_edge = min(row["width_mm"], row["length_mm"]) / 1000.0
        # Record the metrics.
        by_type[room_type]["area_m2"].append(float(row["hull_area_m2"]))
        # Long edge.
        by_type[room_type]["long_edge_m"].append(long_edge)
        # Short edge.
        by_type[room_type]["short_edge_m"].append(short_edge)
        # Aspect ratio.
        by_type[room_type]["aspect"].append(long_edge / short_edge)
        # Ceiling height.
        by_type[room_type]["height_m"].append(row["height_mm"] / 1000.0)
    # Published and omitted.
    published: dict[str, dict] = {}
    # Omitted list.
    omitted: list[dict] = []
    # Every room type in the taxonomy.
    for room_type in ROOM_TYPES:
        # Sample count.
        n = len(by_type[room_type]["area_m2"]) if room_type in by_type else 0
        # Too few samples.
        if n < MIN_ROOM_SAMPLES:
            # Omit with the count.
            omitted.append(
                {
                    "prior": f"room_size:{room_type}",
                    "n": n,
                    "min_n": MIN_ROOM_SAMPLES,
                    "missing": "Structured3D rooms.jsonl has no or too few rooms of this type",
                }
            )
            # Next type.
            continue
        # Publish percentiles of each metric.
        published[room_type] = {
            "n": n,
            "min_n": MIN_ROOM_SAMPLES,
            **{metric: percentiles(values) for metric, values in by_type[room_type].items()},
            "source": "datasets/processed/structured3d/rooms.jsonl (hull area is an upper bound)",
        }
    # Give it back.
    return {
        "rooms_considered": len(rows),
        "drops": dict(sorted(drops.items())),
        "room_size": published,
        "omitted": omitted,
    }


def mine_cubicasa_shapes() -> dict:
    """Dimensionless room shape priors from CubiCasa5K polygons (SVG units, no metre scale)."""
    # Every plan polygon file across the three splits.
    root = processed_dir("cubicasa5k")
    # Aspect ratios and area shares per room type.
    aspect: dict[str, list[float]] = defaultdict(list)
    # Area as a share of the plan canvas.
    share: dict[str, list[float]] = defaultdict(list)
    # Drop reasons.
    drops: Counter = Counter()
    # Walk the splits.
    for split in ("train", "val", "test"):
        # Each plan file.
        for path in sorted((root / split / "polygons").glob("*.json")):
            # Load the plan.
            plan = json.loads(path.read_text())
            # Canvas area for the share.
            canvas = float(plan["width"]) * float(plan["height"])
            # Every floor.
            for floor in plan["floors"].values():
                # Every room polygon.
                for room, _, points in floor["rooms"]:
                    # Map the class.
                    room_type = CUBICASA_ROOM_TO_TYPE.get(room)
                    # Not in the taxonomy.
                    if room_type is None:
                        # Count it.
                        drops[f"unmapped_room_class:{room}"] += 1
                        # Next room.
                        continue
                    # Points as an array.
                    pts = np.asarray(points, float)
                    # Need a real polygon.
                    if len(pts) < 3 or canvas <= 0:
                        # Count it.
                        drops["degenerate_polygon"] += 1
                        # Next room.
                        continue
                    # Bounding edges.
                    extent = pts.max(axis=0) - pts.min(axis=0)
                    # A zero edge has no aspect ratio.
                    if extent.min() <= 0:
                        # Count it.
                        drops["degenerate_polygon"] += 1
                        # Next room.
                        continue
                    # Shoelace area.
                    area = 0.5 * abs(
                        float(
                            np.dot(pts[:, 0], np.roll(pts[:, 1], -1))
                            - np.dot(pts[:, 1], np.roll(pts[:, 0], -1))
                        )
                    )
                    # Record both metrics.
                    aspect[room_type].append(float(extent.max() / extent.min()))
                    # Area share.
                    share[room_type].append(area / canvas)
    # Publish with minimum counts.
    published: dict[str, dict] = {}
    # Omitted list.
    omitted: list[dict] = []
    # Every room type.
    for room_type in ROOM_TYPES:
        # Sample count.
        n = len(aspect.get(room_type, []))
        # Too few samples.
        if n < MIN_ROOM_SAMPLES:
            # Omit with the count.
            omitted.append(
                {
                    "prior": f"room_shape:{room_type}",
                    "n": n,
                    "min_n": MIN_ROOM_SAMPLES,
                    "missing": "no mapped CubiCasa5K room class for this type",
                }
            )
            # Next type.
            continue
        # Publish.
        published[room_type] = {
            "n": n,
            "min_n": MIN_ROOM_SAMPLES,
            "aspect": percentiles(aspect[room_type]),
            "plan_area_share": percentiles(share[room_type]),
            "source": "datasets/processed/cubicasa5k/*/polygons (SVG units; not metres)",
        }
    # Give it back.
    return {"drops": dict(sorted(drops.items())), "room_shape": published, "omitted": omitted}


def run() -> dict:
    """Mine every prior, write layout_priors.json under cleaning/, and return it."""
    # Combine the three sources.
    priors = {
        "note": (
            "Mined only from data on disk. No 3D-FRONT numbers. Structured3D bbox_3d.json has no "
            "class labels, so Structured3D gives room sizes only. CubiCasa5K has no metre scale."
        ),
        "sun_rgbd": mine_sun_rgbd(),
        "structured3d": mine_structured3d_rooms(),
        "cubicasa5k": mine_cubicasa_shapes(),
    }
    # Persist under the tracked cleaning folder.
    write_json(cleaning_dir() / "layout_priors.json", priors)
    # Give it back.
    return priors
