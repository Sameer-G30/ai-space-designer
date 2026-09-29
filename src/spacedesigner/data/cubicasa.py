"""Parse CubiCasa5K SVGs into wall/door/window/room polygons and rasterized masks."""

# Annotations on Python 3.11.
from __future__ import annotations

# Numbers inside SVG attributes.
import re

# Safe-enough XML parser for a trusted local research archive.
import xml.etree.ElementTree as ET

# Reads plans straight from the zip.
import zipfile

# Tallies.
from collections import Counter

# Array math.
import numpy as np

# Polygon rasterizer.
from PIL import Image, ImageDraw

# Shared helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    histogram,
    processed_dir,
    raw_dir,
    require_free_space,
    write_json,
    write_jsonl,
)

# SVG namespace prefix used by every tag.
SVG_NS = "{http://www.w3.org/2000/svg}"

# Floating point numbers, with optional sign and exponent.
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# Structure classes drawn into the structure mask.
STRUCTURE_IDS = {"Wall": 1, "Door": 2, "Window": 3}

# Polygons smaller than this many square SVG units are degenerate.
MIN_AREA = 1.0

# Longest raster side in pixels.
MAX_SIDE = 2048

# A plan with more than this share of dropped polygons is malformed.
MAX_DROPPED_SHARE = 0.5


def parse_transform(text: str | None) -> np.ndarray:
    """Return the 3x3 matrix for an SVG transform="matrix(a,b,c,d,e,f)" (identity otherwise)."""
    # No transform means identity.
    if not text or "matrix" not in text:
        # Identity matrix.
        return np.eye(3)
    # Six numbers a..f.
    a, b, c, d, e, f = (float(v) for v in NUMBER.findall(text)[:6])
    # Homogeneous matrix.
    return np.array([[a, c, e], [b, d, f], [0.0, 0.0, 1.0]])


def parse_points(text: str, matrix: np.ndarray) -> np.ndarray:
    """Parse a polygon points attribute and apply matrix. Returns an (N, 2) float array."""
    # All numbers in order: x1 y1 x2 y2 ...
    values = [float(v) for v in NUMBER.findall(text or "")]
    # Odd counts cannot be coordinates.
    if len(values) % 2:
        # Signal a malformed polygon.
        return np.zeros((0, 2))
    # Pair them up.
    pts = np.array(values, dtype=float).reshape(-1, 2)
    # Nothing to transform.
    if len(pts) == 0:
        # Empty polygon.
        return pts
    # Homogeneous coordinates.
    homogeneous = np.hstack([pts, np.ones((len(pts), 1))])
    # Apply the matrix and drop the last column.
    return (homogeneous @ matrix.T)[:, :2]


