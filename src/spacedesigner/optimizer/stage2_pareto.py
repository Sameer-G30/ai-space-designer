"""Stage 2: sweep objective weights, pick items, place with Stage 1, keep the Pareto front."""

# itertools builds the weight grid.
import itertools

# time measures the whole sweep.
import time

# The independent checker gates every returned point.
from spacedesigner.critic import audit_design

# Same JSONL catalog source as Stage 1.
from spacedesigner.optimizer.catalog import load_catalog

# Result models.
from spacedesigner.optimizer.models import (
    FeasibleOptimization,
    InfeasibleOptimization,
    ParetoOptimization,
    ParetoPoint,
    ParetoResult,
)

# The existing Stage 1 placer keeps every hard constraint inside CP-SAT.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Item scoring and style similarity.
from spacedesigner.recommend.scoring import StyleScorer, load_style_scorer, score_item

# Locked schema types.
from spacedesigner.schemas import CatalogItem, ObjectiveWeights, Requirement, SceneGraph

# Levels swept for the budget, aesthetics and sustainability weights (3^3 - 1 = 26 vectors).
SWEEP_LEVELS = (0.0, 0.5, 1.0)

# Layout, circulation and ergonomics stay fixed during the sweep.
SWEEP_FIXED = 0.5

# Most points a Pareto set may hold.
MAX_POINTS = 8

# Fewest points the set is topped up to when more non-dominated designs exist.
MIN_POINTS = 4

# Objective axes maximized when checking dominance (budget term already encodes cost).
AXES = ("layout", "circulation", "ergonomics", "budget", "aesthetics", "sustainability")


# Every weight vector in the sweep, starting with the requirement's own weights.
def weight_sweep(requirement: Requirement) -> list[ObjectiveWeights]:
    """Return the deterministic list of weight vectors to try."""
    # Start from the user's own weights so their preference is always represented.
    vectors = [requirement.objective_weights]
    # Add the grid over budget, aesthetics, and sustainability.
    for budget, aesthetics, sustainability in itertools.product(SWEEP_LEVELS, repeat=3):
        # An all-zero vector has no meaning, so skip it.
        if budget == aesthetics == sustainability == 0.0:
            # Move to the next vector.
            continue
        # Build the swept weights.
        vectors.append(
            ObjectiveWeights(
                layout=SWEEP_FIXED,
                circulation=SWEEP_FIXED,
                ergonomics=SWEEP_FIXED,
                budget=budget,
                aesthetics=aesthetics,
                sustainability=sustainability,
            )
        )
    # Return in stable order.
    return vectors


# True when a is at least as good as b everywhere and strictly better somewhere.
def dominates(a: dict[str, float], b: dict[str, float], eps: float = 1e-9) -> bool:
    """Return whether term vector a Pareto-dominates term vector b."""
    # No axis may be worse.
    no_worse = all(a[name] >= b[name] - eps for name in AXES)
    # At least one axis must be strictly better.
    strictly_better = any(a[name] > b[name] + eps for name in AXES)
    # Both conditions define dominance.
    return no_worse and strictly_better


# Keep only candidates that no other candidate dominates.
def non_dominated(points: list[ParetoPoint]) -> list[ParetoPoint]:
    """Filter dominated points and collapse exact duplicates (cheapest wins)."""
    # Term vectors per point.
    terms = [p.trace.objective_terms.model_dump() for p in points]
    # Indices that survive.
    keep: list[int] = []
    # Test each point against all others.
    for i, term in enumerate(terms):
        # Dominated by any other point?
        if any(dominates(terms[j], term) for j in range(len(points)) if j != i):
            # Drop it.
            continue
        # Exact duplicates: keep the earlier cheaper one only.
        if any(
            all(abs(terms[j][n] - term[n]) <= 1e-9 for n in AXES)
            and (points[j].design.cost, points[j].design.design_id)
            < (points[i].design.cost, points[i].design.design_id)
            for j in range(len(points))
            if j != i
        ):
            # Drop the more expensive duplicate.
            continue
        # This point survives.
        keep.append(i)
    # Return survivors in input order.
    return [points[i] for i in keep]


