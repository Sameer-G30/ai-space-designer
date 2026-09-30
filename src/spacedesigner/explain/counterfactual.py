"""Warm-started what-if solves. Selection changes only when the budget no longer fits."""

# json builds a stable id from the requested delta.
import json

# uuid5 keeps a repeated what-if on the same design id.
import uuid

# dataclass keeps the public result beside the requirement the route must store.
from dataclasses import dataclass

# Hints and the purchased rows.
from spacedesigner.explain.hints import hints_from_design, selection_from_design

# Response models.
from spacedesigner.explain.models import (
    CounterfactualDesign,
    CounterfactualRejected,
    CounterfactualRequest,
    CounterfactualResult,
)

# Diff keys shared with the version table.
from spacedesigner.explain.versions import change_diff

# Stage 1 placer. Hints are optional and do not change the hard constraints.
from spacedesigner.optimizer.models import FeasibleOptimization
from spacedesigner.optimizer.stage1_cpsat import optimize

# The repair used when a lower budget cannot keep the current rows.
from spacedesigner.optimizer.stage2_pareto import _repair

# Aesthetics stays on the same style-score scale as Stage 2.
from spacedesigner.recommend.scoring import StyleScorer

# Locked records.
from spacedesigner.schemas import CatalogItem, Design, Requirement, SceneGraph


# The solver result plus the requirement row a successful what-if must persist.
@dataclass(frozen=True)
class PreparedCounterfactual:
    """Hold the API payload and, when feasible, the requirement to store with it."""

    # What the route returns.
    result: CounterfactualResult
    # Requirement for a feasible design. None when the what-if was rejected.
    requirement: Requirement | None = None


# Keep the current rows when they fit. Otherwise swap in cheaper rows of the same categories.
def fit_selection(
    previous: list[CatalogItem],
    catalog: tuple[CatalogItem, ...],
    budget: float,
) -> list[CatalogItem] | None:
    """Return a selection within the budget, or None when even the cheapest rows do not fit."""
    # The current purchases are still legal.
    if sum(item.price for item in previous) <= budget + 1e-6:
        # Keep the poses that the hints refer to.
        return list(previous)
    # Nothing was purchased, so the budget cannot be the reason to fail.
    if not previous:
        # Empty selection.
        return []
    # One scored list per category. The current row is first so repair starts there.
    per_category: dict[str, list[tuple[float, CatalogItem]]] = {}
    # Walk in the current placement order.
    for current in previous:
        # Alternatives of this category, cheaper ones included.
        rows = [(1.0, current)]
        # Every other catalog row of the same category.
        for item in catalog:
            # Skip the row already chosen and every other category.
            if item.category == current.category and item.item_id != current.item_id:
                # Score 0 so repair prefers to keep the current row until it must swap.
                rows.append((0.0, item))
        # Best score first, then cheaper item id, matching the repair helper's expectations.
        rows.sort(key=lambda pair: (-pair[0], pair[1].price, pair[1].item_id))
        # One category.
        per_category[current.category] = rows
    # Swap until the total fits, or give up.
    return _repair(per_category, budget)


# Stable ids so the same delta does not create a second design.
def _ids(
    design: Design,
    scene: SceneGraph,
    request: CounterfactualRequest,
    room_changed: bool,
) -> tuple[str, str]:
    """Return (scene_id, requirement_id) for this delta."""
    # Only the fields the client sent, plus the scene the design was solved against.
    payload = {
        "budget_inr": request.budget_inr,
        "length_m": request.length_m,
        "width_m": request.width_m,
        "height_m": request.height_m,
        "occupant_count": request.occupant_count,
        "scene_id": scene.scene_id,
    }
    # Drop omitted parameters so two equivalent requests share an id.
    canon = {key: value for key, value in payload.items() if value is not None or key == "scene_id"}
    # Compact JSON with sorted keys.
    text = json.dumps(canon, sort_keys=True, separators=(",", ":"))
    # One digest for the whole delta.
    digest = uuid.uuid5(uuid.NAMESPACE_URL, f"photospace-cf:{design.design_id}:{text}")
    # A new requirement row, so the original budget is left in place.
    requirement_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"photospace-req:{digest}"))
    # A room-size change cannot overwrite the scene the parent design still uses.
    if room_changed:
        # New scene id.
        scene_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"photospace-scene:{digest}"))
    # Budget and occupant changes keep the scene.
    else:
        # Same room.
        scene_id = scene.scene_id
    # Both ids.
    return scene_id, requirement_id


