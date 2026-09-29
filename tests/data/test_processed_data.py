"""Validate the exported Phase 2a data: no NaN, boxes in bounds, classes in taxonomy, no leakage."""

# Hashes Places files to prove no byte-identical image sits in two splits.
import hashlib

# Array checks.
import numpy as np

# Skip when the cleaned data has not been generated on this machine.
import pytest

# Image decode.
from PIL import Image

# Paths and readers.
from spacedesigner.data.common import processed_dir, read_json, read_jsonl, repo_root

# Taxonomy bounds.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES, ROOM_TYPES

# Where the cleaners write (not created by this import; see helper below).
PROCESSED = repo_root() / "datasets" / "processed"

# Every test needs the processed tree.
pytestmark = pytest.mark.skipif(
    not (PROCESSED / "sun_rgbd" / "manifest.jsonl").is_file(),
    reason="datasets/processed has not been generated (run scripts/clean_*.py)",
)


# SUN RGB-D rows and label files, loaded once.
@pytest.fixture(scope="module")
def sun_rows() -> list[dict]:
    """Return the SUN RGB-D manifest."""
    # Manifest written by the cleaner.
    return read_jsonl(processed_dir("sun_rgbd") / "manifest.jsonl")


# YOLO labels: every box inside the image, every class in the taxonomy, no NaN.
def test_sun_yolo_labels_are_in_bounds_and_in_taxonomy(sun_rows: list[dict]) -> None:
    """Each YOLO line has a valid class id and a box fully inside [0, 1]."""
    # Root of the SUN export.
    root = PROCESSED / "sun_rgbd"
    # Count boxes so an empty export cannot pass.
    total = 0
    # Only rows with labels have a file.
    for row in (r for r in sun_rows if r["n_boxes"] > 0):
        # Label path for the row.
        path = root / "labels" / row["split"] / f"{row['id']}.txt"
        # Every line is one box.
        for line in path.read_text(encoding="utf-8").splitlines():
            # Five fields.
            cls, xc, yc, bw, bh = line.split()
            # Class id inside the taxonomy.
            assert 0 <= int(cls) < len(FURNITURE_CLASSES)
            # Numbers are finite floats.
            values = np.array([xc, yc, bw, bh], dtype=float)
            # No NaN or inf.
            assert np.all(np.isfinite(values))
            # Positive size.
            assert values[2] > 0 and values[3] > 0
            # Corners stay inside the image (tiny tolerance for rounding).
            assert values[0] - values[2] / 2 >= -1e-5 and values[0] + values[2] / 2 <= 1 + 1e-5
            # Same for y.
            assert values[1] - values[3] / 2 >= -1e-5 and values[1] + values[3] / 2 <= 1 + 1e-5
            # Count it.
            total += 1
    # The export must contain boxes and match the manifest count.
    assert total == sum(r["n_boxes"] for r in sun_rows) > 0


# Images and split lists must never overlap.
def test_sun_no_image_in_two_splits(sun_rows: list[dict]) -> None:
    """Each image id, path, and list entry appears in exactly one split."""
    # Ids unique.
    assert len({r["id"] for r in sun_rows}) == len(sun_rows)
    # Paths unique.
    assert len({r["image_path"] for r in sun_rows}) == len(sun_rows)
    # Split lists.
    lists = {
        split: set((PROCESSED / "sun_rgbd" / f"{split}.txt").read_text(encoding="utf-8").split())
        for split in ("train", "val", "test")
    }
    # Pairwise disjoint.
    assert not lists["train"] & lists["val"]
    # Train and test.
    assert not lists["train"] & lists["test"]
    # Val and test.
    assert not lists["val"] & lists["test"]
    # SUN3D frames of one location never straddle splits.
    location_splits: dict[str, set[str]] = {}
    # Group rows by location.
    for row in sun_rows:
        # Only SUN3D sequences have shared locations.
        if "/sun3ddata/" in row["sequence"]:
            # Track the splits seen per location.
            location_splits.setdefault(row["sequence"].rsplit("/", 1)[0], set()).add(row["split"])
    # One split per location.
    assert all(len(splits) == 1 for splits in location_splits.values())


