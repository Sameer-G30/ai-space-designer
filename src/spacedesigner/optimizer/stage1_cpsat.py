"""Stage 1 grid placement using OR-Tools CP-SAT."""

# math converts metric coordinates conservatively to grid cells.
import math

# time measures each isolated solve.
import time

# uuid creates deterministic design identifiers from input identifiers.
import uuid

# Mapping is the optional warm-start hint table. The default solve passes none.
from collections.abc import Mapping

# dataclass keeps internal placement variables explicit.
from dataclasses import dataclass

# CP-SAT supplies interval variables and exact no-overlap constraints.
from ortools.sat.python import cp_model

# BOM aggregation is deterministic and independent of placement order.
from spacedesigner.optimizer.bom import build_bom

# Catalog loading defaults to the tracked JSONL source.
from spacedesigner.optimizer.catalog import load_catalog

# Named constants document every Phase 3 clearance.
from spacedesigner.optimizer.constants import (
    GRID_SIZE_M,
    LOW_CONFIDENCE_MARGIN_M,
    MAX_SOLVE_TIME_SECONDS,
    MIN_CIRCULATION_WIDTH_M,
    MIN_DOOR_CLEAR_WIDTH_M,
    TURNING_SPACE_DIAMETER_M,
)

# Result models keep traces and BOMs outside the locked Design schema.
from spacedesigner.optimizer.models import (
    FeasibleOptimization,
    InfeasibleOptimization,
    OptimizationResult,
)

# Locked schemas define every public input and output record.
from spacedesigner.schemas import (
    BindingConstraint,
    CatalogItem,
    Design,
    ObjectiveTerms,
    OptimizerTrace,
    RejectedItem,
    Requirement,
    SceneGraph,
    SceneObject,
)

# Material scores are deterministic placeholders until Phase 4.
MATERIAL_SCORES = {
    # Fast-renewing natural material receives the strongest placeholder score.
    "bamboo": 1.0,
    # Solid wood receives a high reusable-material score.
    "solid_wood": 0.8,
    # Engineered wood receives a moderate score.
    "engineered_wood": 0.6,
    # Metal receives a moderate recycling-oriented score.
    "metal": 0.7,
    # Upholstery receives a conservative score.
    "upholstered_fabric": 0.5,
    # Plastic receives a low placeholder score.
    "plastic": 0.3,
    # Glass receives a moderate placeholder score.
    "glass": 0.6,
}


# Internal variables associated with one new catalog item.
@dataclass(frozen=True)
class _PlacementVars:
    """Keep one item's CP-SAT variables together."""

    # Catalog row represented by these variables.
    item: CatalogItem
    # Horizontal start cell for the unpadded footprint.
    x: cp_model.IntVar
    # Vertical start cell for the unpadded footprint.
    y: cp_model.IntVar
    # Rotation selector, where one means 90 degrees.
    rotated: cp_model.IntVar
    # Width in x-grid cells after rotation.
    size_x: cp_model.IntVar
    # Width in y-grid cells after rotation.
    size_y: cp_model.IntVar


# Convert a positive metric length upward so geometry is never understated.
def _ceil_cells(value: float) -> int:
    """Round a metric extent upward to solver cells."""
    # Return at least one cell for every positive physical dimension.
    return max(1, math.ceil((value - 1e-9) / GRID_SIZE_M))


# Convert a metric coordinate downward for conservative fixed bounds.
def _floor_cell(value: float) -> int:
    """Round a coordinate downward to a solver cell."""
    # Floor preserves the entire fixed footprint.
    return math.floor((value + 1e-9) / GRID_SIZE_M)


# Determine floor dimensions after a right-angle rotation.
def _rotated_footprint(obj: SceneObject) -> tuple[float, float]:
    """Return an object's world-axis footprint."""
    # Normalize arbitrary degree values before testing the quarter turn.
    quarter_turn = round(obj.rotation / 90.0) % 4
    # Swap local edges for 90-degree and 270-degree poses.
    if quarter_turn in {1, 3}:
        # Return width on x and length on y.
        return obj.dimensions[1], obj.dimensions[0]
    # Keep local length on x and width on y.
    return obj.dimensions[0], obj.dimensions[1]