def polygon_area(pts: np.ndarray) -> float:
    """Return the absolute shoelace area of a polygon."""
    # Fewer than three points has no area.
    if len(pts) < 3:
        # Zero area.
        return 0.0
    # Shoelace formula.
    x, y = pts[:, 0], pts[:, 1]
    # Half the absolute cross-sum.
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def parse_plan(svg: bytes) -> tuple[dict | None, Counter]:
    """Parse one model.svg. Returns (plan or None, drop-reason counter).

    plan = {"width", "height", "floors": {floor_number: {"walls", "doors", "windows",
    "rooms": [(room_type, full_class, points)]}}} with points as lists of [x, y].
    """
    # Drop reasons for polygons and for the plan.
    dropped: Counter = Counter()
    # Parse the XML.
    try:
        # Root <svg> element.
        root = ET.fromstring(svg)
    except ET.ParseError:
        # Broken XML.
        dropped["plan_xml_error"] += 1
        # No plan.
        return None, dropped
    # Canvas size from the viewBox, falling back to width/height.
    box = NUMBER.findall(root.get("viewBox", ""))
    # Prefer the viewBox.
    if len(box) == 4:
        # Width and height are the last two numbers.
        width, height = float(box[2]), float(box[3])
    else:
        # Fall back to attributes.
        width = float((NUMBER.findall(root.get("width", "")) or ["0"])[0])
        # Height likewise.
        height = float((NUMBER.findall(root.get("height", "")) or ["0"])[0])
    # A plan needs a real canvas.
    if width <= 0 or height <= 0:
        # Count it.
        dropped["plan_bad_canvas"] += 1
        # No plan.
        return None, dropped
    # Floors keyed by number.
    floors: dict[int, dict] = {}

    def floor_of(number: int) -> dict:
        """Return (creating) the container for one floor."""
        # Create on first use.
        return floors.setdefault(number, {"walls": [], "doors": [], "windows": [], "rooms": []})

    def visit(node: ET.Element, matrix: np.ndarray, floor: int) -> None:
        """Walk the tree, accumulating transforms, and collect the polygons we care about."""
        # Each child group.
        for child in node:
            # Only groups matter.
            if child.tag != f"{SVG_NS}g":
                # Skip other tags.
                continue
            # Class attribute like 'Wall External' or 'Space Bedroom'.
            classes = child.get("class", "").split()
            # Compose this group's transform.
            local = matrix @ parse_transform(child.get("transform"))
            # First class word decides what the group is.
            kind = classes[0] if classes else ""
            # Floor groups carry the floor number in their id.
            if kind == "Floorplan":
                # Ids look like Floor-1.
                number = int((NUMBER.findall(child.get("id", "Floor-1")) or ["1"])[0])
                # Recurse with the new floor.
                visit(child, local, number)
                # Next child.
                continue
            # Wall, Door, Window and Space hold one direct polygon.
            if kind in STRUCTURE_IDS or kind == "Space":
                # First direct <polygon> child.
                polygon = next((c for c in child if c.tag == f"{SVG_NS}polygon"), None)
                # No polygon at all.
                if polygon is None:
                    # Count it.
                    dropped[f"{kind.lower()}_no_polygon"] += 1
                    # Next child.
                    continue
                # Points in canvas coordinates.
                pts = parse_points(polygon.get("points", ""), local)
                # Fewer than three points, or NaN.
                if len(pts) < 3 or not np.all(np.isfinite(pts)):
                    # Count it.
                    dropped[f"{kind.lower()}_bad_points"] += 1
                    # Next child.
                    continue
                # Degenerate area.
                if polygon_area(pts) < MIN_AREA:
                    # Count it.
                    dropped[f"{kind.lower()}_degenerate"] += 1
                    # Next child.
                    continue
                # Completely outside the canvas.
                if (
                    pts[:, 0].max() < 0
                    or pts[:, 1].max() < 0
                    or pts[:, 0].min() > width
                    or pts[:, 1].min() > height
                ):
                    # Count it.
                    dropped[f"{kind.lower()}_outside_canvas"] += 1
                    # Next child.
                    continue
                # Container for the current floor.
                target = floor_of(floor)
                # Save points as plain lists for JSON.
                listed = np.round(pts, 2).tolist()
                # Walls, doors, windows go to their list.
                if kind == "Wall":
                    # Add the wall.
                    target["walls"].append(listed)
                elif kind == "Door":
                    # Add the door.
                    target["doors"].append(listed)
                elif kind == "Window":
                    # Add the window.
                    target["windows"].append(listed)
                else:
                    # Room type is the word after 'Space'.
                    room = classes[1] if len(classes) > 1 else "Undefined"
                    # Keep the full class string too.
                    target["rooms"].append([room, " ".join(classes[1:]), listed])
                # Doors and windows are nested inside their wall group, so walk into walls only.
                if kind == "Wall":
                    # Recurse to find the nested Door and Window groups.
                    visit(child, local, floor)
                # Rooms, doors and windows are leaves.
                continue
            # Any other group: keep walking.
            visit(child, local, floor)

    # Start from the root with identity and floor 1.
    visit(root, np.eye(3), 1)
    # Empty plans are malformed.
    kept = sum(
        len(f["walls"]) + len(f["doors"]) + len(f["windows"]) + len(f["rooms"])
        for f in floors.values()
    )
    # Number of polygons that were dropped.
    lost = sum(v for k, v in dropped.items() if not k.startswith("plan_"))
    # No walls or no rooms in any floor means an unusable plan.
    if not any(f["walls"] for f in floors.values()):
        # Count it.
        dropped["plan_no_walls"] += 1
        # No plan.
        return None, dropped
    # Rooms are needed too.
    if not any(f["rooms"] for f in floors.values()):
        # Count it.
        dropped["plan_no_rooms"] += 1
        # No plan.
        return None, dropped
    # Too many dropped polygons means a corrupt plan.
    if kept + lost > 0 and lost / (kept + lost) > MAX_DROPPED_SHARE:
        # Count it.
        dropped["plan_mostly_invalid"] += 1
        # No plan.
        return None, dropped
    # Good plan.
    return {"width": width, "height": height, "floors": floors}, dropped


