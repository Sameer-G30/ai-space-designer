"""Pure helpers for the Phase 11 ladder. They do not call Ollama or edit a design."""

# Annotations on Python 3.11.
from __future__ import annotations

# json decodes one layout object.
import json

# Median free-floor and utilization.
import statistics

# Stable design ids for guessed layouts.
import uuid

# Floor rectangles for SUN RGB-D layouts. OpenCV is not imported.
from shapely.geometry import Polygon

# The live checker. This module does not weaken it.
from spacedesigner.critic.deterministic import audit_design

# Kind labels shared with the advisory critic log.
from spacedesigner.critic.disagreement import HARD_KINDS, violation_kinds

# Named constants are read so a retrieved number can be compared. They are not edited.
from spacedesigner.optimizer.constants import (
    LOW_CONFIDENCE_MARGIN_M,
    MIN_CIRCULATION_WIDTH_M,
    MIN_DOOR_CLEAR_WIDTH_M,
    TURNING_SPACE_DIAMETER_M,
)

# Locked records.
from spacedesigner.schemas import CatalogItem, Design, Requirement, SceneGraph
from spacedesigner.schemas.requirement import ObjectiveWeights
from spacedesigner.schemas.scene import Confidence, SceneObject

# How many cheapest catalog rows the coordinate guess may see per category.
SHORTLIST_PER_CATEGORY = 3

# Same plausibility cut the Phase 7b layout scorer uses, applied to a Shapely rectangle.
MIN_SIDE_M = 1.0

# Floor-to-ceiling range, in metres, for a usable SUN RGB-D layout.
HEIGHT_RANGE_M = (1.8, 5.0)

# Retrieved names that correspond to a named solver constant. Others are only recorded.
RETRIEVED_TO_SOLVER = {
    "door_clear_width": "door_clear_width",
    "turning_space": "turning_space",
    "clear_width": "circulation",
}

# Room types the synthetic generator already pairs with catalog categories.
REAL_MUST_HAVE = {
    "bedroom": ("bed", "nightstand"),
    "living_room": ("sofa", "coffee_table"),
    "dining_room": ("table", "chair"),
    "home_office": ("desk", "chair"),
}

# JSON schema for one coordinate guess. The product parser schema is not reused.
LAYOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "rotation": {"type": "number"},
                },
                "required": ["id", "x", "y", "rotation"],
            },
        }
    },
    "required": ["objects"],
}


# Named solver clearances, for comparison only.
def solver_constant_values() -> dict[str, float]:
    """Return the three clearance constants a retrieved number might name."""
    # Circulation approach, door width, and turning diameter. The grid is not a clearance.
    return {
        "circulation": MIN_CIRCULATION_WIDTH_M,
        "door_clear_width": MIN_DOOR_CLEAR_WIDTH_M,
        "turning_space": TURNING_SPACE_DIAMETER_M,
    }


# Categories that still need a purchase.
def missing_categories(scene: SceneGraph, requirement: Requirement) -> list[str]:
    """Return must-have categories that no must-keep object already covers."""
    # Ids the requirement or the scene marks as fixed.
    required_ids = set(requirement.must_keep_object_ids)
    # Scene flags count even when the requirement list omitted them.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Types already present among those fixed objects.
    present = {obj.type for obj in scene.objects if obj.id in required_ids}
    # Categories still missing, in the requirement's order.
    missing = [category for category in requirement.must_have if category not in present]
    # Drop duplicates without changing that order.
    return list(dict.fromkeys(missing))


# Cheapest rows, matching Stage 1's sort key, limited to a short prompt.
def shortlist_items(
    catalog: tuple[CatalogItem, ...] | list[CatalogItem],
    categories: list[str],
    per_category: int = SHORTLIST_PER_CATEGORY,
) -> list[CatalogItem]:
    """Return up to per_category rows per category, cheapest footprint first."""
    # Chosen rows in category order.
    chosen: list[CatalogItem] = []
    # One category at a time.
    for category in categories:
        # Rows of this class, in file order before the sort.
        matches = [item for item in catalog if item.category == category]
        # Same key Stage 1 uses: price, footprint, then id.
        ordered = sorted(
            matches,
            key=lambda item: (item.price, item.dims.length * item.dims.width, item.item_id),
        )
        # The prompt only sees the first few.
        chosen.extend(ordered[:per_category])
    # Flat list.
    return chosen