# Build a fixed interval with a stable end expression.
def _fixed_interval(
    model: cp_model.CpModel,
    start: int,
    size: int,
    name: str,
) -> cp_model.IntervalVar:
    """Create one fixed CP-SAT interval."""
    # Use integer constants so the interval has no decision variable.
    return model.new_interval_var(start, size, start + size, name)


# Convert one wall opening into an inward keep-out rectangle.
def _opening_box(scene: SceneGraph, index: int) -> tuple[int, int, int, int]:
    """Return an opening keep-out as x, y, width, and height cells."""
    # Select the validated opening by stable list index.
    opening = scene.openings[index]
    # Convert its along-wall start conservatively.
    along_start = _floor_cell(opening.position)
    # Cover the exact upper along-wall edge despite coordinate offset.
    along_end = math.ceil((opening.position + opening.width) / GRID_SIZE_M)
    # Convert the full conservative along-wall span.
    along_size = along_end - along_start
    # Use circulation width as the required clear approach depth.
    depth = _ceil_cells(MIN_CIRCULATION_WIDTH_M)
    # Read complete room extents in grid cells.
    room_x = math.floor(scene.dimensions.length / GRID_SIZE_M)
    # Read the perpendicular room extent.
    room_y = math.floor(scene.dimensions.width / GRID_SIZE_M)
    # North occupies the top horizontal wall.
    if opening.wall.lower() == "north":
        # Extend inward from the north boundary.
        return along_start, max(0, room_y - depth), along_size, depth
    # South occupies the bottom horizontal wall.
    if opening.wall.lower() == "south":
        # Extend inward from the south boundary.
        return along_start, 0, along_size, depth
    # East occupies the right vertical wall.
    if opening.wall.lower() == "east":
        # Extend inward from the east boundary.
        return max(0, room_x - depth), along_start, depth, along_size
    # West occupies the left vertical wall.
    if opening.wall.lower() == "west":
        # Extend inward from the west boundary.
        return 0, along_start, depth, along_size
    # Reject walls outside the supported rectangular frame.
    raise ValueError(f"opening {index} has unsupported wall '{opening.wall}'")


# Pick one deterministic catalog item for every missing category.
def _select_items(
    scene: SceneGraph,
    requirement: Requirement,
    catalog: tuple[CatalogItem, ...],
    fixed_objects: list[SceneObject],
) -> tuple[list[CatalogItem], list[RejectedItem], str | None]:
    """Select compact affordable candidates before geometric placement."""
    # Categories already supplied by retained furniture need no purchase.
    present = {obj.type for obj in fixed_objects}
    # Deduplicate required categories while preserving user order.
    missing = list(
        dict.fromkeys(category for category in requirement.must_have if category not in present)
    )
    # Collect the chosen catalog rows.
    selected: list[CatalogItem] = []
    # Explain considered alternatives that were not selected.
    rejected: list[RejectedItem] = []
    # Process each missing category independently.
    for category in missing:
        # Find all matching rows in source order.
        matches = [item for item in catalog if item.category == category]
        # A category absent from the catalog makes the hard requirement impossible.
        if not matches:
            # Return a readable failure without constructing a model.
            return [], rejected, f"no catalog item exists for required category '{category}'"
        # Prefer lowest price, then smallest footprint, then stable identifier.
        ordered = sorted(
            matches,
            key=lambda item: (
                item.price,
                item.dims.length * item.dims.width,
                item.item_id,
            ),
        )
        # Select exactly one mandatory row for Stage 1.
        selected.append(ordered[0])
        # Record every same-category alternative and the deterministic reason.
        rejected.extend(
            RejectedItem(
                item_id=item.item_id,
                reason=f"higher deterministic rank than selected {ordered[0].item_id}",
            )
            for item in ordered[1:]
        )
    # Return selected rows and trace facts.
    return selected, rejected, None


