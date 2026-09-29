"""Unit tests for the cleaning rules, using tiny synthetic inputs (no dataset files needed)."""

# Image builder for the hash test.
import numpy as np

# Synthetic pictures.
from PIL import Image

# Shared helpers under test.
from spacedesigner.data.common import dhash, find_near_duplicates, stratified_group_split

# CubiCasa polygon rules under test.
from spacedesigner.data.cubicasa import parse_plan, polygon_area

# NYU depth mask under test.
from spacedesigner.data.nyu import mask_depth

# Box rules under test.
from spacedesigner.data.sun_rgbd import clean_boxes, to_yolo_lines

# A 640x480 image used by the box tests.
W, H = 640, 480


# Helper: run one box through the cleaner and return (kept, reasons).
def one(label: str, box: list[float]):
    """Clean a single MATLAB-style box."""
    # Drop the clip count; tests read it separately where needed.
    kept, reasons, _ = clean_boxes([(label, box)], W, H)
    # Give the results back.
    return kept, reasons


# A normal box passes and converts from 1-based to 0-based.
def test_valid_box_is_kept_and_shifted() -> None:
    """A clean chair box stays and shifts by one pixel."""
    # 100 wide, 100 tall at MATLAB (11, 21).
    kept, reasons = one("chair", [11, 21, 100, 100])
    # One kept box.
    assert len(kept) == 1 and not reasons
    # Class id 3 is chair; x0=10, y0=20.
    assert kept[0] == (3, 10.0, 20.0, 110.0, 120.0)


# Each bad-box reason is reported.
def test_bad_boxes_are_dropped_with_reasons() -> None:
    """Unmapped, NaN, degenerate, tiny, and out-of-bounds boxes are dropped."""
    # Not in the taxonomy.
    assert one("paper", [10, 10, 50, 50])[1] == {"unmapped_class": 1}
    # NaN coordinates.
    assert one("chair", [float("nan"), 10, 50, 50])[1] == {"non_finite": 1}
    # Zero width.
    assert one("chair", [10, 10, 0, 50])[1] == {"degenerate": 1}
    # Negative height.
    assert one("chair", [10, 10, 50, -5])[1] == {"degenerate": 1}
    # Three pixels wide.
    assert one("chair", [10, 10, 3, 60])[1] == {"tiny": 1}
    # Mostly outside the image.
    assert one("chair", [600, 10, 200, 50])[1] == {"out_of_bounds": 1}


# A hair of overshoot is clipped rather than dropped.
def test_small_overshoot_is_clipped_inside_the_image() -> None:
    """A box that pokes 2 px past the edge is clipped and stays in bounds."""
    # Runs to x = 641.
    kept, reasons, clipped = clean_boxes([("desk", [540, 100, 102, 100])], W, H)
    # Kept and counted as clipped.
    assert len(kept) == 1 and clipped == 1 and not reasons
    # Right edge sits on the image edge.
    assert kept[0][3] == W


# Same class and near-identical box is a duplicate; a different class is not.
def test_duplicate_boxes_are_dropped() -> None:
    """Identical same-class boxes collapse to one."""
    # Two identical chairs and one table on the same pixels.
    boxes = [
        ("chair", [50, 50, 100, 100]),
        ("chair", [50, 50, 100, 100]),
        ("table", [50, 50, 100, 100]),
    ]
    # Clean them.
    kept, reasons, _ = clean_boxes(boxes, W, H)
    # Chair once, table once.
    assert sorted(b[0] for b in kept) == [3, 7] and reasons == {"duplicate": 1}


# YOLO output must be normalised and finite.
def test_yolo_lines_are_normalised() -> None:
    """Every YOLO number lies in [0, 1] and the class id is an int."""
    # One clean box.
    kept, _ = one("bed", [1, 1, 640, 480])
    # Format it.
    (line,) = to_yolo_lines(kept, W, H)
    # Split the fields.
    fields = line.split()
    # Class id then four floats.
    assert fields[0] == "0" and all(0.0 <= float(v) <= 1.0 for v in fields[1:])


# Depth masking never leaves NaN.
def test_depth_mask_removes_zero_nan_and_out_of_range() -> None:
    """Invalid depth becomes 0.0 and valid depth is untouched."""
    # Zero, NaN, too near, valid, too far.
    raw = np.array([[0.0, np.nan, 0.2, 2.5, 11.0]], dtype=np.float32)
    # Mask it.
    masked = mask_depth(raw)
    # No NaN survives.
    assert not np.isnan(masked).any()
    # Only the valid reading remains.
    assert masked.tolist() == [[0.0, 0.0, 0.0, 2.5, 0.0]]


# Splits keep a group together and never repeat an item.
def test_group_split_never_leaks() -> None:
    """Every item gets one split and groups are not divided."""
    # 200 items in groups of 4 across two strata.
    items = [(f"i{n}", f"g{n // 4}", "a" if n < 100 else "b") for n in range(200)]
    # Split them.
    result = stratified_group_split(items)
    # Every item assigned.
    assert set(result) == {item[0] for item in items}
    # Each group sits in one split.
    for group in {item[1] for item in items}:
        # Splits used by the group.
        used = {result[item[0]] for item in items if item[1] == group}
        # Exactly one.
        assert len(used) == 1
    # All three splits are used.
    assert set(result.values()) == {"train", "val", "test"}


# Perceptual hashes catch a slightly changed copy but not a different image.
def test_near_duplicate_detection() -> None:
    """A brightened copy is a near-duplicate; a different pattern is not."""
    # Seeded gradient image.
    base = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (64, 1))
    # Same picture, slightly brighter.
    bright = np.clip(base.astype(int) + 8, 0, 255).astype(np.uint8)
    # A very different picture.
    other = base.T.copy()
    # Hash all three.
    hashes = [dhash(Image.fromarray(a)) for a in (base, bright, other)]
    # Only the brightened copy is dropped.
    assert find_near_duplicates(hashes, 4) == {1}


# CubiCasa polygon area and malformed-plan handling.
def test_cubicasa_area_and_malformed_plans() -> None:
    """A unit square has area 1; broken XML and empty plans are rejected."""
    # Unit square.
    assert polygon_area(np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)) == 1.0
    # Broken XML.
    plan, reasons = parse_plan(b"<svg")
    # No plan and a reason.
    assert plan is None and reasons["plan_xml_error"] == 1
    # Valid canvas but nothing on it.
    empty = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>'
    # No walls means malformed.
    plan, reasons = parse_plan(empty)
    # Rejected.
    assert plan is None and reasons["plan_no_walls"] == 1