# Solve one what-if. This function does not write to the database.
def prepare_counterfactual(
    scene: SceneGraph,
    requirement: Requirement,
    design: Design,
    request: CounterfactualRequest,
    catalog: tuple[CatalogItem, ...],
    scorer: StyleScorer,
    use_hints: bool = True,
) -> PreparedCounterfactual:
    """Re-solve with optional CP-SAT hints and return the design or a reason."""
    # Replacement budget, or the budget this design was solved under.
    budget = requirement.budget_inr if request.budget_inr is None else request.budget_inr
    # Replacement edges. Unset fields keep the current room.
    length = scene.dimensions.length if request.length_m is None else request.length_m
    # Width.
    width = scene.dimensions.width if request.width_m is None else request.width_m
    # Height. Stage 1 does not place against it, but the scene record keeps it.
    height = scene.dimensions.height if request.height_m is None else request.height_m
    # Occupants. Stage 1 does not constrain the count.
    if request.occupant_count is None:
        # Keep the stored count.
        occupants = requirement.occupant_count
    # The client sent a new count.
    else:
        # Use it.
        occupants = request.occupant_count
    # A room change is a real geometry change, not a repeated value.
    room_changed = (
        abs(length - scene.dimensions.length) > 1e-9
        or abs(width - scene.dimensions.width) > 1e-9
        or abs(height - scene.dimensions.height) > 1e-9
    )
    # How far the budget moved. Zero when the client left it alone or repeated it.
    budget_change = budget - requirement.budget_inr
    # Scene id stays put unless the room changed.
    scene_id, requirement_id = _ids(design, scene, request, room_changed)
    # Dimensions object with the edited edges and the same confidence.
    dimensions = scene.dimensions.model_copy(
        update={"length": length, "width": width, "height": height}
    )
    # Scene the solver will see.
    solved_scene = scene.model_copy(
        update={
            "scene_id": scene_id,
            "version": 1 if room_changed else scene.version,
            "dimensions": dimensions,
        }
    )
    # Requirement the solver will see. Weights stay on the design's own weights.
    solved_requirement = requirement.model_copy(
        update={
            "requirement_id": requirement_id,
            "scene_id": scene_id,
            "budget_inr": budget,
            "occupant_count": occupants,
            "objective_weights": design.weights,
        }
    )
    # Rows the parent design bought.
    previous = selection_from_design(design, catalog)
    # Cheaper rows when the current ones no longer fit.
    selection = fit_selection(previous, catalog, budget)
    # No affordable row for a required category.
    if selection is None:
        # Do not start CP-SAT.
        return PreparedCounterfactual(
            result=CounterfactualRejected(
                reason=f"no catalog selection fits budget INR {budget:.2f}",
                parent_design_id=design.design_id,
                solve_time_ms=0.0,
                warm_started=False,
                hint_count=0,
            )
        )
    # Poses from the parent, limited to items that are still being bought.
    available = hints_from_design(design, catalog)
    # Item ids in the new selection.
    kept = {item.item_id for item in selection}
    # Hints CP-SAT will see. An empty dict is not a warm start.
    hints = {item_id: pose for item_id, pose in available.items() if item_id in kept}
    # The cold path builds the same hints and then ignores them, so the timed section matches.
    passed_hints = hints if use_hints and hints else None
    # Style scores for the unchanged style word.
    style_scores = scorer.style_scores(requirement.style)
    # Mean aesthetics, or 1 when nothing is purchased, matching Stage 2.
    aesthetics = (
        1.0
        if not selection
        else sum(style_scores[item.item_id] for item in selection) / len(selection)
    )
    # Same variant rule as Stage 2 so a replay finds this design again.
    variant = "|".join(sorted(item.item_id for item in selection))
    # Place. Hard constraints are unchanged. Hints only guide the search.
    result = optimize(
        solved_scene,
        solved_requirement,
        catalog,
        selection=selection,
        variant=variant,
        term_overrides={"aesthetics": aesthetics},
        hints=passed_hints,
    )
    # How many hints were handed to the solver.
    hint_count = 0 if passed_hints is None else len(passed_hints)
    # No feasible placement under the new parameters.
    if not isinstance(result, FeasibleOptimization):
        # Readable reason, no design.
        return PreparedCounterfactual(
            result=CounterfactualRejected(
                reason=result.reason,
                parent_design_id=design.design_id,
                solve_time_ms=result.solve_time_ms,
                warm_started=hint_count > 0,
                hint_count=hint_count,
            )
        )
    # Point the new design at its parent. The trace id already matches the new design id.
    child = result.design.model_copy(update={"parent_design_id": design.design_id})
    # Score and cost deltas against the stored parent.
    score_change = child.score - design.score
    # Rupee delta.
    cost_change = child.cost - design.cost
    # Null when the budget did not move, so the UI does not show a divide-by-zero.
    sensitivity = None if abs(budget_change) <= 1e-9 else score_change / budget_change
    # Extra diff keys. The five required keys are added by change_diff.
    extra: dict[str, object] = {}
    # Record the budget pair whenever the client sent one, including a repeated value.
    if request.budget_inr is not None:
        # Budget before.
        extra["budget_before_inr"] = requirement.budget_inr
        # Budget after.
        extra["budget_after_inr"] = budget
    # Sensitivity is present only when the budget actually changed.
    if sensitivity is not None:
        # The by-product the explanation may quote.
        extra["sensitivity_score_per_inr"] = sensitivity
    # Room edges when the geometry changed.
    if room_changed:
        # Length.
        extra["room_length_m"] = length
        # Width.
        extra["room_width_m"] = width
        # Height.
        extra["room_height_m"] = height
    # Occupants when the count changed.
    if occupants != requirement.occupant_count:
        # Previous count.
        extra["occupant_count_before"] = requirement.occupant_count
        # New count.
        extra["occupant_count_after"] = occupants
    # Diff stored on both the parent version and the child version.
    diff = change_diff(design, child, extra)
    # Successful what-if. The route persists the requirement and the public result.
    return PreparedCounterfactual(
        result=CounterfactualDesign(
            design=child,
            trace=result.trace,
            bom=result.bom,
            scene=solved_scene,
            parent_design_id=design.design_id,
            solve_time_ms=result.solve_time_ms,
            score_change=score_change,
            cost_change=cost_change,
            budget_change_inr=budget_change,
            sensitivity_score_per_inr=sensitivity,
            hint_count=hint_count,
            warm_started=hint_count > 0,
            diff=diff,
        ),
        requirement=solved_requirement,
    )
