"""Tests for the real CP-SAT Stage 1 optimizer."""

# Independent critic verifies successful solver output.
from spacedesigner.critic import audit_design

# Real optimizer entry point remains unmocked.
from spacedesigner.optimizer import optimize

# Small validated records keep each test focused.
from tests.phase3_samples import sample_catalog, sample_requirement, sample_scene


# Confirm a compact required item is placed feasibly.
def test_feasible_tiny_catalog_item_has_clean_audit() -> None:
    """Solve one feasible room with the real CP-SAT model."""
    # Build the room.
    scene = sample_scene()
    # Build the gold requirement.
    requirement = sample_requirement()
    # Solve against a one-row catalog.
    result = optimize(scene, requirement, sample_catalog())
    # Require a design rather than an infeasible fallback.
    assert result.feasible
    # Require exact independent hard-constraint compliance.
    assert audit_design(scene, requirement, result.design, result.bom) == []
    # Require deterministic accounting.
    assert sum(line.line_total for line in result.bom) == result.design.cost


# Confirm retained poses are copied without normalization.
def test_must_keep_object_stays_at_180_degree_pose() -> None:
    """Keep a retained scene object exactly fixed."""
    # Include the retained object in the source scene.
    scene = sample_scene(with_fixed=True)
    # Require the same fixed chair and no additional chair purchase.
    requirement = sample_requirement(category="chair", keep_fixed=True)
    # Solve with a catalog that should not be selected.
    result = optimize(scene, requirement, sample_catalog(category="chair"))
    # Require a feasible output.
    assert result.feasible
    # Locate the retained output by stable identifier.
    retained = next(obj for obj in result.design.objects if obj.id == "fixed-chair")
    # Preserve its exact position.
    assert retained.position == [4.5, 4.5]
    # Preserve the non-new-item rotation.
    assert retained.rotation == 180
    # Require no purchased BOM row.
    assert result.bom == []


# Confirm hard budget failures never leak a design.
def test_infeasible_budget_has_readable_reason() -> None:
    """Return no design when the cheapest item exceeds budget."""
    # Solve a requirement with a deliberately tiny budget.
    result = optimize(
        sample_scene(),
        sample_requirement(budget=10.0),
        sample_catalog(price=1000.0),
    )
    # Require the explicit failed variant.
    assert not result.feasible
    # Require a useful budget explanation.
    assert "exceeds budget" in result.reason