# One user message describing the room and the allowed ids.
def layout_messages(
    scene: SceneGraph,
    requirement: Requirement,
    shortlist: list[CatalogItem],
) -> list[dict[str, str]]:
    """Build the chat messages for a coordinate guess. Retrieved numbers are not included."""
    # Fixed objects the model must account for.
    required_ids = set(requirement.must_keep_object_ids)
    # Scene-level flags.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Lines for those objects.
    keep_lines = []
    # Each fixed object, in scene order.
    for obj in scene.objects:
        # Only the required ones are mandatory in the reply.
        if obj.id not in required_ids:
            # Movable scene objects are not part of this guess.
            continue
        # One readable line. Dimensions stay on the scene object.
        keep_lines.append(
            f"{obj.id} type {obj.type} x {obj.position[0]} y {obj.position[1]} "
            f"rotation {obj.rotation} size {obj.dimensions[0]} {obj.dimensions[1]} "
            f"{obj.dimensions[2]}"
        )
    # Candidate purchases.
    candidate_lines = [
        (
            f"{item.item_id} category {item.category} price {item.price} "
            f"size {item.dims.length} {item.dims.width} {item.dims.height}"
        )
        for item in shortlist
    ]
    # Openings the checker will enforce.
    opening_lines = [
        f"{opening.type} on {opening.wall} at {opening.position} width {opening.width}"
        for opening in scene.openings
    ]
    # Low-confidence rooms lose an inset. The text states that rule; it does not change code.
    inset = (
        f"Confidence is low. Keep every footprint at least {LOW_CONFIDENCE_MARGIN_M} m "
        "inside each wall."
        if scene.dimensions.confidence.value == "low"
        else "Confidence is not low. Footprints may touch the walls."
    )
    # The instruction block. Named constants are the solver's, not retrieved replacements.
    system = "\n".join(
        [
            "You place furniture by guessing centre coordinates. Reply with JSON only.",
            "x and y are metres from the south-west corner. rotation is degrees.",
            "Copy every must-keep id. Use only candidate ids for new items.",
            "Do not invent an id. Pick at most one candidate per required category.",
            f"Stay inside the room. Do not overlap. Leave {MIN_CIRCULATION_WIDTH_M} m",
            "clear in front of each opening.",
            f"A door narrower than {MIN_DOOR_CLEAR_WIDTH_M} m cannot be widened.",
            f"If accessibility is required, leave a {TURNING_SPACE_DIAMETER_M} m circle",
            "at the room centre.",
            "Do not spend more than the budget. You cannot change the design after you reply.",
        ]
    )
    # The room facts.
    user = "\n".join(
        [
            (
                f"room {scene.dimensions.length} by {scene.dimensions.width} "
                f"by {scene.dimensions.height}"
            ),
            inset,
            f"budget_inr {requirement.budget_inr}",
            f"accessibility_required {requirement.accessibility_required}",
            "must_have " + ", ".join(requirement.must_have),
            "openings:",
            *opening_lines,
            "must_keep:",
            *keep_lines,
            "candidates:",
            *candidate_lines,
        ]
    )
    # System rules, then the room.
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# Decode the assistant string into an object.
def parse_layout_payload(raw: str) -> dict:
    """Return the JSON object. Raise ValueError when it is not a layout object."""
    # Strip a fence if the model added one.
    text = raw.strip()
    # Opening fence.
    if text.startswith("```"):
        # Drop the first line.
        text = text.split("\n", 1)[-1]
        # Drop the closing fence.
        text = text.removesuffix("```").strip()
    # Decode.
    try:
        # One value.
        value = json.loads(text)
    # Not JSON.
    except json.JSONDecodeError as exc:
        # The caller counts this as no design.
        raise ValueError("layout JSON could not be parsed") from exc
    # An object with a list.
    if not isinstance(value, dict) or not isinstance(value.get("objects"), list):
        # Not a layout.
        raise ValueError("layout JSON needs an objects list")
    # Usable payload.
    return value