# Swap picks for cheaper alternatives until the selection fits the budget.
def _repair(
    per_category: dict[str, list[tuple[float, CatalogItem]]],
    budget: float,
) -> list[CatalogItem] | None:
    """Return an affordable selection, or None if even the best repair is over budget."""
    # Start from each category's best-scored row.
    chosen = {category: rows[0] for category, rows in per_category.items()}
    # Loop until the total price fits.
    while sum(item.price for _, item in chosen.values()) > budget + 1e-6:
        # Best swap: smallest score loss per rupee saved.
        best: tuple[float, str, tuple[float, CatalogItem]] | None = None
        # Look at every category.
        for category, rows in per_category.items():
            # Score and price currently chosen here.
            score, item = chosen[category]
            # Try each cheaper alternative.
            for alt_score, alt in rows:
                # Only cheaper rows can help.
                if alt.price >= item.price:
                    # Skip.
                    continue
                # Score lost per rupee saved (lower is better).
                loss = (score - alt_score) / (item.price - alt.price)
                # Remember the cheapest-loss swap.
                if best is None or (loss, alt.item_id) < (best[0], best[2][1].item_id):
                    # New best swap.
                    best = (loss, category, (alt_score, alt))
        # No cheaper row exists anywhere, so this weight vector cannot be made affordable.
        if best is None:
            # Give up on this vector.
            return None
        # Apply the swap.
        chosen[best[1]] = best[2]
    # Return the repaired rows in category order.
    return [item for _, item in chosen.values()]


# Assign the labels that name each point in the set.
def label_points(points: list[ParetoPoint], requirement: Requirement) -> list[ParetoPoint]:
    """Label a non-dominated list and cut it to between MIN_POINTS and MAX_POINTS."""
    # Helper: index of the best point under a key (ties broken by design id).
    def best(key) -> int:
        """Return the index minimizing key."""
        # Smallest key wins.
        return min(range(len(points)), key=lambda i: (key(points[i]), points[i].design.design_id))

    # Mean of all six terms for the balanced label.
    def mean_terms(p: ParetoPoint) -> float:
        """Equal-weight mean of the six objective terms."""
        # Average over axes.
        return sum(p.trace.objective_terms.model_dump()[n] for n in AXES) / len(AXES)

    # Weighted score under the user's own weights.
    weights = requirement.objective_weights.model_dump()
    # Total of the user's weights (guard zero).
    total = sum(weights.values()) or 1.0

    # Weighted mean of terms under the user's weights.
    def user_score(p: ParetoPoint) -> float:
        """Score a point under the requirement's own weights."""
        # Weighted average.
        return sum(weights[n] * p.trace.objective_terms.model_dump()[n] for n in AXES) / total

    # Label rules in priority order.
    rules = {
        "cheapest": best(lambda p: p.design.cost),
        "balanced": best(lambda p: -mean_terms(p)),
        "premium": best(lambda p: -p.design.cost),
        "most_sustainable": best(lambda p: -p.trace.objective_terms.sustainability),
        "best_style": best(lambda p: -p.trace.objective_terms.aesthetics),
        "best_space": best(
            lambda p: -(p.trace.objective_terms.layout + p.trace.objective_terms.circulation)
        ),
        "user_weighted": best(lambda p: -user_score(p)),
    }
    # Collect labels per point index.
    labels: dict[int, list[str]] = {}
    # Assign each rule's winner.
    for name, index in rules.items():
        # Append the label.
        labels.setdefault(index, []).append(name)
    # Top up to MIN_POINTS with the remaining points that are farthest in cost from those chosen.
    while len(labels) < min(MIN_POINTS, len(points)):
        # Costs already covered.
        covered = [points[i].design.cost for i in labels]
        # Farthest unlabeled point.
        extra = max(
            (i for i in range(len(points)) if i not in labels),
            key=lambda i: (min(abs(points[i].design.cost - c) for c in covered), -i),
        )
        # Label it by its rank in cost.
        labels[extra] = ["alternative"]
    # Return labelled points ordered by cost, at most MAX_POINTS.
    ordered = sorted(labels, key=lambda i: (points[i].design.cost, points[i].design.design_id))
    # Build new points with labels attached.
    return [points[i].model_copy(update={"labels": labels[i]}) for i in ordered[:MAX_POINTS]]


