"""Version diff correctness. These designs are constructed, not solved."""

# Locked design and object records.
# The diff helpers under test.
from spacedesigner.explain.versions import change_diff, initial_diff
from spacedesigner.schemas import Design


# One design with the given objects, cost, and score.
def _design(design_id: str, objects: list[dict], cost: float, score: float) -> Design:
    """Validate a small design."""
    # Every locked field is filled. Weights are a flat one vector.
    return Design.model_validate(
        {
            "design_id": design_id,
            "scene_id": "scene-diff",
            "requirement_id": "requirement-diff",
            "weights": {
                "layout": 1.0,
                "circulation": 1.0,
                "ergonomics": 1.0,
                "budget": 1.0,
                "aesthetics": 1.0,
                "sustainability": 1.0,
            },
            "score": score,
            "cost": cost,
            "objects": objects,
            "parent_design_id": None,
        }
    )


# One kept chair at a centre.
def _chair(object_id: str, x: float, y: float) -> dict:
    """Return one scene object payload."""
    # A square chair.
    return {
        "id": object_id,
        "type": "chair",
        "position": [x, y],
        "rotation": 0.0,
        "dimensions": [0.5, 0.5, 0.9],
        "movable": True,
        "must_keep": False,
        "confidence": "high",
    }


# The snapshot diff adds every object and changes nothing else.
def test_initial_diff_adds_every_object() -> None:
    """Version 1 reports the current objects as additions."""
    # Two objects.
    design = _design("design-a", [_chair("a", 1.0, 1.0), _chair("b", 2.0, 1.0)], 100.0, 0.5)
    # Snapshot.
    diff = initial_diff(design)
    # Both ids are additions.
    assert diff["items_added"] == ["a", "b"]
    # Nothing was removed or moved.
    assert diff["items_removed"] == []
    assert diff["items_moved"] == []
    # No earlier design to subtract.
    assert diff["cost_change"] == 0.0
    assert diff["score_change"] == 0.0


# Added, removed, moved, and the two numeric deltas.
def test_change_diff_reports_add_remove_move_and_deltas() -> None:
    """A second design reports each kind of object change and both deltas."""
    # Parent: chair a at (1, 1) and chair b at (2, 1).
    before = _design("design-a", [_chair("a", 1.0, 1.0), _chair("b", 2.0, 1.0)], 100.0, 0.4)
    # Child: chair a moved, chair b removed, chair c added.
    after = _design("design-b", [_chair("a", 1.5, 1.0), _chair("c", 3.0, 1.0)], 140.0, 0.55)
    # Diff.
    diff = change_diff(before, after)
    # c is new.
    assert diff["items_added"] == ["c"]
    # b is gone.
    assert diff["items_removed"] == ["b"]
    # a moved. The entry keeps both centres.
    moved = diff["items_moved"]
    # One move.
    assert isinstance(moved, list)
    assert len(moved) == 1
    # The moved id and the two centres.
    assert moved[0]["id"] == "a"
    assert moved[0]["from_position"] == [1.0, 1.0]
    assert moved[0]["to_position"] == [1.5, 1.0]
    # Deltas are the differences. Score subtraction is a binary float.
    assert diff["cost_change"] == 40.0
    assert abs(diff["score_change"] - 0.15) < 1e-9
    # The diff names both designs.
    assert diff["parent_design_id"] == "design-a"
    assert diff["result_design_id"] == "design-b"
