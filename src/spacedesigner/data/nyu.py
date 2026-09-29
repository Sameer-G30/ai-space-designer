"""Export NYU Depth V2 labeled data to PNG/npy with masked depth and taxonomy label maps."""

# Annotations on Python 3.11.
from __future__ import annotations

# HDF5 reader for the v7.3 .mat file.
import h5py

# Array math.
import numpy as np

# MATLAB v5 reader for splits.mat.
import scipy.io as sio

# PNG writer.
from PIL import Image

# Shared helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    histogram,
    processed_dir,
    raw_dir,
    require_free_space,
    write_json,
    write_jsonl,
)

# Taxonomy and mappers.
from spacedesigner.data.taxonomy import (
    FURNITURE_CLASSES,
    FURNITURE_INDEX,
    map_furniture,
    map_nyu_scene,
    normalize_label,
)

# Kinect v1 depth is trusted only inside this range (metres). Zero means "no reading".
MIN_DEPTH_M = 0.5

# Upper bound of the NYU depth range in metres.
MAX_DEPTH_M = 10.0

# Label-map value for pixels NYU left unlabeled.
UNLABELED = 255


def read_string(handle: h5py.File, ref: h5py.Reference) -> str:
    """Decode one MATLAB char array stored behind an HDF5 object reference."""
    # Characters are stored as code points in a column.
    return "".join(chr(int(c)) for c in handle[ref][:].flatten())


def mask_depth(raw: np.ndarray) -> np.ndarray:
    """Return float32 depth where 0 or out-of-range readings become 0.0 (never NaN)."""
    # Work in float32 on a copy.
    depth = np.asarray(raw, dtype=np.float32).copy()
    # Non-finite readings are invalid.
    depth[~np.isfinite(depth)] = 0.0
    # Below range or above range is invalid too.
    depth[(depth < MIN_DEPTH_M) | (depth > MAX_DEPTH_M)] = 0.0
    # Callers treat 0.0 as "invalid".
    return depth


def taxonomy_lookup(names: list[str]) -> np.ndarray:
    """Build a uint8 table: raw label id -> UNLABELED (0 only), 0 (other), or class index + 1."""
    # Table index is the raw id; NYU ids run from 1 to len(names).
    table = np.zeros(len(names) + 1, dtype=np.uint8)
    # Raw id 0 means unlabeled.
    table[0] = UNLABELED
    # Fill each named class.
    for raw_id, name in enumerate(names, start=1):
        # Map through the shared synonym table.
        mapped = map_furniture(name)
        # Unmapped classes stay 0 ("other").
        if mapped is not None:
            # Class ids are stored +1 so 0 can mean "other".
            table[raw_id] = FURNITURE_INDEX[mapped] + 1
    # Give the table back.
    return table


