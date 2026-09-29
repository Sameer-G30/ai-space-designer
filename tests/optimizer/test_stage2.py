"""Stage 2 Pareto tests."""

# Independent audit used on every returned design.
from spacedesigner.critic import audit_design

# The real 26-item... catalog and Stage 2 under test.
from spacedesigner.data.synthetic import generate
from spacedesigner.optimizer.catalog import load_catalog
from spacedesigner.optimizer.models import InfeasibleOptimization, ParetoOptimization
from spacedesigner.optimizer.stage2_pareto import (
    AXES,
    dominates,
    optimize_pareto,
    weight_sweep,
)

# Fake embedder keeps tests off the real weights.
from spacedesigner.recommend.scoring import load_style_scorer
from spacedesigner.schemas import Requirement, SceneGraph
from tests.phase3_samples import sample_requirement, sample_scene
from tests.recommend.fakes import FakeEmbedder


# Scorer built from the real catalog with the fake embedder in a throwaway cache.
def _scorer(tmp_path):
    """Return a deterministic scorer."""
    # Cache under pytest's temporary directory.
    return load_style_scorer(load_catalog(), FakeEmbedder(), tmp_path / "c.npz", ("modern",))


# Two required categories give a richer sweep.
def _requirement(budget: float = 400000.0) -> Requirement:
    """Return a two-category requirement."""
    # Start from the desk sample and add a chair.
    base = sample_requirement("desk", budget=budget)
    # Copy with two categories.
    return base.model_copy(update={"must_have": ["desk", "sofa"]})


# The weight sweep contains the user's weights and 26 grid vectors.
def test_weight_sweep_size() -> None:
    """Return 27 vectors."""
    # 1 own + 3^3 - 1.
    assert len(weight_sweep(sample_requirement())) == 27


# Dominance is strict and irreflexive.
def test_dominates_semantics() -> None:
    """A vector never dominates itself or an equal vector."""
    # Six equal terms.
    a = dict.fromkeys(AXES, 0.5)
    # Slightly better on one axis.
    b = {**a, "budget": 0.6}
    # Equal vectors do not dominate.
    assert not dominates(a, a)
    # Better on one axis and equal elsewhere dominates.
    assert dominates(b, a) and not dominates(a, b)


# No returned point is dominated, and every point is hard-clean.
def test_pareto_set_is_non_dominated_and_audited(tmp_path) -> None:
    """Check dominance, audit, budget, labels, BOM and design ids."""
    # Solve the two-category requirement.
    result = optimize_pareto(sample_scene(), _requirement(), scorer=_scorer(tmp_path))
    # It must be feasible.
    assert isinstance(result, ParetoOptimization)
    # Between one and eight points, and the sweep found several.
    assert 1 <= len(result.points) <= 8
    # Term vectors.
    terms = [p.trace.objective_terms.model_dump() for p in result.points]
    # No point is dominated by another.
    for i, a in enumerate(terms):
        # Compare with every other point.
        for j, b in enumerate(terms):
            # Skip itself.
            if i != j:
                # Dominance must be false.
                assert not dominates(b, a)
    # Hard checks on each design.
    for point in result.points:
        # Independent checker reports nothing.
        assert audit_design(sample_scene(), _requirement(), point.design, point.bom) == []
        # Budget is never exceeded.
        assert point.design.cost <= 400000.0
        # BOM total equals cost.
        assert abs(sum(line.line_total for line in point.bom) - point.design.cost) < 1e-6
        # Trace stays beside the design.
        assert point.trace.design_id == point.design.design_id
    # Design ids are unique.
    assert len({p.design.design_id for p in result.points}) == len(result.points)
    # The named labels exist.
    labels = {label for p in result.points for label in p.labels}
    # Cheapest, balanced, premium and most sustainable are all present.
    assert {"cheapest", "balanced", "premium", "most_sustainable"} <= labels
    # Cheapest is no costlier than premium.
    costs = {label: p.design.cost for p in result.points for label in p.labels}
    assert costs["cheapest"] <= costs["premium"]


# Different weights must change which item is chosen.
def test_weights_change_item_selection(tmp_path) -> None:
    """More than one distinct selection is placed."""
    # Solve with the real catalog and fake vectors.
    result = optimize_pareto(sample_scene(), _requirement(), scorer=_scorer(tmp_path))
    # Distinct selections were evaluated and designs differ in cost.
    assert result.candidates_evaluated > 1 and len({p.design.cost for p in result.points}) > 1


# A budget below the cheapest selection stays a readable no-design outcome.
def test_infeasible_budget_has_reason_and_no_design(tmp_path) -> None:
    """Return the Stage 1 reason, not a design."""
    # One rupee cannot buy a desk.
    result = optimize_pareto(sample_scene(), _requirement(budget=1.0), scorer=_scorer(tmp_path))
    # Infeasible with a readable message.
    assert isinstance(result, InfeasibleOptimization) and result.reason.strip()


# Generated rooms: every feasible room yields audited, non-dominated sets.
def test_generated_rooms_hold_invariants(tmp_path) -> None:
    """Run a small fixed-seed sample."""
    # Twenty rooms keep the test quick.
    scenes, requirements = generate(20, seed=20260930)
    # Shared scorer.
    scorer = _scorer(tmp_path)
    # Evaluate each pair.
    for scene_data, req_data in zip(scenes, requirements, strict=True):
        # Validate the pair.
        scene, req = SceneGraph.model_validate(scene_data), Requirement.model_validate(req_data)
        # Solve.
        result = optimize_pareto(scene, req, scorer=scorer)
        # Infeasible rooms only need a reason.
        if not result.feasible:
            # Readable reason.
            assert result.reason.strip()
            # Next room.
            continue
        # Audit every point and check dominance.
        terms = [p.trace.objective_terms.model_dump() for p in result.points]
        # Loop over points.
        for i, point in enumerate(result.points):
            # No violations and no breach.
            assert audit_design(scene, req, point.design, point.bom) == []
            assert point.design.cost <= req.budget_inr + 1e-6
            # Not dominated by any sibling.
            assert not any(dominates(terms[j], terms[i]) for j in range(len(terms)) if j != i)