# Turn a parsed guess into a Design. Unknown ids are skipped, not invented.
def design_from_guess(
    payload: dict,
    scene: SceneGraph,
    requirement: Requirement,
    shortlist: list[CatalogItem],
) -> tuple[Design, list[CatalogItem], list[str]]:
    """Build a design from guessed centres. The checker still decides violations."""
    # Notes for the report. They do not change the checker.
    notes: list[str] = []
    # Candidate ids the prompt offered.
    by_item = {item.item_id: item for item in shortlist}
    # Scene objects by id.
    by_scene = {obj.id: obj for obj in scene.objects}
    # Fixed ids.
    required_ids = set(requirement.must_keep_object_ids)
    # Scene flags.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Placed objects.
    objects: list[SceneObject] = []
    # Purchases, one per accepted candidate row.
    selected: list[CatalogItem] = []
    # Ids already placed.
    seen: set[str] = set()
    # Each guessed row.
    for index, row in enumerate(payload.get("objects", [])):
        # Skip a non-object.
        if not isinstance(row, dict):
            # Note it.
            notes.append(f"skipped row {index}")
            # Next row.
            continue
        # Id as text.
        object_id = str(row.get("id", "")).strip()
        # Pose fields.
        try:
            # Centre x.
            x = float(row["x"])
            # Centre y.
            y = float(row["y"])
            # Rotation in degrees.
            rotation = float(row["rotation"])
        # Missing or non-numeric.
        except (KeyError, TypeError, ValueError):
            # Skip this row.
            notes.append(f"skipped {object_id or index}: bad pose")
            # Next row.
            continue
        # A must-keep or other scene id.
        if object_id in by_scene:
            # Duplicate ids are invalid on the schema.
            if object_id in seen:
                # Skip the repeat.
                notes.append(f"skipped duplicate {object_id}")
                # Next row.
                continue
            # Source pose and size.
            source = by_scene[object_id]
            # Place the scene size at the guessed centre so a moved keep is visible.
            objects.append(
                SceneObject(
                    id=source.id,
                    type=source.type,
                    position=[x, y],
                    rotation=rotation,
                    dimensions=list(source.dimensions),
                    movable=source.movable,
                    must_keep=source.must_keep or object_id in required_ids,
                    confidence=source.confidence,
                )
            )
            # Remember the id.
            seen.add(object_id)
            # Next row.
            continue
        # A candidate purchase.
        item = by_item.get(object_id)
        # Not on the shortlist.
        if item is None:
            # Do not invent a catalog row.
            notes.append(f"skipped unknown id {object_id}")
            # Next row.
            continue
        # New object id. The index keeps repeats unique.
        placed_id = f"llm::{item.item_id}::{index}"
        # Place the catalog size. Coordinates are not snapped to the solver grid.
        objects.append(
            SceneObject(
                id=placed_id,
                type=item.category,
                position=[x, y],
                rotation=rotation,
                dimensions=[item.dims.length, item.dims.width, item.dims.height],
                movable=True,
                must_keep=False,
                confidence=Confidence.high,
            )
        )
        # This row is a purchase.
        selected.append(item)
        # Remember the placed id.
        seen.add(placed_id)
    # Cost is the sum of accepted purchases. Kept scene objects are not priced.
    cost = float(sum(item.price for item in selected))
    # Stable id for this guess.
    design_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"photospace-llm:{scene.scene_id}:{requirement.requirement_id}",
        )
    )
    # Score is unused. Zero marks that this is not an optimizer score.
    design = Design(
        design_id=design_id,
        scene_id=scene.scene_id,
        requirement_id=requirement.requirement_id,
        weights=requirement.objective_weights,
        score=0.0,
        cost=cost,
        objects=objects,
    )
    # Design, purchases, and skip notes.
    return design, selected, notes


# World-axis floor area of one object, using the checker's quarter-turn rule.
def _footprint_area(obj: SceneObject) -> float:
    """Return length times width after a quarter-turn swap."""
    # Quarter turn.
    quarter = round(obj.rotation / 90.0) % 4
    # Odd turns swap the floor edges.
    if quarter in {1, 3}:
        # Width along x, length along y.
        return obj.dimensions[1] * obj.dimensions[0]
    # Even turns keep the local axes.
    return obj.dimensions[0] * obj.dimensions[1]