# Test images with geometry files must have finite, readable depth.
def test_sun_test_geometry_files_are_valid(sun_rows: list[dict]) -> None:
    """Depth PNGs decode and layouts hold polygons for every flagged test image."""
    # Flagged rows.
    flagged = [r for r in sun_rows if r["has_test_geometry"]]
    # Only test images carry geometry.
    assert flagged and all(r["split"] == "test" for r in flagged)
    # Check a spread of rows.
    for row in flagged[:: max(1, len(flagged) // 40)]:
        # Folder for the row.
        geo = PROCESSED / "sun_rgbd" / "geometry" / "test" / row["id"]
        # Depth decodes to uint16.
        depth = np.asarray(Image.open(geo / "depth.png"))
        # Correct dtype and some data.
        assert depth.dtype == np.uint16 and depth.max() > 0
        # Layout has at least one polygon.
        layout = read_json(geo / "layout.json")
        # Polygon present.
        assert any(o and o.get("polygon") for o in layout["objects"])


# NYU: splits, NaN, ranges, and label ids.
def test_nyu_export_is_clean() -> None:
    """Official splits are disjoint and complete; sampled arrays have no NaN and valid ids."""
    # Manifest.
    rows = read_jsonl(PROCESSED / "nyu_depth_v2" / "manifest.jsonl")
    # Official counts: 795 train, 654 test.
    assert sum(r["split"] == "train" for r in rows) == 795
    # Test frames.
    assert sum(r["split"] == "test" for r in rows) == 654
    # Ids unique means no frame is in two splits.
    assert len({r["id"] for r in rows}) == len(rows) == 1449
    # Sample about 60 frames.
    for row in rows[:: max(1, len(rows) // 60)]:
        # Depth array.
        depth = np.load(PROCESSED / "nyu_depth_v2" / row["depth"])
        # No NaN and within range.
        assert not np.isnan(depth).any() and depth.min() >= 0.0 and depth.max() <= 10.0
        # Label map.
        labels = np.asarray(Image.open(PROCESSED / "nyu_depth_v2" / row["labels"]))
        # Ids are 0..len(classes) or 255 (unlabeled).
        assert set(np.unique(labels)) <= set(range(len(FURNITURE_CLASSES) + 1)) | {255}
        # Same size as depth.
        assert labels.shape == depth.shape


# Room-type set: labels in taxonomy, no leakage, SUN splits preserved.
def test_room_type_dataset_has_no_split_leakage(sun_rows: list[dict]) -> None:
    """Paths are unique, labels are known room types, and no Places file crosses splits."""
    # Manifest.
    rows = read_jsonl(PROCESSED / "room_types" / "manifest.jsonl")
    # Paths unique.
    assert len({r["path"] for r in rows}) == len(rows)
    # Labels in the 15 room types.
    assert {r["room_type"] for r in rows} <= set(ROOM_TYPES)
    # Label ids match the names.
    assert all(ROOM_TYPES[r["label"]] == r["room_type"] for r in rows)
    # SUN rows keep the detection split.
    sun_split = {r["id"]: r["split"] for r in sun_rows}
    # Compare each SUN row.
    assert all(sun_split[r["name"]] == r["split"] for r in rows if r["source"] == "sun_rgbd")
    # Byte hashes per split for the Places files.
    seen: dict[str, str] = {}
    # Every Places row.
    for row in (r for r in rows if r["source"] == "places365_val"):
        # Hash the copied file.
        digest = hashlib.md5((PROCESSED / row["path"]).read_bytes()).hexdigest()
        # Same bytes must not appear under two splits.
        assert seen.setdefault(digest, row["split"]) == row["split"]
    # Every split is used.
    assert {r["split"] for r in rows} == {"train", "val", "test"}


# CubiCasa: official splits, valid masks.
def test_cubicasa_export_keeps_official_splits() -> None:
    """Plans are unique, split names are official, and masks use known ids."""
    # Manifest.
    rows = read_jsonl(PROCESSED / "cubicasa5k" / "manifest.jsonl")
    # Unique plan ids mean no plan is in two splits.
    assert len({r["id"] for r in rows}) == len(rows)
    # Splits are the official three.
    assert {r["split"] for r in rows} == {"train", "val", "test"}
    # Room ids from the vocabulary.
    room_ids = read_json(PROCESSED / "cubicasa5k" / "room_classes.json")
    # Sample masks.
    for row in rows[:: max(1, len(rows) // 40)]:
        # Every floor has one structure mask; some plans have no floor 1, so glob them.
        masks = sorted(
            (PROCESSED / "cubicasa5k" / row["split"] / "masks").glob(
                f"{row['id']}_F*_structure.png"
            )
        )
        # One mask per floor.
        assert len(masks) == row["n_floors"]
        # Base path of the first floor's mask pair.
        base = str(masks[0])[: -len("_structure.png")]
        # Values 0..3.
        structure = np.asarray(Image.open(f"{base}_structure.png"))
        # Only wall, door, window, background.
        assert set(np.unique(structure)) <= {0, 1, 2, 3}
        # Room ids stay inside the vocabulary.
        rooms = np.asarray(Image.open(f"{base}_rooms.png"))
        # Known ids.
        assert set(np.unique(rooms)) <= set(room_ids.values())
        # Same raster size.
        assert rooms.shape == structure.shape
    # Every plan has geometry.
    assert all(r["n_walls"] > 0 and r["n_rooms"] > 0 for r in rows)


# Structured3D: honest completeness flags and finite dimensions.
def test_structured3d_export_is_label_only() -> None:
    """No scene claims images; room dimensions are finite and positive."""
    # Scene rows.
    scenes = read_jsonl(PROCESSED / "structured3d" / "scenes.jsonl")
    # Official ranges give 3000/250/250.
    counts = {s: sum(r["split"] == s for r in scenes) for s in ("train", "val", "test")}
    # Compare.
    assert counts == {"train": 3000, "val": 250, "test": 250}
    # No scene may claim photo or depth files.
    assert not any(
        r["has_perspective_rgb"] or r["has_depth"] or r["complete_for_photo_or_depth_check"]
        for r in scenes
    )
    # Room rows.
    rooms = read_jsonl(PROCESSED / "structured3d" / "rooms.jsonl")
    # Finite positive dimensions.
    for key in ("width_mm", "length_mm", "height_mm", "hull_area_m2"):
        # Values.
        values = np.array([r[key] for r in rooms], dtype=float)
        # Finite and positive.
        assert np.all(np.isfinite(values)) and np.all(values > 0)
