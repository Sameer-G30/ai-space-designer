"""Synthetic generator v1: random rooms with matching requirement text and gold Requirement JSON.

Room sizes come from the Structured3D priors, object choices and sizes from the SUN RGB-D priors,
and budgets from the synthetic catalog prices. Every record is validated against the locked
SceneGraph and Requirement schemas before it is written.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Seeded randomness keeps the set reproducible.
import random

# Rectangle and percentile math.
import numpy as np

# Paths and helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    raw_dir,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)

# Locked schemas that gate every record.
from spacedesigner.schemas.requirement import ObjectiveWeights, Requirement
from spacedesigner.schemas.scene import SceneGraph

# Seed for the whole generator.
SEED = 20260930

# Room types that have both a Structured3D size prior and a SUN co-occurrence prior.
ROOM_TYPES_USED = ("bedroom", "living_room", "dining_room", "home_office")

# Largest floor area, in square metres, a synthetic room may have.
MAX_AREA_M2 = 60.0

# Smallest floor area, in square metres, a synthetic room may have.
MIN_AREA_M2 = 5.0

# Wall names in a fixed order.
WALLS = ("north", "east", "south", "west")

# Style words used in the requirement text and in the gold JSON.
STYLES = (
    "modern",
    "scandinavian",
    "minimalist",
    "industrial",
    "traditional",
    "rustic",
    "mid_century",
    "bohemian",
    "contemporary",
)

# Categories a requirement may ask for, per room type (all are taxonomy classes in the catalog).
WANTED: dict[str, tuple[str, ...]] = {
    "bedroom": ("bed", "nightstand", "dresser", "cabinet", "lamp", "desk", "chair", "mirror"),
    "living_room": ("sofa", "coffee_table", "tv_stand", "shelf", "armchair", "lamp", "side_table"),
    "dining_room": ("table", "chair", "cabinet", "lamp", "mirror"),
    "home_office": ("desk", "chair", "shelf", "cabinet", "lamp", "side_table"),
}


def quantile_sample(percentile_row: dict, rng: random.Random) -> float:
    """Draw one value by interpolating a published p05..p95 row at a random quantile."""
    # Random quantile between the published ends.
    u = rng.uniform(0.05, 0.95)
    # Published quantile positions and their values.
    xs = [0.05, 0.25, 0.50, 0.75, 0.95]
    # Values in the same order.
    ys = [percentile_row[k] for k in ("p05", "p25", "p50", "p75", "p95")]
    # Linear interpolation between neighbouring percentiles.
    return float(np.interp(u, xs, ys))


def sample_room(
    room_type: str, size_priors: dict, rng: random.Random
) -> tuple[float, float, float]:
    """Sample (length, width, height) in metres inside the plausible area limits."""
    # Structured3D prior for this room type.
    prior = size_priors[room_type]
    # Retry until the area limits hold.
    for _ in range(50):
        # Long edge.
        length = quantile_sample(prior["long_edge_m"], rng)
        # Short edge, never longer than the long edge.
        width = min(quantile_sample(prior["short_edge_m"], rng), length)
        # Area check.
        if MIN_AREA_M2 <= length * width <= MAX_AREA_M2:
            # Ceiling height from the prior, clipped to a sane range.
            height = float(np.clip(quantile_sample(prior["height_m"], rng), 2.4, 3.6))
            # Done.
            return round(length, 2), round(width, 2), round(height, 2)
    # Fall back to the median room, which always passes.
    return (round(prior["long_edge_m"]["p50"], 2), round(prior["short_edge_m"]["p50"], 2), 2.8)


def sample_openings(length: float, width: float, rng: random.Random) -> list[dict]:
    """One door and zero to three windows on the four walls, kept inside each wall's length."""
    # Wall lengths: north and south run along the length, east and west along the width.
    wall_length = {"north": length, "south": length, "east": width, "west": width}
    # Result list.
    openings: list[dict] = []
    # The door goes on a random wall.
    door_wall = rng.choice(WALLS)
    # Door width in metres.
    door_width = 0.9
    # Position is the distance from the wall start to the opening start.
    openings.append(
        {
            "type": "door",
            "wall": door_wall,
            "width": door_width,
            "position": round(rng.uniform(0.2, wall_length[door_wall] - door_width - 0.2), 2),
        }
    )
    # Zero to three windows.
    for _ in range(rng.randint(0, 3)):
        # Any wall, including the door's wall.
        wall = rng.choice(WALLS)
        # Window width, capped by the wall.
        window_width = round(min(rng.uniform(0.8, 1.8), wall_length[wall] - 0.4), 2)
        # Skip walls that are too short for a window.
        if window_width < 0.5:
            # Next window.
            continue
        # Add the window.
        openings.append(
            {
                "type": "window",
                "wall": wall,
                "width": window_width,
                "position": round(rng.uniform(0.2, wall_length[wall] - window_width - 0.2), 2),
            }
        )
    # Give them back.
    return openings


def overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """True when two (x0, y0, x1, y1) rectangles overlap."""
    # Separated on x or y means no overlap.
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def sample_objects(
    room_type: str, length: float, width: float, cooc: dict, sizes: dict, rng: random.Random
) -> list[dict]:
    """Sample existing objects using SUN presence rates and sizes; place them without overlap."""
    # Presence prior for this room type.
    classes = cooc[room_type]["classes"]
    # Placed rectangles for the overlap test.
    placed: list[tuple[float, float, float, float]] = []
    # Output objects.
    objects: list[dict] = []
    # Walk classes with a published size prior, most common first.
    for category, info in sorted(classes.items(), key=lambda kv: -kv[1]["p_present"]):
        # Skip classes with no measured size.
        if category not in sizes:
            # Next class.
            continue
        # Present with the measured probability.
        if rng.random() > info["p_present"]:
            # Absent in this room.
            continue
        # Number of instances: 1, or the measured mean rounded (capped at 4).
        count = (
            1
            if info["mean_count_when_present"] < 1.5
            else min(4, round(info["mean_count_when_present"]))
        )
        # Place each instance.
        for _ in range(count):
            # Size from the measured percentiles.
            l_ = quantile_sample(sizes[category]["length_m"], rng)
            # Width.
            w_ = quantile_sample(sizes[category]["width_m"], rng)
            # Height.
            h_ = quantile_sample(sizes[category]["height_m"], rng)
            # Rotation in 90 degree steps.
            rotation = float(rng.choice((0, 90, 180, 270)))
            # Footprint after rotation.
            fx, fy = (l_, w_) if rotation in (0, 180) else (w_, l_)
            # Too big for the room.
            if fx > length - 0.1 or fy > width - 0.1:
                # Skip it.
                continue
            # Try random positions.
            for _ in range(30):
                # Centre inside the room with the footprint fully inside.
                cx = rng.uniform(fx / 2, length - fx / 2)
                # Y centre.
                cy = rng.uniform(fy / 2, width - fy / 2)
                # Rectangle.
                rect = (cx - fx / 2, cy - fy / 2, cx + fx / 2, cy + fy / 2)
                # Keep only non-overlapping placements.
                if not any(overlaps(rect, other) for other in placed):
                    # Remember it.
                    placed.append(rect)
                    # Add the object.
                    objects.append(
                        {
                            "type": category,
                            "position": [round(cx, 2), round(cy, 2)],
                            "rotation": rotation,
                            "dimensions": [round(l_, 2), round(w_, 2), round(h_, 2)],
                        }
                    )
                    # Done with this instance.
                    break
    # Give ids and flags.
    return objects