# Fraction of required categories present.
def _must_have_rate(requirement: Requirement, design: Design) -> float | None:
    """Return present/required, or None when nothing was required."""
    # Stable unique categories.
    required = list(dict.fromkeys(requirement.must_have))
    # Nothing to satisfy.
    if not required:
        # Not applicable.
        return None
    # Types in the design.
    present = {obj.type for obj in design.objects}
    # Fraction.
    return sum(category in present for category in required) / len(required)


# Fraction of must-keep ids that the checker did not reject.
def _must_keep_rate(
    scene: SceneGraph,
    requirement: Requirement,
    violations: list[str],
) -> float | None:
    """Return pose-correct keeps over required keeps, or None when there are none."""
    # Required ids.
    required_ids = set(requirement.must_keep_object_ids)
    # Scene flags.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Nothing to retain.
    if not required_ids:
        # Not applicable.
        return None
    # Ids the checker said were missing or moved.
    bad = 0
    # Each required id.
    for object_id in required_ids:
        # The checker quotes the id, so obj_01 does not match obj_010.
        token = f"'{object_id}'"
        # A violation that names this id as absent or moved.
        failed = any(
            token in text and ("absent" in text or "changed pose" in text) for text in violations
        )
        # Count it.
        bad += int(failed)
    # Fraction that were not flagged.
    return (len(required_ids) - bad) / len(required_ids)


# One returned design, scored by the live checker.
def score_design(
    scene: SceneGraph,
    requirement: Requirement,
    design: Design,
    bom: list,
) -> dict:
    """Return violation, budget, and requirement counts for one design."""
    # Independent audit. The list is the source of violations.
    violations = audit_design(scene, requirement, design, bom)
    # Hard kinds.
    kinds = violation_kinds(violations)
    # Floor area.
    floor = scene.dimensions.length * scene.dimensions.width
    # Sum of footprints. Overlap can push this above the floor area.
    used = sum(_footprint_area(obj) for obj in design.objects)
    # Ratio.
    utilization = used / floor if floor else 0.0
    # Clearance-kind strings, including the checker's own phrases.
    clearance_hit = any(
        "clearance" in text.lower() or "turning" in text.lower() or "blocks opening" in text.lower()
        for text in violations
    )
    # The row the aggregator reads.
    return {
        "returned": True,
        "violation_count": len(violations),
        "violations": violations,
        "kinds": sorted(kinds),
        "budget_ok": design.cost <= requirement.budget_inr + 1e-6,
        "cost": design.cost,
        "must_have_rate": _must_have_rate(requirement, design),
        "must_keep_rate": _must_keep_rate(scene, requirement, violations),
        "utilization": utilization,
        "free_floor": max(0.0, 1.0 - utilization),
        "clearance_clean": not clearance_hit,
    }


# A room that produced no design.
def no_design_row(reason: str) -> dict:
    """Return a row that counts as not clean and not returned."""
    # Reason is stored. Rates stay empty.
    return {"returned": False, "reason": reason, "violation_count": 0}


# True when a returned design meets every hard check this phase reports.
def row_is_clean(row: dict) -> bool:
    """Return True only for a returned design with no violation and full satisfaction."""
    # No design is not a success.
    if not row.get("returned"):
        # Infeasible and unreadable both fail this rate.
        return False
    # Must-have. None means nothing was required.
    have = row.get("must_have_rate")
    # Must-keep.
    keep = row.get("must_keep_rate")
    # All three hard outcomes.
    return (
        row.get("violation_count", 1) == 0
        and bool(row.get("budget_ok"))
        and (have is None or have == 1.0)
        and (keep is None or keep == 1.0)
    )


