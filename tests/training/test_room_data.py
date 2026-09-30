"""Phase 7a tests: torch-free helpers only. No weights are downloaded and nothing trains."""

# Skip when the cleaned export is not on disk.
import pytest

# Helpers under test.
from spacedesigner.data.taxonomy import ROOM_TYPES
from spacedesigner.training import detector
from spacedesigner.training.room_data import (
    PROCESSED_DIR,
    confusion_matrix,
    load_split,
    summarize_confusion,
)


# A hand-made matrix checks the maths.
def test_confusion_and_summary() -> None:
    """Three of four predictions are right; one bedroom is called a kitchen."""
    # Class ids: bedroom and kitchen from the locked taxonomy.
    bed, kit = ROOM_TYPES.index("bedroom"), ROOM_TYPES.index("kitchen")
    # Truth and predictions.
    matrix = confusion_matrix([bed, bed, kit, kit], [bed, kit, kit, kit], len(ROOM_TYPES))
    # Summarize.
    summary = summarize_confusion(matrix)
    # Top-1 is 3 of 4.
    assert summary["top1"] == 0.75
    # Bedroom recall is 1 of 2.
    assert summary["per_class_recall"]["bedroom"] == 0.5
    # The single confusion is reported.
    assert summary["top_confusions"][0] == {"true": "bedroom", "predicted": "kitchen", "count": 1}


# Unknown split names must fail loudly.
def test_load_split_rejects_unknown() -> None:
    """A typo in the split name raises instead of returning nothing."""
    # Expect ValueError.
    with pytest.raises(ValueError):
        load_split("holdout")


# Real manifest: no path appears in two splits.
@pytest.mark.skipif(
    not (PROCESSED_DIR / "room_types" / "manifest.jsonl").exists(), reason="export missing"
)
def test_room_splits_disjoint() -> None:
    """Official splits share no image."""
    # Load all three splits.
    sets = [{str(p) for p, _ in load_split(s)} for s in ("train", "val", "test")]
    # Pairwise disjoint.
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])


# The generated detector yaml keeps the locked class order.
@pytest.mark.skipif(
    not (PROCESSED_DIR / "sun_rgbd" / "train.txt").exists(), reason="export missing"
)
def test_detector_yaml_matches_taxonomy(tmp_path, monkeypatch) -> None:
    """Class ids follow FURNITURE_CLASSES exactly."""
    # Redirect output so the test does not touch models/.
    monkeypatch.setattr(detector, "DETECTOR_DIR", tmp_path)
    monkeypatch.setattr(detector, "DATA_YAML", tmp_path / "data.yaml")
    # Write the yaml.
    text = detector.write_data_yaml().read_text(encoding="utf-8")
    # First and last classes.
    assert "  0: bed" in text and "  25: window" in text
    # Exactly 26 names.
    assert text.count("\n  ") == 26
