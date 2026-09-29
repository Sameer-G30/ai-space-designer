"""Taxonomy tests: sizes, synonym targets, and grounding in real dataset labels."""

# Skip tests whose source files are not on disk.
import pytest

# Paths to the tracked vocabularies and the raw category file.
from spacedesigner.data.common import cleaning_dir, raw_dir, read_json

# Taxonomy under test.
from spacedesigner.data.taxonomy import (
    FURNITURE_CLASSES,
    FURNITURE_SYNONYMS,
    NYU_SCENE_TO_ROOM,
    PLACES_INDOOR_CATEGORIES,
    ROOM_TYPES,
    SUN_SCENE_TO_ROOM,
    map_furniture,
    normalize_label,
)


# The plan asks for about 25 furniture classes and about 15 room types.
def test_taxonomy_sizes() -> None:
    """Class counts stay near the plan's targets."""
    # Furniture: about 25.
    assert 24 <= len(FURNITURE_CLASSES) <= 27
    # Rooms: about 15.
    assert len(ROOM_TYPES) == 15
    # Places categories: about 15-20.
    assert 15 <= len(PLACES_INDOOR_CATEGORIES) <= 20


# Duplicate names would make YOLO ids ambiguous.
def test_taxonomy_names_are_unique() -> None:
    """No class or room name repeats."""
    # Furniture names.
    assert len(set(FURNITURE_CLASSES)) == len(FURNITURE_CLASSES)
    # Room names.
    assert len(set(ROOM_TYPES)) == len(ROOM_TYPES)


# Every synonym must land on a real class, and every class must be reachable.
def test_synonyms_point_into_the_taxonomy() -> None:
    """All synonym targets are taxonomy classes and every class has a synonym."""
    # Targets are classes.
    assert set(FURNITURE_SYNONYMS.values()) <= set(FURNITURE_CLASSES)
    # Every class has at least one source label.
    assert set(FURNITURE_SYNONYMS.values()) == set(FURNITURE_CLASSES)
    # Synonym keys are already normalized.
    assert all(key == normalize_label(key) for key in FURNITURE_SYNONYMS)


# Room maps must only produce known room types.
def test_room_maps_use_known_room_types() -> None:
    """Places, SUN, and NYU room maps target the 15 room types."""
    # Places.
    assert set(PLACES_INDOOR_CATEGORIES.values()) <= set(ROOM_TYPES)
    # SUN.
    assert set(SUN_SCENE_TO_ROOM.values()) <= set(ROOM_TYPES)
    # NYU.
    assert set(NYU_SCENE_TO_ROOM.values()) <= set(ROOM_TYPES)


# The user's examples of synonym handling.
def test_known_synonyms_resolve() -> None:
    """Sofa/couch and night_stand/nightstand collapse to one class each."""
    # Couch is a sofa.
    assert map_furniture("Couch") == "sofa"
    # Both night stand spellings agree.
    assert map_furniture("night_stand") == map_furniture("Night Stand") == "nightstand"
    # SUN's endtable typo is handled.
    assert map_furniture("entable") == "side_table"
    # Unknown labels stay unmapped.
    assert map_furniture("paper") is None


# Synonyms must come from labels that really appear in SUN RGB-D or NYU.
def test_furniture_synonyms_are_grounded_in_dataset_labels() -> None:
    """Every synonym key appears in the SUN RGB-D 2D box labels or the NYU name list."""
    # SUN vocabulary written by the cleaner.
    sun = set(read_json(cleaning_dir() / "sun_rgbd_label_vocabulary.json")["normalized"])
    # NYU vocabulary written by the cleaner.
    nyu = set(read_json(cleaning_dir() / "nyu_label_vocabulary.json")["normalized"])
    # Keys missing from both.
    ungrounded = [key for key in FURNITURE_SYNONYMS if key not in sun | nyu]
    # None allowed.
    assert not ungrounded, f"synonyms not found in SUN or NYU labels: {ungrounded}"


# Places strings must be official, not invented.
def test_places_categories_are_official_strings() -> None:
    """Every chosen Places category is in categories_places365.txt."""
    # The official file.
    path = raw_dir("places365") / "categories_places365.txt"
    # Skip when the file is not on disk.
    if not path.is_file():
        # Nothing to compare against.
        pytest.skip("categories_places365.txt not on disk")
    # First column of each line.
    official = {line.split()[0] for line in path.read_text(encoding="utf-8").splitlines() if line}
    # All chosen strings exist.
    assert set(PLACES_INDOOR_CATEGORIES) <= official


# SUN scene strings must be real too.
def test_sun_scene_map_is_grounded() -> None:
    """Every mapped SUN scene string appears in the exported SUN summary."""
    # Summary written by the SUN cleaner.
    summary = read_json(cleaning_dir() / "sun_rgbd_summary.json")
    # Scenes seen in the data.
    seen = set(summary["scene_histogram"])
    # All mapped scenes exist.
    assert set(SUN_SCENE_TO_ROOM) <= seen