# Compute deterministic objective terms without embeddings.
def _objective_terms(
    scene: SceneGraph,
    requirement: Requirement,
    objects: list[SceneObject],
    selected: list[CatalogItem],
    cost: float,
) -> ObjectiveTerms:
    """Compute six bounded deterministic Phase 3 terms."""
    # Sum exact placed footprint area.
    used_area = sum(_rotated_footprint(obj)[0] * _rotated_footprint(obj)[1] for obj in objects)
    # Normalize utilization against room floor area.
    utilization = min(1.0, used_area / (scene.dimensions.length * scene.dimensions.width))
    # Reward useful but not excessive utilization.
    layout = max(0.0, 1.0 - abs(utilization - 0.35) / 0.35)
    # Use unused floor fraction as a simple circulation proxy.
    circulation = max(0.0, min(1.0, 1.0 - utilization))
    # Hard-clearance compliance gives the full ergonomic term.
    ergonomics = 1.0
    # Reward remaining budget while preserving hard compliance.
    budget = (
        1.0
        if requirement.budget_inr == 0 and cost == 0
        else max(
            0.0,
            min(1.0, 1.0 - cost / max(requirement.budget_inr, 1.0)),
        )
    )
    # Tokenize the requested style for deterministic tag overlap.
    style_tokens = {token.strip().lower() for token in requirement.style.replace(",", " ").split()}
    # Count selected rows with at least one matching style tag.
    style_matches = sum(
        bool(style_tokens.intersection(tag.lower() for tag in item.style_tags)) for item in selected
    )
    # Use perfect compatibility when no new purchase is needed.
    aesthetics = 1.0 if not selected else style_matches / len(selected)
    # Average fixed material lookup values for selected rows.
    sustainability = (
        1.0
        if not selected
        else sum(MATERIAL_SCORES.get(item.material, 0.5) for item in selected) / len(selected)
    )
    # Validate and clamp all six public values.
    return ObjectiveTerms(
        layout=layout,
        circulation=circulation,
        ergonomics=ergonomics,
        budget=budget,
        aesthetics=aesthetics,
        sustainability=sustainability,
    )


# Combine normalized terms with the locked user weights.
def _weighted_score(requirement: Requirement, terms: ObjectiveTerms) -> float:
    """Return a normalized weighted average."""
    # Serialize weights in the same field order as objective terms.
    weights = requirement.objective_weights.model_dump()
    # Serialize terms for matching name lookup.
    values = terms.model_dump()
    # Sum all supplied weights without requiring them to total one.
    denominator = sum(weights.values())
    # A zero vector has a deterministic zero score.
    if denominator == 0:
        # Return the neutral score.
        return 0.0
    # Compute the weighted mean over all six fields.
    return sum(weights[name] * values[name] for name in weights) / denominator