def rasterize(floor: dict, width: float, height: float, room_ids: dict[str, int]):
    """Return (structure_mask, room_mask) uint8 arrays for one floor."""
    # Scale so the longest side fits MAX_SIDE, never enlarging past 1:1.
    scale = min(1.0, MAX_SIDE / max(width, height))
    # Raster size in pixels.
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    # Room mask starts empty.
    rooms = Image.new("L", size, 0)
    # Structure mask starts empty.
    structure = Image.new("L", size, 0)
    # Drawing handles.
    draw_rooms, draw_structure = ImageDraw.Draw(rooms), ImageDraw.Draw(structure)
    # Rooms first, largest first so small rooms stay visible.
    for room, _, pts in sorted(floor["rooms"], key=lambda r: -polygon_area(np.array(r[2]))):
        # Scaled integer-free coordinates.
        draw_rooms.polygon([(x * scale, y * scale) for x, y in pts], fill=room_ids[room])
    # Then walls, doors, windows in that order so windows sit on top.
    for name, key in (("Wall", "walls"), ("Door", "doors"), ("Window", "windows")):
        # Every polygon of this kind.
        for pts in floor[key]:
            # Fill with the structure id.
            draw_structure.polygon(
                [(x * scale, y * scale) for x, y in pts], fill=STRUCTURE_IDS[name]
            )
    # Arrays for the caller.
    return np.asarray(structure), np.asarray(rooms)


def official_splits(archive: zipfile.ZipFile) -> dict[str, str]:
    """Read train.txt / val.txt / test.txt into {'collection/number': split}."""
    # Result map.
    result: dict[str, str] = {}
    # Three official files.
    for split in ("train", "val", "test"):
        # Lines look like /high_quality_architectural/6044/.
        for line in archive.read(f"cubicasa5k/{split}.txt").decode("utf-8").split():
            # Strip the slashes.
            result[line.strip("/")] = split
    # Give the map back.
    return result


