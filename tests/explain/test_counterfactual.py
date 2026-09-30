"""Warm-start hints and counterfactual solves on the small Phase 3 fixture."""

# Catalog rows for a forced expensive-to-cheap swap.
# The what-if planner. It does not touch a database.
from spacedesigner.explain.counterfactual import prepare_counterfactual
from spacedesigner.explain.hints import hints_from_design
from spacedesigner.explain.models import CounterfactualDesign, CounterfactualRequest

# Stage 1, with and without hints.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Deterministic style scores. No CLIP weights.
from spacedesigner.recommend.scoring import load_style_scorer
from spacedesigner.schemas import CatalogItem

# Shared fixtures.
from tests.phase3_samples import sample_catalog, sample_requirement, sample_scene
from tests.recommend.fakes import FakeEmbedder


# A scorer over the rows a test is using.
def _scorer(catalog: tuple[CatalogItem, ...], tmp_path) -> object:
    """Build a tag-or-fake scorer that does not load CLIP."""
    # Fake vectors, cached under the test tmp directory.
    return load_style_scorer(catalog, FakeEmbedder(), tmp_path / "clip.npz", ("modern",))


# Hints from a solved design reproduce that design.
def test_hints_keep_the_same_placement(tmp_path) -> None:
    """A warm start of an unchanged model returns the same centres."""
    # Spacious room and one desk.
    scene = sample_scene()
    # Budget that covers the sample desk.
    requirement = sample_requirement()
    # One catalog row.
    catalog = sample_catalog()
    # Cold solve.
    first = optimize(scene, requirement, catalog)
    # The fixture is feasible.
    assert first.feasible is True
    # Cell hints from the centres the solver just chose.
    hints = hints_from_design(first.design, catalog)
    # One purchased desk.
    assert len(hints) == 1
    # Warm start.
    second = optimize(scene, requirement, catalog, hints=hints)
    # Still feasible.
    assert second.feasible is True
    # Same object ids and centres.
    assert [obj.id for obj in second.design.objects] == [obj.id for obj in first.design.objects]
    # Centres match exactly on this grid.
    for left, right in zip(first.design.objects, second.design.objects, strict=True):
        # X.
        assert left.position[0] == right.position[0]
        # Y.
        assert left.position[1] == right.position[1]


# A hint outside the room is repaired. The no-hint path is not what this test calls.
def test_bad_hint_still_returns_a_design() -> None:
    """An impossible hint does not make a feasible room infeasible."""
    # The same spacious fixture.
    scene = sample_scene()
    # One desk.
    requirement = sample_requirement()
    # One row.
    catalog = sample_catalog()
    # A start cell far outside the room, rotation 0.
    hints = {"test-desk": (-20, -20, 0)}
    # Solve with that hint.
    result = optimize(scene, requirement, catalog, hints=hints)
    # Repair finds the feasible placement.
    assert result.feasible is True


# Two desks so a lower budget must swap the selected row.
def _two_desks() -> tuple[CatalogItem, CatalogItem]:
    """Return a cheap desk and an expensive desk."""
    # Cheap row.
    cheap = CatalogItem.model_validate(
        {
            "item_id": "desk-cheap",
            "category": "desk",
            "dims": {"length": 0.8, "width": 0.5, "height": 0.75},
            "price": 1000.0,
            "style_tags": ["modern"],
            "material": "solid_wood",
            "embedding": None,
        }
    )
    # Expensive row of the same category.
    expensive = CatalogItem.model_validate(
        {
            "item_id": "desk-expensive",
            "category": "desk",
            "dims": {"length": 0.9, "width": 0.6, "height": 0.75},
            "price": 5000.0,
            "style_tags": ["modern"],
            "material": "metal",
            "embedding": None,
        }
    )
    # Cheap first in the tuple. The selection argument overrides that order.
    return cheap, expensive


