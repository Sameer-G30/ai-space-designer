"""Rebuild an optimizer trace from a stored design. The trace is not a database column."""

# FeasibleOptimization carries the trace. Infeasible means the stored design cannot be replayed.
# Selection order has to match the object-id suffix.
from spacedesigner.explain.hints import selection_from_design
from spacedesigner.optimizer.models import FeasibleOptimization

# Same placer Stage 2 used. Hints are not needed to recover an optimal placement.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Style scores reproduce the aesthetics term Stage 2 wrote into the trace.
from spacedesigner.recommend.scoring import StyleScorer

# Locked records.
from spacedesigner.schemas import CatalogItem, Design, Requirement, SceneGraph


# Replay the placement and the aesthetics override that produced this design.
def recover_optimization(
    scene: SceneGraph,
    requirement: Requirement,
    design: Design,
    catalog: tuple[CatalogItem, ...],
    scorer: StyleScorer,
) -> FeasibleOptimization:
    """Return the feasible replay, or raise ValueError when the replay is not feasible."""
    # Purchased rows in the original placement order.
    selection = selection_from_design(design, catalog)
    # The point's weights, which can differ from the requirement row's weights.
    weighted = requirement.model_copy(update={"objective_weights": design.weights})
    # Stage 2's variant is the sorted item ids, including the empty string when nothing was bought.
    variant = "|".join(sorted(item.item_id for item in selection))
    # Stage 2 replaces the tag-overlap aesthetics term with the mean style score.
    if selection:
        # Scores for the requirement's style word.
        style_scores = scorer.style_scores(requirement.style)
        # Mean over the purchased rows, matching Stage 2.
        aesthetics = sum(style_scores[item.item_id] for item in selection) / len(selection)
    # Nothing purchased keeps the perfect aesthetics term Stage 2 uses.
    else:
        # The empty-selection value.
        aesthetics = 1.0
    # Replay. The design id formula depends on the scene, the requirement id, and the variant.
    result = optimize(
        scene,
        weighted,
        catalog,
        selection=selection,
        variant=variant,
        term_overrides={"aesthetics": aesthetics},
    )
    # A replay that the checker would reject cannot explain the stored design.
    if not isinstance(result, FeasibleOptimization):
        # The route turns this into HTTP 422.
        raise ValueError(result.reason)
    # The replayed trace.
    return result