# Run the whole Stage 2 sweep for one scene and requirement.
def optimize_pareto(
    scene: SceneGraph,
    requirement: Requirement,
    catalog: tuple[CatalogItem, ...] | None = None,
    scorer: StyleScorer | None = None,
) -> ParetoResult:
    """Return one labelled Pareto set of audited designs, or a readable infeasible reason."""
    # Clock for the total sweep.
    started = time.perf_counter()
    # Same catalog source as Stage 1.
    active_catalog = load_catalog() if catalog is None else catalog
    # Cheapest Stage 1 design is the feasibility anchor and the always-present candidate.
    baseline = optimize(scene, requirement, active_catalog)
    # Stage 1 infeasibility is Stage 2 infeasibility (same reason, no design).
    if not baseline.feasible:
        # Return the readable Stage 1 reason with the total time.
        return InfeasibleOptimization(
            reason=baseline.reason, solve_time_ms=(time.perf_counter() - started) * 1000
        )
    # Cached CLIP vectors (no model load) or the labelled tag-overlap fallback.
    active_scorer = scorer or load_style_scorer(active_catalog, extra_styles=(requirement.style,))
    # Style similarity for every row.
    style_scores = active_scorer.style_scores(requirement.style)
    # Categories already covered by fixed scene objects need no purchase.
    fixed_types = {
        obj.type
        for obj in scene.objects
        if obj.must_keep or obj.id in set(requirement.must_keep_object_ids)
    }
    # Missing categories in requirement order.
    missing = list(dict.fromkeys(c for c in requirement.must_have if c not in fixed_types))
    # Room dimensions for space fit.
    room_length, room_width = scene.dimensions.length, scene.dimensions.width
    # Distinct selections already placed, by item-id tuple.
    seen: dict[tuple[str, ...], ParetoPoint | None] = {}
    # Placed, audited candidates.
    candidates: list[ParetoPoint] = []

    # Place, audit, and store one selection.
    def try_selection(selection: list[CatalogItem], weights: ObjectiveWeights) -> None:
        """Run Stage 1 placement for a selection and keep it if hard-clean."""
        # Deduplicate identical selections across weight vectors.
        key = tuple(sorted(item.item_id for item in selection))
        # Already handled.
        if key in seen:
            # Nothing more to do.
            return
        # Mark as seen (None until it passes).
        seen[key] = None
        # Mean CLIP style score of the purchased rows replaces the placeholder aesthetics term.
        aesthetics = (
            1.0
            if not selection
            else sum(style_scores[item.item_id] for item in selection) / len(selection)
        )
        # Weights ride on a copy of the requirement so Design.weights records them.
        weighted = requirement.model_copy(update={"objective_weights": weights})
        # Place with CP-SAT; every hard constraint lives inside this call.
        result = optimize(
            scene,
            weighted,
            active_catalog,
            selection=selection,
            variant="|".join(key),
            term_overrides={"aesthetics": aesthetics},
        )
        # Infeasible geometry or budget: discard the candidate.
        if not isinstance(result, FeasibleOptimization):
            # Skip.
            return
        # Independent audit against the original requirement.
        if audit_design(scene, requirement, result.design, result.bom):
            # A rejected design is never returned.
            return
        # Never exceed the hard budget.
        if result.design.cost > requirement.budget_inr + 1e-6:
            # Skip.
            return
        # Keep the audited candidate.
        point = ParetoPoint(
            labels=["candidate"],
            design=result.design,
            trace=result.trace,
            bom=result.bom,
            solve_time_ms=result.solve_time_ms,
        )
        # Record and store it.
        seen[key] = point
        # Append to the candidate list.
        candidates.append(point)

    # Nothing to buy: the baseline is the only possible design.
    if not missing:
        # Recompute with the baseline's own single selection.
        try_selection([], requirement.objective_weights)
    # Otherwise sweep the weight vectors.
    else:
        # Budget share used by the budget-fit term.
        share = requirement.budget_inr / len(missing)
        # Try the cheapest anchor first so it is always a candidate.
        cheapest = [
            min(
                (i for i in active_catalog if i.category == category),
                key=lambda i: (i.price, i.dims.length * i.dims.width, i.item_id),
            )
            for category in missing
        ]
        # Place the anchor under the user's weights.
        try_selection(cheapest, requirement.objective_weights)
        # Sweep the weights.
        for weights in weight_sweep(requirement):
            # Score every row of each missing category under these weights.
            per_category = {
                category: sorted(
                    (
                        (
                            score_item(
                                item,
                                category,
                                style_scores[item.item_id],
                                weights.model_dump(),
                                room_length,
                                room_width,
                                share,
                            ).total,
                            item,
                        )
                        for item in active_catalog
                        if item.category == category
                    ),
                    key=lambda pair: (-pair[0], pair[1].price, pair[1].item_id),
                )
                for category in missing
            }
            # Weights change which item is picked, before placement.
            selection = _repair(per_category, requirement.budget_inr)
            # Skip vectors that cannot be made affordable.
            if selection is None:
                # Next vector.
                continue
            # Place and audit.
            try_selection(selection, weights)
    # The anchor failed the audit (should not happen): report it as infeasible.
    if not candidates:
        # Readable reason and no design.
        return InfeasibleOptimization(
            reason="no candidate passed the independent hard-constraint audit",
            solve_time_ms=(time.perf_counter() - started) * 1000,
        )
    # Remove dominated candidates.
    front = non_dominated(candidates)
    # Label and cut the set.
    points = label_points(front, requirement)
    # Return the single Pareto set.
    return ParetoOptimization(
        points=points,
        candidates_evaluated=len(candidates),
        dominated_removed=len(candidates) - len(front),
        style_backend=active_scorer.backend_for(requirement.style),
        solve_time_ms=(time.perf_counter() - started) * 1000,
    )
