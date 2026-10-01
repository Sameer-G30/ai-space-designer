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


# Several purchases must use the room instead of one corner.
def test_several_items_spread_along_walls_with_the_chair_at_the_desk() -> None:
    """Put anchors on walls and the chair beside the desk."""
    # Four categories in one office.
    requirement = sample_requirement().model_copy(
        update={"must_have": ["desk", "chair", "shelf", "sofa"]}
    )
    # One compact row per category.
    catalog = tuple(sample_catalog(category=name)[0] for name in requirement.must_have)
    # Solve the real model.
    result = optimize(sample_scene(), requirement, catalog)
    # The room is large enough for four small pieces.
    assert result.feasible
    # Hard constraints still hold.
    assert audit_design(sample_scene(), requirement, result.design, result.bom) == []
    # Look up each placed piece.
    by_type = {obj.type: obj for obj in result.design.objects}
    # Footprint gap to the nearest wall, in metres.
    def wall_gap(obj) -> float:
        # Rotated floor edges.
        quarter = round(obj.rotation / 90.0) % 4
        # Swap edges on a quarter turn.
        swapped = quarter in {1, 3}
        # World length and width.
        length = obj.dimensions[1] if swapped else obj.dimensions[0]
        # The other edge.
        width = obj.dimensions[0] if swapped else obj.dimensions[1]
        # Air on each side.
        gaps = (
            obj.position[0] - length / 2,
            6.0 - (obj.position[0] + length / 2),
            obj.position[1] - width / 2,
            6.0 - (obj.position[1] + width / 2),
        )
        # The nearest wall.
        return min(gaps)
    # The three anchors sit on a wall, not in the middle of the floor.
    for name in ("desk", "shelf", "sofa"):
        # One grid cell of slack.
        assert wall_gap(by_type[name]) <= 0.1
    # They are not the same corner: at least two different nearest walls.
    nearest = set()
    # Record which side each anchor touches.
    for name in ("desk", "shelf", "sofa"):
        # This piece.
        obj = by_type[name]
        # Gap on each side, same order as above.
        quarter = round(obj.rotation / 90.0) % 4
        # Edges.
        swapped = quarter in {1, 3}
        # World length and width.
        length = obj.dimensions[1] if swapped else obj.dimensions[0]
        # The other edge.
        width = obj.dimensions[0] if swapped else obj.dimensions[1]
        # Named gaps.
        sides = {
            "west": obj.position[0] - length / 2,
            "east": 6.0 - (obj.position[0] + length / 2),
            "south": obj.position[1] - width / 2,
            "north": 6.0 - (obj.position[1] + width / 2),
        }
        # The side it actually touches.
        nearest.add(min(sides, key=sides.get))
    # Three walls are assigned before a wall is reused.
    assert len(nearest) == 3
    # The chair is next to the desk, not across the room.
    desk = by_type["desk"]
    # The companion.
    chair = by_type["chair"]
    # Manhattan distance between centres.
    apart = abs(desk.position[0] - chair.position[0]) + abs(desk.position[1] - chair.position[1])
    # Close enough to read as a desk and its chair.
    assert apart < 2.0


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