# Rates over a list of per-room rows.
def aggregate_layouts(rows: list[dict]) -> dict:
    """Summarise violation, budget, and requirement rates. Empty input is explicit."""
    # Nothing was measured.
    if not rows:
        # A zero-room aggregate, not a fake perfect score.
        return {"rooms": 0, "returned": 0, "no_design": 0, "clean": 0, "clean_rate": None}
    # Returned designs only.
    returned = [row for row in rows if row.get("returned")]
    # Counts.
    rooms = len(rows)
    # Returned count.
    n_returned = len(returned)
    # Any hard violation.
    with_violation = sum(1 for row in returned if row["violation_count"] > 0)
    # Budget.
    budget_ok = sum(1 for row in returned if row.get("budget_ok"))
    # Clean rooms, including no-design as not clean.
    clean = sum(1 for row in rows if row_is_clean(row))
    # Must-have means over returned rows that have a rate.
    have_values = [
        row["must_have_rate"] for row in returned if row.get("must_have_rate") is not None
    ]
    # Must-keep means.
    keep_values = [
        row["must_keep_rate"] for row in returned if row.get("must_keep_rate") is not None
    ]
    # Utilization values.
    utilization = [row["utilization"] for row in returned if "utilization" in row]
    # Free floor.
    free_floor = [row["free_floor"] for row in returned if "free_floor" in row]
    # Clearance.
    clearance_clean = sum(1 for row in returned if row.get("clearance_clean"))
    # Kind counts among returned designs.
    kind_counts = {kind: 0 for kind in HARD_KINDS}
    # Each returned design.
    for row in returned:
        # Each kind that design raised.
        for kind in row.get("kinds", []):
            # Only the four hard kinds.
            if kind in kind_counts:
                # Count the design once per kind.
                kind_counts[kind] += 1
    # Mean violations.
    mean_violations = (
        sum(row["violation_count"] for row in returned) / n_returned if n_returned else None
    )
    # The summary.
    return {
        "rooms": rooms,
        "returned": n_returned,
        "no_design": rooms - n_returned,
        "with_violation": with_violation,
        "violation_rate": (with_violation / n_returned) if n_returned else None,
        "mean_violations": mean_violations,
        "budget_ok": budget_ok,
        "budget_rate": (budget_ok / n_returned) if n_returned else None,
        "clean": clean,
        "clean_rate": clean / rooms,
        "must_have_mean": (sum(have_values) / len(have_values)) if have_values else None,
        "must_have_rooms": len(have_values),
        "must_keep_mean": (sum(keep_values) / len(keep_values)) if keep_values else None,
        "must_keep_rooms": len(keep_values),
        "utilization_median": statistics.median(utilization) if utilization else None,
        "free_floor_median": statistics.median(free_floor) if free_floor else None,
        "clearance_clean": clearance_clean,
        "clearance_clean_rate": (clearance_clean / n_returned) if n_returned else None,
        "kinds": kind_counts,
    }


# Compare retrieved numbers with named constants. Nothing is written back to the solver.
def clearance_gaps(
    retrieved: list[tuple[str, float]],
    constants: dict[str, float] | None = None,
) -> list[dict]:
    """Return one record per retrieved number. applied is always false."""
    # Live constants unless a test passes a stand-in.
    values = solver_constant_values() if constants is None else constants
    # Records.
    gaps: list[dict] = []
    # Each number.
    for name, value_m in retrieved:
        # Solver name, if this retrieved label maps to one.
        solver_name = RETRIEVED_TO_SOLVER.get(name)
        # No matching constant. Still recorded, still not applied.
        if solver_name is None:
            # Unmapped measurement.
            gaps.append(
                {
                    "name": name,
                    "value_m": value_m,
                    "solver_constant": None,
                    "differs": False,
                    "applied": False,
                }
            )
            # Next number.
            continue
        # Named constant.
        constant = values[solver_name]
        # One millimetre tolerance.
        differs = abs(float(value_m) - float(constant)) > 0.001
        # Record the comparison.
        gaps.append(
            {
                "name": name,
                "value_m": value_m,
                "solver_constant": solver_name,
                "solver_value_m": constant,
                "differs": differs,
                "applied": False,
            }
        )
    # Every number.
    return gaps