def make_record(
    index: int, priors: dict, catalog: list[dict], rng: random.Random
) -> tuple[dict, dict]:
    """Build one scene dict and its gold requirement dict."""
    # Random room type.
    room_type = rng.choice(ROOM_TYPES_USED)
    # Room size.
    length, width, height = sample_room(room_type, priors["structured3d"]["room_size"], rng)
    # Openings.
    openings = sample_openings(length, width, rng)
    # Existing objects from the SUN priors.
    raw_objects = sample_objects(
        room_type,
        length,
        width,
        priors["sun_rgbd"]["cooccurrence"],
        priors["sun_rgbd"]["object_size"],
        rng,
    )
    # Scene id.
    scene_id = f"syn_room_{index:05d}"
    # Objects with ids, movable and must-keep flags.
    objects = []
    # Number each object.
    for number, obj in enumerate(raw_objects, start=1):
        # Must-keep about a quarter of the time.
        keep = rng.random() < 0.25
        # Build the scene object.
        objects.append(
            {
                "id": f"{scene_id}_obj_{number:02d}",
                **obj,
                "movable": not keep,
                "must_keep": keep,
                "confidence": rng.choice(("low", "medium", "high")),
            }
        )
    # The scene graph.
    scene = {
        "scene_id": scene_id,
        "version": 1,
        "room_type": room_type,
        "dimensions": {
            "length": length,
            "width": width,
            "height": height,
            "confidence": rng.choice(("low", "medium", "high")),
        },
        "openings": openings,
        "objects": objects,
    }
    # Categories the user asks for, taken from the room-type list.
    must_have = sorted(rng.sample(WANTED[room_type], rng.randint(1, 3)))
    # Median catalog price per wanted category.
    by_category: dict[str, list[float]] = {}
    # Group catalog prices.
    for item in catalog:
        # Append price.
        by_category.setdefault(item["category"], []).append(item["price"])
    # Sum of medians for the wanted items.
    base = sum(sorted(by_category[c])[len(by_category[c]) // 2] for c in must_have)
    # Budget is 1.2x to 3x that base, rounded to 1000 INR.
    budget = float(max(5000, round(base * rng.uniform(1.2, 3.0) / 1000) * 1000))
    # Style.
    style = rng.choice(STYLES)
    # People count.
    occupants = rng.randint(1, 4)
    # Accessibility in about one in five rooms.
    accessible = rng.random() < 0.2
    # Random objective weights in [0, 1] (independent draws, one term boosted to 1.0 at most).
    weights = {k: round(rng.uniform(0.1, 1.0), 2) for k in ObjectiveWeights.model_fields}
    # Must-keep ids in this scene.
    keep_ids = [o["id"] for o in objects if o["must_keep"]]
    # Requirement text that matches the gold JSON.
    text = (
        f"I want to redo my {room_type.replace('_', ' ')} in a {style.replace('_', ' ')} style. "
        f"I need {', '.join(c.replace('_', ' ') for c in must_have)}. "
        f"The budget is {int(budget)} rupees for {occupants} "
        f"{'person' if occupants == 1 else 'people'}."
    )
    # Mention the kept objects and accessibility so the text matches the JSON.
    if keep_ids:
        # Names of the kept objects.
        kept_names = [o["type"].replace("_", " ") for o in objects if o["must_keep"]]
        # Add the sentence.
        text += f" Please keep my {', '.join(kept_names)}."
    # Accessibility sentence.
    if accessible:
        # Add the sentence.
        text += " The room must be wheelchair accessible."
    # The gold requirement.
    requirement = {
        "requirement_id": f"syn_req_{index:05d}",
        "scene_id": scene_id,
        "raw_text": text,
        "budget_inr": budget,
        "must_have": must_have,
        "must_keep_object_ids": keep_ids,
        "occupant_count": occupants,
        "style": style,
        "accessibility_required": accessible,
        "objective_weights": weights,
    }
    # Give both back.
    return scene, requirement


def generate(n: int, seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """Generate n validated (scene, requirement) pairs."""
    # Seeded generator.
    rng = random.Random(seed)
    # Priors and catalog.
    priors = read_json(cleaning_dir() / "layout_priors.json")
    # Catalog rows.
    catalog = read_jsonl(cleaning_dir() / "furniture_catalog.jsonl")
    # Output lists.
    scenes: list[dict] = []
    # Requirements.
    requirements: list[dict] = []
    # Build each pair.
    for index in range(1, n + 1):
        # One pair.
        scene, requirement = make_record(index, priors, catalog, rng)
        # Locked-schema validation raises on any violation.
        SceneGraph.model_validate(scene)
        # Same for the requirement.
        Requirement.model_validate(requirement)
        # Keep both.
        scenes.append(scene)
        # Requirement.
        requirements.append(requirement)
    # Give the lists back.
    return scenes, requirements


def run(n: int = 2000) -> dict:
    """Generate the set under datasets/raw/synthetic and write a small tracked manifest."""
    # Generate and validate.
    scenes, requirements = generate(n)
    # Output folder (gitignored).
    out = raw_dir("synthetic")
    # Full set, not committed.
    write_jsonl(out / "scenes.jsonl", scenes)
    # Requirements.
    write_jsonl(out / "requirements.jsonl", requirements)
    # Tracked manifest: counts and three schema-valid examples.
    manifest = {
        "seed": SEED,
        "records": n,
        "scenes_valid": n,
        "requirements_valid": n,
        "room_type_counts": {
            t: sum(1 for s in scenes if s["room_type"] == t) for t in ROOM_TYPES_USED
        },
        "scenes_with_must_keep": sum(1 for r in requirements if r["must_keep_object_ids"]),
        "accessibility_required": sum(1 for r in requirements if r["accessibility_required"]),
        "objects_total": sum(len(s["objects"]) for s in scenes),
        "generated_set": "datasets/raw/synthetic/ (gitignored, not committed)",
        "examples": [{"scene": scenes[i], "requirement": requirements[i]} for i in range(3)],
    }
    # Persist the manifest.
    write_json(cleaning_dir() / "synthetic_manifest.json", manifest)
    # Give it back.
    return manifest