def run() -> dict:
    """Export every labeled NYU frame and return the stats."""
    # Source folder.
    source = raw_dir("nyu_depth_v2")
    # Output folder (gitignored).
    out = processed_dir("nyu_depth_v2")
    # 1449 frames of RGB, float32 depth, and labels is about 2.5 GB.
    require_free_space(out, 4 * 1024**3)
    # Official split indexes (1-based MATLAB).
    splits_mat = sio.loadmat(source / "splits.mat")
    # Train and test indexes converted to 0-based sets.
    train = {int(i) - 1 for i in splits_mat["trainNdxs"].flatten()}
    # Test indexes.
    test = {int(i) - 1 for i in splits_mat["testNdxs"].flatten()}
    # A frame in both splits would be leakage.
    assert not train & test, "official NYU splits overlap"
    # Open the labeled file read-only.
    handle = h5py.File(source / "nyu_depth_v2_labeled.mat", "r")
    # Raw class names (id = position + 1).
    names = [read_string(handle, ref) for ref in handle["names"][0]]
    # Lookup table from raw id to taxonomy id.
    table = taxonomy_lookup(names)
    # Scene names like kitchen_0004 and scene types like kitchen.
    scenes = [read_string(handle, ref) for ref in handle["scenes"][0]]
    # Scene types.
    scene_types = [read_string(handle, ref) for ref in handle["sceneTypes"][0]]
    # Number of frames.
    count = handle["images"].shape[0]
    # Every frame must be in exactly one official split.
    assert train | test == set(range(count)), "official splits do not cover all frames"
    # Rows for the manifest.
    rows: list[dict] = []
    # Pixels per taxonomy class, across the dataset.
    pixel_hist = np.zeros(len(FURNITURE_CLASSES), dtype=np.int64)
    # Fraction of invalid depth pixels, per frame.
    invalid_fractions: list[float] = []
    # Frames whose labels contain ids outside 0..len(names).
    bad_label_frames = 0
    # Export each frame.
    for index in range(count):
        # Split name from the official lists.
        split = "train" if index in train else "test"
        # Frame id.
        frame = f"nyu_{index:04d}"
        # Folder for this split.
        for kind in ("rgb", "depth", "labels", "labels_raw"):
            # Create each output folder.
            (out / split / kind).mkdir(parents=True, exist_ok=True)
        # HDF5 stores (3, W, H); transpose to (H, W, 3).
        rgb = np.asarray(handle["images"][index]).transpose(2, 1, 0)
        # Save the colour image as PNG.
        Image.fromarray(rgb).save(out / split / "rgb" / f"{frame}.png")
        # Raw Kinect depth (metres), transposed to (H, W); zeros are missing readings.
        depth = mask_depth(np.asarray(handle["rawDepths"][index]).T)
        # Save as float32 npy. 0.0 marks invalid pixels.
        np.save(out / split / "depth" / f"{frame}.npy", depth)
        # Fraction of pixels with no usable depth.
        invalid_fractions.append(float((depth == 0.0).mean()))
        # Raw label ids (uint16), transposed to (H, W).
        raw_labels = np.asarray(handle["labels"][index]).T
        # Ids beyond the name list would index past the table.
        if int(raw_labels.max()) > len(names):
            # Count and clamp the frame out of the export.
            bad_label_frames += 1
            # Skip the label export for this frame.
            continue
        # Save raw ids so nothing is lost.
        Image.fromarray(raw_labels.astype(np.uint16)).save(
            out / split / "labels_raw" / f"{frame}.png"
        )
        # Taxonomy map: 255 unlabeled, 0 other, k+1 furniture class.
        mapped = table[raw_labels]
        # Save as an 8-bit PNG.
        Image.fromarray(mapped).save(out / split / "labels" / f"{frame}.png")
        # Count pixels per taxonomy class.
        pixel_hist += np.bincount(
            mapped[(mapped > 0) & (mapped != UNLABELED)] - 1, minlength=len(FURNITURE_CLASSES)
        )
        # Room type from the NYU scene type.
        rows.append(
            {
                "id": frame,
                "split": split,
                "scene": scenes[index],
                "scene_type": scene_types[index],
                "room_type": map_nyu_scene(scene_types[index]),
                "rgb": f"{split}/rgb/{frame}.png",
                "depth": f"{split}/depth/{frame}.npy",
                "labels": f"{split}/labels/{frame}.png",
                "labels_raw": f"{split}/labels_raw/{frame}.png",
                "invalid_depth_fraction": round(invalid_fractions[-1], 6),
            }
        )
    # Close the file.
    handle.close()
    # Manifest for tests and later phases.
    write_jsonl(out / "manifest.jsonl", rows)
    # Raw ids that map into the taxonomy, with names, for the report.
    mapped_raw = {n: map_furniture(n) for n in names if map_furniture(n)}
    # Stats for the report.
    stats = {
        "frames": count,
        "frames_exported": len(rows),
        "frames_dropped_bad_labels": bad_label_frames,
        "split_frames": histogram([r["split"] for r in rows]),
        "raw_classes": len(names),
        "raw_classes_mapped_to_taxonomy": len(mapped_raw),
        "raw_classes_unmapped": len(names) - len(mapped_raw),
        "depth_valid_range_m": [MIN_DEPTH_M, MAX_DEPTH_M],
        "mean_invalid_depth_fraction": round(float(np.mean(invalid_fractions)), 4),
        "frames_with_over_half_invalid_depth": int(sum(f > 0.5 for f in invalid_fractions)),
        "pixels_per_taxonomy_class": {
            name: int(pixel_hist[i]) for i, name in enumerate(FURNITURE_CLASSES)
        },
        "scene_type_histogram": histogram([r["scene_type"] for r in rows]),
        "room_type_histogram": histogram([r["room_type"] for r in rows if r["room_type"]]),
        "scene_types_unmapped": histogram([r["scene_type"] for r in rows if not r["room_type"]]),
    }
    # Persist the stats.
    write_json(cleaning_dir() / "nyu_summary.json", stats)
    # Persist the name list for the taxonomy grounding test.
    write_json(
        cleaning_dir() / "nyu_label_vocabulary.json",
        {"names": names, "normalized": sorted({normalize_label(n) for n in names})},
    )
    # Give the stats back.
    return stats