# Counts across rooms.
def summarize_gaps(per_room: list[list[dict]]) -> dict:
    """Count retrieved numbers and how many differ from a named constant."""
    # Totals.
    numbers = 0
    # Mapped to a constant.
    mapped = 0
    # Mapped and different.
    differs = 0
    # Rooms that returned at least one number.
    rooms_with_numbers = 0
    # Each room.
    for gaps in per_room:
        # This room contributed.
        if gaps:
            # Count the room.
            rooms_with_numbers += 1
        # Each number.
        for gap in gaps:
            # Count it.
            numbers += 1
            # Mapped.
            if gap.get("solver_constant") is not None:
                # Count the mapping.
                mapped += 1
                # Count a difference.
                differs += int(bool(gap.get("differs")))
    # Summary. The solver was not given these numbers.
    return {
        "rooms": len(per_room),
        "rooms_with_numbers": rooms_with_numbers,
        "numbers": numbers,
        "mapped_to_solver_constant": mapped,
        "mapped_values_that_differ": differs,
        "applied_to_solver": False,
    }


# Largest floor polygon to a minimum rotated rectangle.
def sun_layout_rectangle(payload: dict) -> tuple[float, float, float] | None:
    """Return length, width, height in metres, or None when the layout is unusable."""
    # Best polygon so far.
    best_area = -1.0
    # Geometry of that polygon.
    best_geom = None
    # Height of that polygon.
    best_height = None
    # Each annotated object.
    for obj in payload.get("objects") or []:
        # Null placeholders in the SUN file.
        if not obj:
            # Skip.
            continue
        # Each polygon on that object.
        for poly in obj.get("polygon") or []:
            # Floor outline.
            xs = poly.get("X") or []
            # Depth axis in the SUN frame.
            zs = poly.get("Z") or []
            # Need a polygon.
            if len(xs) < 3 or len(xs) != len(zs):
                # Skip.
                continue
            # Pairs.
            points = list(zip(xs, zs, strict=True))
            # Shapely polygon.
            polygon = Polygon(points)
            # Repair a self-intersection when Shapely can.
            if not polygon.is_valid:
                # Zero buffer is the usual repair.
                polygon = polygon.buffer(0)
            # Empty repair.
            if polygon.is_empty or polygon.area <= best_area:
                # Not the largest.
                continue
            # Height from the annotation, not from the floor polygon.
            try:
                # Ymax minus Ymin.
                height = float(poly["Ymax"]) - float(poly["Ymin"])
            # Missing height.
            except (KeyError, TypeError, ValueError):
                # Skip.
                continue
            # Keep it.
            best_area = float(polygon.area)
            # Geometry.
            best_geom = polygon
            # Height.
            best_height = height
    # No polygon.
    if best_geom is None or best_height is None:
        # Unusable.
        return None
    # Minimum rotated rectangle.
    rect = best_geom.minimum_rotated_rectangle
    # Corners.
    coords = list(rect.exterior.coords)
    # Edge lengths.
    edges: list[float] = []
    # Each edge.
    for index in range(len(coords) - 1):
        # Delta x.
        dx = coords[index + 1][0] - coords[index][0]
        # Delta y.
        dy = coords[index + 1][1] - coords[index][1]
        # Length.
        edges.append((dx * dx + dy * dy) ** 0.5)
    # A rectangle has four edges.
    if len(edges) < 4:
        # Unusable.
        return None
    # Longest and the opposite short side (index 2 on a rectangle).
    ordered = sorted(edges, reverse=True)
    # Long side.
    length = ordered[0]
    # Short side.
    width = ordered[2]
    # Phase 7b plausibility cut.
    if width < MIN_SIDE_M or not HEIGHT_RANGE_M[0] <= best_height <= HEIGHT_RANGE_M[1]:
        # Drop it.
        return None
    # Metres.
    return float(length), float(width), float(best_height)


# Eligible SUN manifest rows for the real-room sample.
def eligible_sun_rows(rows: list[dict]) -> list[dict]:
    """Keep test layouts with a supported room type that are not also NYU frames."""
    # Chosen rows.
    chosen = []
    # Each manifest row.
    for row in rows:
        # Test split only.
        if row.get("split") != "test" or not row.get("has_test_geometry"):
            # Skip.
            continue
        # Leave NYU-overlapping frames out of the SUN sample so the two sets stay distinct.
        if row.get("overlaps_nyu_depth_v2"):
            # Skip.
            continue
        # Only room types with a fixed template below.
        if row.get("room_type") not in REAL_MUST_HAVE:
            # Skip.
            continue
        # Keep the row.
        chosen.append(row)
    # Stable order before a seeded shuffle.
    chosen.sort(key=lambda row: str(row.get("id", "")))
    # Eligible rows.
    return chosen