# Solve one room and return either one audited candidate or a reason.
def optimize(
    scene: SceneGraph,
    requirement: Requirement,
    catalog: tuple[CatalogItem, ...] | None = None,
    selection: list[CatalogItem] | None = None,
    variant: str | None = None,
    term_overrides: dict[str, float] | None = None,
    hints: Mapping[str, tuple[int, int, int]] | None = None,
) -> OptimizationResult:
    """Produce one hard-feasible design, optionally for a caller-chosen item selection."""
    # Start wall-clock measurement before preflight checks.
    started = time.perf_counter()
    # Reject mismatched records before model construction.
    if requirement.scene_id != scene.scene_id:
        # Return a readable identifier mismatch.
        return InfeasibleOptimization(
            reason="requirement scene_id does not match the supplied scene",
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Build the complete must-keep identifier set.
    required_ids = set(requirement.must_keep_object_ids)
    # Include scene-level must-keep flags even if the requirement omitted them.
    required_ids.update(obj.id for obj in scene.objects if obj.must_keep)
    # Index scene objects for stable lookup.
    scene_by_id = {obj.id: obj for obj in scene.objects}
    # Identify references that cannot be fixed.
    missing_ids = sorted(required_ids.difference(scene_by_id))
    # Reject dangling must-keep references.
    if missing_ids:
        # Explain all missing identifiers.
        return InfeasibleOptimization(
            reason=f"must-keep object ids are absent from the scene: {', '.join(missing_ids)}",
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Preserve fixed objects in original scene order.
    fixed_objects = [obj for obj in scene.objects if obj.id in required_ids]
    # Validate every physical door clear width.
    narrow_doors = [
        index
        for index, opening in enumerate(scene.openings)
        if opening.type.lower() == "door" and opening.width < MIN_DOOR_CLEAR_WIDTH_M
    ]
    # A narrow required opening cannot meet the hard standard.
    if narrow_doors:
        # Report stable opening indexes.
        return InfeasibleOptimization(
            reason=f"door openings below {MIN_DOOR_CLEAR_WIDTH_M:.3f} m: {narrow_doors}",
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Load the tracked JSONL only when no explicit test catalog was supplied.
    active_catalog = load_catalog() if catalog is None else catalog
    # Select deterministic Stage 1 items for missing categories.
    selected, rejected, selection_error = _select_items(
        scene,
        requirement,
        active_catalog,
        fixed_objects,
    )
    # A Stage 2 caller may replace the cheapest default with its own chosen rows.
    if selection is not None and selection_error is None:
        # Categories that still need a purchase after retained furniture.
        needed = sorted(item.category for item in selected)
        # The override must cover exactly the same missing categories.
        if sorted(item.category for item in selection) != needed:
            # A mismatched override cannot satisfy must_have presence.
            return InfeasibleOptimization(
                reason="supplied selection does not match the missing required categories",
                solve_time_ms=(time.perf_counter() - started) * 1000,
            )
        # Keep the caller's order so placement is deterministic.
        selected = list(selection)
        # Rebuild the rejected list relative to the supplied rows.
        chosen_ids = {item.item_id for item in selected}
        # Record same-category alternatives that Stage 2 scored lower.
        rejected = [
            RejectedItem(
                item_id=item.item_id,
                reason="lower Stage 2 objective score than the selected item of its category",
            )
            for item in active_catalog
            if item.category in needed and item.item_id not in chosen_ids
        ]
    # Return any catalog coverage failure directly.
    if selection_error is not None:
        # Preserve the readable selector reason.
        return InfeasibleOptimization(
            reason=selection_error,
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Compute exact purchased cost.
    cost = sum(item.price for item in selected)
    # Reject a deterministic selection that exceeds the hard budget.
    if cost > requirement.budget_inr + 1e-6:
        # Include both amounts for actionable feedback.
        return InfeasibleOptimization(
            reason=(
                f"minimum selected catalog cost INR {cost:.2f} exceeds "
                f"budget INR {requirement.budget_inr:.2f}"
            ),
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Create the finite-domain model.
    model = cp_model.CpModel()
    # Convert room extents conservatively downward.
    room_x = math.floor(scene.dimensions.length / GRID_SIZE_M)
    # Convert the second room extent.
    room_y = math.floor(scene.dimensions.width / GRID_SIZE_M)
    # Apply the extra wall inset only to low-confidence rooms.
    margin_m = LOW_CONFIDENCE_MARGIN_M if scene.dimensions.confidence.value == "low" else 0.0
    # Convert the wall inset upward.
    margin = _ceil_cells(margin_m) if margin_m > 0 else 0
    # Furniture itself is unpadded; circulation is the reserved opening approach.
    padding = 0
    # Collect padded furniture x intervals for no-overlap.
    x_intervals: list[cp_model.IntervalVar] = []
    # Collect padded furniture y intervals for no-overlap.
    y_intervals: list[cp_model.IntervalVar] = []
    # Collect reserved x intervals that may overlap one another.
    reserved_x: list[cp_model.IntervalVar] = []
    # Collect reserved y intervals paired with reserved x intervals.
    reserved_y: list[cp_model.IntervalVar] = []
    # Add every fixed object as a conservative padded obstacle.
    for index, obj in enumerate(fixed_objects):
        # Compute the exact rotated floor edges.
        footprint_x, footprint_y = _rotated_footprint(obj)
        # Compute conservative lower x cell.
        start_x = _floor_cell(obj.position[0] - footprint_x / 2)
        # Compute conservative lower y cell.
        start_y = _floor_cell(obj.position[1] - footprint_y / 2)
        # Compute conservative upper x cell.
        end_x = math.ceil((obj.position[0] + footprint_x / 2) / GRID_SIZE_M)
        # Compute conservative upper y cell.
        end_y = math.ceil((obj.position[1] + footprint_y / 2) / GRID_SIZE_M)
        # Cover the exact fixed x footprint despite coordinate offset.
        size_x = end_x - start_x
        # Cover the exact fixed y footprint despite coordinate offset.
        size_y = end_y - start_y
        # Reject fixed geometry outside the usable low-confidence inset.
        if (
            start_x < margin
            or start_y < margin
            or start_x + size_x > room_x - margin
            or start_y + size_y > room_y - margin
        ):
            # Explain which retained object violates bounds.
            return InfeasibleOptimization(
                reason=f"must-keep object '{obj.id}' lies outside the usable room bounds",
                solve_time_ms=(time.perf_counter() - started) * 1000,
            )
        # Expand x by circulation half-padding.
        padded_x = start_x - padding
        # Expand y by circulation half-padding.
        padded_y = start_y - padding
        # Add a fixed expanded x interval.
        x_intervals.append(
            _fixed_interval(model, padded_x, size_x + 2 * padding, f"fixed_x_{index}")
        )
        # Add a fixed expanded y interval.
        y_intervals.append(
            _fixed_interval(model, padded_y, size_y + 2 * padding, f"fixed_y_{index}")
        )
    # Add each opening as a fixed no-placement obstacle.
    for index in range(len(scene.openings)):
        # Convert the wall slot into an inward box.
        box_x, box_y, box_w, box_h = _opening_box(scene, index)
        # Add its x projection to the reserved list.
        reserved_x.append(_fixed_interval(model, box_x, box_w, f"opening_x_{index}"))
        # Add its y projection to the reserved list.
        reserved_y.append(_fixed_interval(model, box_y, box_h, f"opening_y_{index}"))
    # Reserve a central square containing the required turning circle.
    if requirement.accessibility_required:
        # Convert the turning diameter upward.
        turning = _ceil_cells(TURNING_SPACE_DIAMETER_M)
        # Center the reserved square horizontally.
        turning_x = (room_x - turning) // 2
        # Center the reserved square vertically.
        turning_y = (room_y - turning) // 2
        # Reject rooms physically too small for the turning square.
        if turning_x < margin or turning_y < margin:
            # Return a direct accessibility reason.
            return InfeasibleOptimization(
                reason=f"room cannot contain a {TURNING_SPACE_DIAMETER_M:.3f} m turning space",
                solve_time_ms=(time.perf_counter() - started) * 1000,
            )
        # Add the fixed turning-space x interval.
        reserved_x.append(_fixed_interval(model, turning_x, turning, "turning_x"))
        # Add the fixed turning-space y interval.
        reserved_y.append(_fixed_interval(model, turning_y, turning, "turning_y"))
    # Collect variables needed to decode new placements.
    placements: list[_PlacementVars] = []
    # Create one mandatory placement for every selected item.
    for index, item in enumerate(selected):
        # Convert local catalog dimensions to cells.
        base_x = _ceil_cells(item.dims.length)
        # Convert the local width independently.
        base_y = _ceil_cells(item.dims.width)
        # Rotation is zero for 0 degrees and one for 90 degrees.
        rotated = model.new_bool_var(f"rotated_{index}")
        # World x extent is selected from the two local edges.
        size_x = model.new_int_var(min(base_x, base_y), max(base_x, base_y), f"size_x_{index}")
        # World y extent is selected from the two local edges.
        size_y = model.new_int_var(min(base_x, base_y), max(base_x, base_y), f"size_y_{index}")
        # Tie rotation and dimensions exactly.
        model.add_allowed_assignments(
            [rotated, size_x, size_y],
            [(0, base_x, base_y), (1, base_y, base_x)],
        )
        # Padded start stays inside the confidence inset.
        padded_start_x = model.new_int_var(margin, room_x - margin, f"padded_x_{index}")
        # Padded start stays inside the confidence inset vertically.
        padded_start_y = model.new_int_var(margin, room_y - margin, f"padded_y_{index}")
        # Unpadded start follows the padded start.
        start_x = model.new_int_var(margin + padding, room_x - margin, f"x_{index}")
        # Unpadded vertical start follows the padded start.
        start_y = model.new_int_var(margin + padding, room_y - margin, f"y_{index}")
        # Link the actual x start to circulation padding.
        model.add(start_x == padded_start_x + padding)
        # Link the actual y start to circulation padding.
        model.add(start_y == padded_start_y + padding)
        # Padded x end depends on the selected rotation.
        padded_end_x = model.new_int_var(margin, room_x - margin, f"padded_end_x_{index}")
        # Padded y end depends on the selected rotation.
        padded_end_y = model.new_int_var(margin, room_y - margin, f"padded_end_y_{index}")
        # Add the mandatory padded x interval.
        x_interval = model.new_interval_var(
            padded_start_x,
            size_x + 2 * padding,
            padded_end_x,
            f"new_x_{index}",
        )
        # Add the mandatory padded y interval.
        y_interval = model.new_interval_var(
            padded_start_y,
            size_y + 2 * padding,
            padded_end_y,
            f"new_y_{index}",
        )
        # Collect the x projection.
        x_intervals.append(x_interval)
        # Collect the y projection.
        y_intervals.append(y_interval)
        # Preserve decoding variables and metadata.
        placements.append(_PlacementVars(item, start_x, start_y, rotated, size_x, size_y))
    # Enforce rectangle non-overlap across furniture and reserved spaces.
    model.add_no_overlap_2d(x_intervals, y_intervals)
    # Keep every furniture rectangle out of every reserved rectangle.
    for furniture_x, furniture_y in zip(x_intervals, y_intervals, strict=True):
        # Add one independent pairwise exclusion per reserved area.
        for obstacle_x, obstacle_y in zip(reserved_x, reserved_y, strict=True):
            # Reserved areas may overlap each other but never furniture.
            model.add_no_overlap_2d(
                [furniture_x, obstacle_x],
                [furniture_y, obstacle_y],
            )
    # Minimize starts for deterministic lower-left placement.
    model.minimize(sum(var.x + var.y + var.rotated for var in placements))
    # Count hints actually attached, so a missing item id is not treated as a warm start.
    hints_applied = 0
    # Attach warm-start hints only when a counterfactual caller supplied them.
    if hints:
        # Each hint is (start x cell, start y cell, rotation bit) for one catalog item.
        for placement in placements:
            # Skip items the previous design did not place.
            hinted = hints.get(placement.item.item_id)
            # This item has no previous pose.
            if hinted is None:
                # Leave it for a normal search.
                continue
            # Unpack the previous cell pose.
            hint_x, hint_y, hint_rotated = hinted
            # Local edges in cells, matching the rotation encoding below.
            base_x = _ceil_cells(placement.item.dims.length)
            # Width is independent of length.
            base_y = _ceil_cells(placement.item.dims.width)
            # Bit 1 swaps the local edges, which is the only rotation Stage 1 uses.
            swapped = int(hint_rotated) == 1
            # World x size that agrees with the rotation bit.
            hint_size_x = base_y if swapped else base_x
            # World y size that agrees with the rotation bit.
            hint_size_y = base_x if swapped else base_y
            # Hint the unpadded x start. A bad value is repaired rather than fixed.
            model.add_hint(placement.x, int(hint_x))
            # Hint the unpadded y start.
            model.add_hint(placement.y, int(hint_y))
            # Hint the 0-or-90 rotation bit.
            model.add_hint(placement.rotated, 1 if swapped else 0)
            # Hint the x extent so the hint assignment is complete.
            model.add_hint(placement.size_x, int(hint_size_x))
            # Hint the y extent so the hint assignment is complete.
            model.add_hint(placement.size_y, int(hint_size_y))
            # Record that this item received a hint.
            hints_applied += 1
    # Configure the finite-domain solver.
    solver = cp_model.CpSolver()
    # Apply the short per-room time limit.
    solver.parameters.max_time_in_seconds = MAX_SOLVE_TIME_SECONDS
    # Use one worker for reproducible benchmark behavior.
    solver.parameters.num_search_workers = 1
    # Repair an infeasible hint instead of changing the no-hint search.
    if hints_applied:
        # The default path leaves this parameter unset.
        solver.parameters.repair_hint = True
    # Solve the complete hard-constraint model.
    status = solver.solve(model)
    # Reject unknown, invalid, and infeasible statuses.
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        # Translate solver status into a readable phase-level reason.
        return InfeasibleOptimization(
            reason=(
                "no placement satisfies room bounds, clearances, openings, "
                "must-keep poses, accessibility, and budget"
            ),
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Start the output with exact unchanged must-keep objects.
    design_objects = [obj.model_copy(deep=True) for obj in fixed_objects]
    # Decode every selected item into the locked SceneObject shape.
    for index, placement in enumerate(placements):
        # Read the chosen start in metric units.
        start_x_m = solver.value(placement.x) * GRID_SIZE_M
        # Read the chosen vertical start.
        start_y_m = solver.value(placement.y) * GRID_SIZE_M
        # Read the selected world x extent.
        extent_x_m = solver.value(placement.size_x) * GRID_SIZE_M
        # Read the selected world y extent.
        extent_y_m = solver.value(placement.size_y) * GRID_SIZE_M
        # Convert the rotation bit to degrees.
        rotation = 90.0 if solver.value(placement.rotated) else 0.0
        # Append a validated generated scene object.
        design_objects.append(
            SceneObject(
                id=f"catalog::{placement.item.item_id}::{index}",
                type=placement.item.category,
                position=[start_x_m + extent_x_m / 2, start_y_m + extent_y_m / 2],
                rotation=rotation,
                dimensions=[
                    placement.item.dims.length,
                    placement.item.dims.width,
                    placement.item.dims.height,
                ],
                movable=True,
                must_keep=False,
                confidence="high",
            )
        )
    # Compute all deterministic objective terms.
    terms = _objective_terms(scene, requirement, design_objects, selected, cost)
    # Stage 2 replaces the placeholder aesthetics term with its CLIP-based value.
    if term_overrides:
        # Copy with the overridden bounded terms; validation re-checks the [0, 1] range.
        terms = ObjectiveTerms.model_validate({**terms.model_dump(), **term_overrides})
    # Derive a stable identifier from the two input identifiers (plus a variant for Stage 2).
    suffix = "" if variant is None else f":{variant}"
    design_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"photospace:{scene.scene_id}:{requirement.requirement_id}{suffix}",
        )
    )
    # Validate the final design against the locked contract.
    design = Design(
        design_id=design_id,
        scene_id=scene.scene_id,
        requirement_id=requirement.requirement_id,
        weights=requirement.objective_weights,
        score=_weighted_score(requirement, terms),
        cost=cost,
        objects=design_objects,
    )
    # Record relevant hard constraints for later explanations.
    bindings = [
        BindingConstraint(
            name="must_have",
            detail=f"all {len(set(requirement.must_have))} required categories are present",
        ),
        BindingConstraint(
            name="circulation",
            detail=f"furniture clearance is at least {MIN_CIRCULATION_WIDTH_M:.3f} m",
        ),
        BindingConstraint(
            name="budget",
            detail=f"catalog cost INR {cost:.2f} is within INR {requirement.budget_inr:.2f}",
        ),
    ]
    # Record the low-confidence inset when active.
    if margin_m > 0:
        # Append its measured value.
        bindings.append(
            BindingConstraint(
                name="low_confidence_margin",
                detail=f"room walls use an extra {margin_m:.3f} m safety inset",
            )
        )
    # Record accessibility reservation when required.
    if requirement.accessibility_required:
        # Append the cited turning-space diameter.
        bindings.append(
            BindingConstraint(
                name="accessibility_turning_space",
                detail=f"central turning space diameter is {TURNING_SPACE_DIAMETER_M:.3f} m",
            )
        )
    # Validate the full trace separately from Design.
    trace = OptimizerTrace(
        design_id=design_id,
        binding_constraints=bindings,
        rejected_items=rejected,
        objective_terms=terms,
    )
    # Aggregate selected rows into stable BOM lines.
    bom = build_bom(selected)
    # Assert the required BOM/cost invariant before returning.
    if abs(sum(line.line_total for line in bom) - design.cost) > 1e-6:
        # Treat an internal accounting mismatch as infeasible rather than leaking a bad design.
        return InfeasibleOptimization(
            reason="internal BOM total does not equal design cost",
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Return one complete feasible result.
    return FeasibleOptimization(
        design=design,
        trace=trace,
        bom=bom,
        solve_time_ms=(time.perf_counter() - started) * 1000,
    )
