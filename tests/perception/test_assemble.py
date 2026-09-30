"""Scaling, confidence, and scene assembly tests."""

# pytest raises.
import pytest

# Code under test.
from spacedesigner.perception.assemble import InvalidMeasurement, apply_scale, build_scene
from spacedesigner.schemas import Confidence, SceneGraph


# A worker-style result with a visible ceiling.
def result(ceiling: bool = True) -> dict:
    """Return an unscaled perception result."""
    # Room, one bed, one door.
    return {
        "room": {"length": 4.0, "width": 3.0, "height": 2.5, "ceiling_found": ceiling},
        "objects": [
            {"type": "bed", "score": 0.9, "footprint": [1.0, 3.0, 0.5, 2.0], "height": 0.6},
            {"type": "bed", "score": 0.8, "footprint": [-0.2, 0.3, 2.9, 3.4], "height": 0.5},
        ],
        "openings": [{"type": "door", "wall": "south", "position": 0.4, "width": 0.9}],
        "room_type": "bedroom",
    }


# Without a typed length the metric depth is used and every dimension is low.
def test_no_measurement_is_low_confidence() -> None:
    """Scale 1.0 and low on all three dimensions."""
    # Apply no measurement.
    scale, confidence = apply_scale(result()["room"], None, "length")
    # Metric depth is kept as is.
    assert scale == 1.0
    # All low.
    assert set(confidence.values()) == {Confidence.low}


# One typed length scales everything and gives high confidence.
def test_known_length_scales_and_gives_high_confidence() -> None:
    """A 5 m length on a 4 m estimate scales by 1.25."""
    # Anchor the length.
    scale, confidence = apply_scale(result()["room"], 5.0, "length")
    # Factor is typed divided by estimated.
    assert scale == pytest.approx(1.25)
    # All dimensions are high because the ceiling was found.
    assert set(confidence.values()) == {Confidence.high}


# A height from the no-ceiling fallback stays low even with a typed length.
def test_height_without_ceiling_stays_low() -> None:
    """The fallback height is not anchored."""
    # No ceiling found.
    _, confidence = apply_scale(result(ceiling=False)["room"], 5.0, "length")
    # Length and width are high.
    assert confidence["length"] == Confidence.high
    # Height stays low.
    assert confidence["height"] == Confidence.low


# Bad numbers are refused with a clear error.
@pytest.mark.parametrize(
    ("length", "axis"), [(0.0, "length"), (-1.0, "length"), (4.0, "depth"), (400.0, "length")]
)
def test_invalid_measurements_are_rejected(length: float, axis: str) -> None:
    """Zero, negative, unknown axis, and absurd ratios all raise."""
    # Each one is refused.
    with pytest.raises(InvalidMeasurement):
        apply_scale(result()["room"], length, axis)


# The assembled scene is valid, scaled, and labelled with the weakest confidence.
def test_build_scene_scales_objects_and_uses_weakest_confidence() -> None:
    """Scene fields follow the scale, and objects stay inside the room."""
    # Low confidence case.
    scene, per_dim, factor = build_scene(result(), "photo-1", 3)
    # Locked schema type.
    assert isinstance(scene, SceneGraph)
    # Version comes from the caller.
    assert scene.version == 3
    # Metric depth kept.
    assert factor == 1.0
    # Scene-level confidence is low.
    assert scene.dimensions.confidence == Confidence.low
    # Every dimension has its own label.
    assert set(per_dim) == {"length", "width", "height"}
    # Ids are unique per class.
    assert [o.id for o in scene.objects] == ["bed_1", "bed_2"]
    # Every object box fits inside the room.
    for obj in scene.objects:
        # Half sizes.
        hx, hy = obj.dimensions[0] / 2, obj.dimensions[1] / 2
        # Inside on x.
        assert hx - 1e-9 <= obj.position[0] <= scene.dimensions.length - hx + 1e-9
        # Inside on y.
        assert hy - 1e-9 <= obj.position[1] <= scene.dimensions.width - hy + 1e-9
    # The door is kept on its wall.
    assert scene.openings[0].wall == "south"
    # Scaled case.
    scaled, _, factor = build_scene(result(), "photo-1", 1, known_length_m=8.0)
    # Scale of two.
    assert factor == pytest.approx(2.0)
    # Room doubles.
    assert scaled.dimensions.length == pytest.approx(8.0)
    # Width doubles.
    assert scaled.dimensions.width == pytest.approx(6.0)
    # High confidence with a typed length and a found ceiling.
    assert scaled.dimensions.confidence == Confidence.high