# An empty scene whose size is an annotated rectangle.
def rectangle_scene(
    scene_id: str,
    room_type: str,
    length: float,
    width: float,
    height: float,
) -> SceneGraph:
    """Build a high-confidence scene with no objects and no openings."""
    # Validate.
    return SceneGraph.model_validate(
        {
            "scene_id": scene_id,
            "version": 1,
            "room_type": room_type,
            "dimensions": {
                "length": round(float(length), 3),
                "width": round(float(width), 3),
                "height": round(float(height), 3),
                "confidence": "high",
            },
            "openings": [],
            "objects": [],
        }
    )


# Median catalog price times two, rounded to 1000 INR, for a fixed template.
def template_budget(
    catalog: tuple[CatalogItem, ...] | list[CatalogItem],
    categories: tuple[str, ...] | list[str],
) -> float:
    """Return a deterministic budget from median prices. Raises if a category is missing."""
    # Sum of medians.
    total = 0.0
    # Each required category.
    for category in categories:
        # Prices.
        prices = sorted(item.price for item in catalog if item.category == category)
        # The template cannot ask for a class the catalog does not sell.
        if not prices:
            # Tell the caller.
            raise ValueError(f"no catalog price for {category}")
        # Median, lower middle on an even count.
        total += prices[(len(prices) - 1) // 2]
    # Twice that sum, at least 5000, rounded to thousands.
    return float(max(5000, round(total * 2 / 1000) * 1000))


# Fixed requirement for one real room. The sentence matches the JSON and is not parsed here.
def template_requirement(
    scene_id: str,
    room_type: str,
    budget_inr: float,
) -> Requirement:
    """Return the structured requirement used for a SUN layout room."""
    # Categories for this room type.
    categories = REAL_MUST_HAVE[room_type]
    # Equal weights.
    weights = {name: 1.0 for name in ObjectiveWeights.model_fields}
    # A sentence a person could have typed. Parsing it is a separate, optional step.
    text = (
        f"I want to redo my {room_type.replace('_', ' ')} in a modern style. "
        f"I need {', '.join(category.replace('_', ' ') for category in categories)}. "
        f"The budget is {int(budget_inr)} rupees for 1 person."
    )
    # Validate.
    return Requirement.model_validate(
        {
            "requirement_id": f"requirement-{scene_id}",
            "scene_id": scene_id,
            "raw_text": text,
            "budget_inr": budget_inr,
            "must_have": list(categories),
            "must_keep_object_ids": [],
            "occupant_count": 1,
            "style": "modern",
            "accessibility_required": False,
            "objective_weights": weights,
        }
    )


# Added, removed, cost, and score on a version diff.
def diff_matches(before: Design, after: Design, diff: dict) -> bool:
    """Return True when the diff's sets and deltas match the two designs."""
    # Ids before.
    before_ids = {obj.id for obj in before.objects}
    # Ids after.
    after_ids = {obj.id for obj in after.objects}
    # Added set.
    if set(diff.get("items_added", [])) != after_ids - before_ids:
        # Mismatch.
        return False
    # Removed set.
    if set(diff.get("items_removed", [])) != before_ids - after_ids:
        # Mismatch.
        return False
    # Cost delta.
    if abs(float(diff.get("cost_change", 0.0)) - (after.cost - before.cost)) > 1e-6:
        # Mismatch.
        return False
    # Score delta.
    if abs(float(diff.get("score_change", 0.0)) - (after.score - before.score)) > 1e-6:
        # Mismatch.
        return False
    # Moved list.
    moved = diff.get("items_moved", [])
    # Must be a list.
    if not isinstance(moved, list):
        # Mismatch.
        return False
    # Ids that claim to have moved.
    moved_ids = {entry["id"] for entry in moved if isinstance(entry, dict) and "id" in entry}
    # A moved id has to exist on both sides.
    return moved_ids <= (before_ids & after_ids)