# A higher budget keeps the item, passes a hint, and reports sensitivity.
def test_higher_budget_is_warm_started_and_reports_sensitivity(tmp_path) -> None:
    """Budget plus 10 percent keeps the desk and returns score change over budget change."""
    # Fixture.
    scene = sample_scene()
    # Budget 10000.
    requirement = sample_requirement()
    # One desk at 1000.
    catalog = sample_catalog()
    # Scorer for the aesthetics override.
    scorer = _scorer(catalog, tmp_path)
    # Place the desk.
    solved = optimize(scene, requirement, catalog, term_overrides={"aesthetics": 1.0})
    # Feasible.
    assert solved.feasible is True
    # Ten percent more budget.
    request = CounterfactualRequest(budget_inr=11000.0)
    # Warm start.
    prepared = prepare_counterfactual(
        scene, requirement, solved.design, request, catalog, scorer, use_hints=True
    )
    # Feasible what-if.
    assert isinstance(prepared.result, CounterfactualDesign)
    # The desk was hinted.
    assert prepared.result.hint_count == 1
    assert prepared.result.warm_started is True
    # Same object, so nothing was added, removed, or moved.
    assert prepared.result.diff["items_added"] == []
    assert prepared.result.diff["items_removed"] == []
    assert prepared.result.diff["items_moved"] == []
    # The price did not change.
    assert prepared.result.cost_change == 0.0
    # The budget moved by 1000.
    assert prepared.result.budget_change_inr == 1000.0
    # Sensitivity is the score delta per rupee.
    assert prepared.result.sensitivity_score_per_inr is not None
    # It matches the two deltas.
    assert prepared.result.sensitivity_score_per_inr == (
        prepared.result.score_change / prepared.result.budget_change_inr
    )


# A budget below the current desk swaps in the cheaper desk.
def test_lower_budget_swaps_the_catalog_item(tmp_path) -> None:
    """A budget that cannot keep the expensive desk adds the cheap desk and removes the old one."""
    # Room.
    scene = sample_scene()
    # Budget that can buy the expensive desk.
    requirement = sample_requirement(budget=8000.0)
    # Both rows.
    cheap, expensive = _two_desks()
    # Catalog tuple.
    catalog = (cheap, expensive)
    # Force the expensive row so the later repair has something to swap.
    solved = optimize(
        scene,
        requirement,
        catalog,
        selection=[expensive],
        term_overrides={"aesthetics": 1.0},
    )
    # Feasible at 5000.
    assert solved.feasible is True
    assert solved.design.cost == 5000.0
    # Scorer.
    scorer = _scorer(catalog, tmp_path)
    # New budget fits only the cheap desk.
    request = CounterfactualRequest(budget_inr=2000.0)
    # Re-solve.
    prepared = prepare_counterfactual(scene, requirement, solved.design, request, catalog, scorer)
    # Feasible.
    assert isinstance(prepared.result, CounterfactualDesign)
    # The new cost is the cheap desk.
    assert prepared.result.design.cost == 1000.0
    # The expensive object id is gone and the cheap one is present.
    assert prepared.result.diff["items_removed"]
    assert prepared.result.diff["items_added"]
    # The removed id mentions the expensive item.
    assert any("desk-expensive" in item_id for item_id in prepared.result.diff["items_removed"])
    # The added id mentions the cheap item.
    assert any("desk-cheap" in item_id for item_id in prepared.result.diff["items_added"])


# A longer room does not overwrite the scene id used by the parent.
def test_room_change_uses_a_new_scene_id(tmp_path) -> None:
    """Editing the length returns a design whose scene id is not the parent's."""
    # Original 6 m room.
    scene = sample_scene()
    # One desk.
    requirement = sample_requirement()
    # One row.
    catalog = sample_catalog()
    # Scorer.
    scorer = _scorer(catalog, tmp_path)
    # Place it.
    solved = optimize(scene, requirement, catalog, term_overrides={"aesthetics": 1.0})
    # Feasible.
    assert solved.feasible is True
    # Shorten the room. 4 m still holds a 0.8 m desk.
    request = CounterfactualRequest(length_m=4.0)
    # Re-solve.
    prepared = prepare_counterfactual(scene, requirement, solved.design, request, catalog, scorer)
    # Feasible.
    assert isinstance(prepared.result, CounterfactualDesign)
    # New scene id.
    assert prepared.result.scene.scene_id != scene.scene_id
    # The new length is the one requested.
    assert prepared.result.scene.dimensions.length == 4.0
    # The parent design id is recorded.
    assert prepared.result.design.parent_design_id == solved.design.design_id