def run() -> dict:
    """Parse and rasterize every plan. Return the stats."""
    # Output folder (gitignored).
    out = processed_dir("cubicasa5k")
    # Masks and JSON are small; still check space.
    require_free_space(out, 2 * 1024**3)
    # Open the zip once.
    archive = zipfile.ZipFile(raw_dir("cubicasa5k") / "cubicasa5k.zip")
    # Official split map.
    splits = official_splits(archive)
    # Every model.svg member.
    members = sorted(n for n in archive.namelist() if n.endswith("/model.svg"))
    # Parsed plans by id.
    plans: dict[str, dict] = {}
    # Polygon and plan drop reasons.
    dropped: Counter = Counter()
    # Plans dropped, by id, for the report.
    dropped_plans: dict[str, str] = {}
    # Room class frequency for the vocabulary.
    room_counts: Counter = Counter()
    # Pass 1: parse.
    for member in members:
        # 'cubicasa5k/high_quality/1245/model.svg' -> 'high_quality/1245'.
        key = member[len("cubicasa5k/") : -len("/model.svg")]
        # Parse.
        plan, reasons = parse_plan(archive.read(member))
        # Add to the tally.
        dropped.update(reasons)
        # Malformed plan.
        if plan is None:
            # Remember why.
            dropped_plans[key] = next(k for k in reasons if k.startswith("plan_"))
            # Next plan.
            continue
        # Plans outside the official lists cannot be assigned a split.
        if key not in splits:
            # Count it.
            dropped["plan_not_in_official_split"] += 1
            # Remember why.
            dropped_plans[key] = "plan_not_in_official_split"
            # Next plan.
            continue
        # Keep the plan.
        plans[key] = plan
        # Count room classes.
        for floor in plan["floors"].values():
            # Every room polygon.
            for room, _, _ in floor["rooms"]:
                # Tally the first-word class.
                room_counts[room] += 1
    # Room ids: most frequent first, starting at 1 (0 is background).
    room_ids = {room: i + 1 for i, (room, _) in enumerate(room_counts.most_common())}
    # Manifest rows.
    rows: list[dict] = []
    # Pass 2: write polygons and masks.
    for key, plan in plans.items():
        # Split from the official lists.
        split = splits[key]
        # Flat id.
        plan_id = key.replace("/", "_")
        # Folders.
        for kind in ("polygons", "masks"):
            # Create each one.
            (out / split / kind).mkdir(parents=True, exist_ok=True)
        # Save polygons.
        write_json(out / split / "polygons" / f"{plan_id}.json", plan)
        # One mask pair per floor.
        for number, floor in sorted(plan["floors"].items()):
            # Rasterize.
            structure, room_mask = rasterize(floor, plan["width"], plan["height"], room_ids)
            # Save the structure mask.
            Image.fromarray(structure).save(
                out / split / "masks" / f"{plan_id}_F{number}_structure.png"
            )
            # Save the room mask.
            Image.fromarray(room_mask).save(
                out / split / "masks" / f"{plan_id}_F{number}_rooms.png"
            )
        # One manifest row per plan.
        rows.append(
            {
                "id": plan_id,
                "source_key": key,
                "collection": key.split("/")[0],
                "split": split,
                "width": plan["width"],
                "height": plan["height"],
                "n_floors": len(plan["floors"]),
                "n_walls": sum(len(f["walls"]) for f in plan["floors"].values()),
                "n_doors": sum(len(f["doors"]) for f in plan["floors"].values()),
                "n_windows": sum(len(f["windows"]) for f in plan["floors"].values()),
                "n_rooms": sum(len(f["rooms"]) for f in plan["floors"].values()),
            }
        )
    # Manifest and vocabulary.
    write_jsonl(out / "manifest.jsonl", rows)
    # Room vocabulary used by the room masks.
    write_json(out / "room_classes.json", {"background": 0, **room_ids})
    # Stats for the report.
    stats = {
        "svg_plans_in_zip": len(members),
        "official_split_entries": len(splits),
        "plans_kept": len(rows),
        "plans_dropped": len(dropped_plans),
        "plans_dropped_by_reason": histogram(list(dropped_plans.values())),
        "polygons_dropped_by_reason": dict(
            sorted((k, v) for k, v in dropped.items() if not k.startswith("plan_"))
        ),
        "split_plans": histogram([r["split"] for r in rows]),
        "collection_plans": histogram([r["collection"] for r in rows]),
        "floors_total": sum(r["n_floors"] for r in rows),
        "walls_total": sum(r["n_walls"] for r in rows),
        "doors_total": sum(r["n_doors"] for r in rows),
        "windows_total": sum(r["n_windows"] for r in rows),
        "rooms_total": sum(r["n_rooms"] for r in rows),
        "room_class_histogram": dict(room_counts.most_common()),
        "license": "CC BY-NC-SA 4.0 (Zenodo id cc-by-nc-sa-4.0)",
    }
    # Persist the stats.
    write_json(cleaning_dir() / "cubicasa_summary.json", stats)
    # Give the stats back.
    return stats
