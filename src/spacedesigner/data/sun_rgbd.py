"""Clean SUN RGB-D 2D boxes into YOLO labels with a sensor/scene-stratified split."""

# Annotations on Python 3.11.
from __future__ import annotations

# Reads image bytes to check they decode.
import io

# Parses the layout JSON.
import json

# Zip access without unpacking the whole archive.
import zipfile

# Lists of raw label counts.
from collections import Counter

# Array math for the box clean-up.
import numpy as np

# MATLAB v5 reader for the updated 2D box file.
import scipy.io as sio

# Image decode check and size.
from PIL import Image

# Shared helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    dhash,
    histogram,
    processed_dir,
    raw_dir,
    require_free_space,
    stratified_group_split,
    write_json,
    write_jsonl,
)

# Taxonomy and mappers.
from spacedesigner.data.taxonomy import (
    FURNITURE_CLASSES,
    FURNITURE_INDEX,
    map_furniture,
    map_sun_scene,
    normalize_label,
)

# A box must keep at least this share of its area inside the image or it is out of bounds.
MIN_INSIDE_FRACTION = 0.9

# Boxes with a side shorter than this many pixels are tiny.
MIN_SIDE_PX = 8.0

# Boxes covering less than this share of the image are tiny.
MIN_AREA_FRACTION = 0.0005

# Two same-class boxes with IoU at or above this are duplicates.
DUPLICATE_IOU = 0.9


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Return intersection over union of two (x0, y0, x1, y1) boxes."""
    # Overlap width, floored at zero.
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    # Overlap height.
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    # Intersection area.
    inter = iw * ih
    # Union area.
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    # Guard against a zero union.
    return inter / union if union > 0 else 0.0


def clean_boxes(
    raw_boxes: list[tuple[str, list[float]]], width: int, height: int
) -> tuple[list[tuple[int, float, float, float, float]], Counter, int]:
    """Clean (label, [x, y, w, h]) rows (MATLAB 1-based) for one image.

    Returns kept (class_id, x0, y0, x1, y1) boxes in 0-based pixel coordinates, a Counter of
    drop reasons, and the number of kept boxes that were clipped to the image edge.
    Reasons: unmapped_class, non_finite, degenerate, out_of_bounds, tiny, duplicate.
    """
    # Kept boxes.
    kept: list[tuple[int, float, float, float, float]] = []
    # Reason tally.
    dropped: Counter = Counter()
    # Boxes that overshot the edge slightly and were clipped instead of dropped.
    clipped = 0
    # Image area for the tiny test.
    image_area = float(width * height)
    # Walk every raw box.
    for label, values in raw_boxes:
        # Map the label first; unmapped classes are not part of the taxonomy.
        name = map_furniture(label)
        # Drop unmapped.
        if name is None:
            # Count it.
            dropped["unmapped_class"] += 1
            # Next box.
            continue
        # Coerce to floats.
        arr = np.asarray(values, dtype=float).reshape(-1)
        # Need exactly four finite numbers.
        if arr.size != 4 or not np.all(np.isfinite(arr)):
            # Count NaN/inf or wrong length.
            dropped["non_finite"] += 1
            # Next box.
            continue
        # Zero or negative extent is degenerate.
        if arr[2] <= 0 or arr[3] <= 0:
            # Count it.
            dropped["degenerate"] += 1
            # Next box.
            continue
        # MATLAB x, y are 1-based pixel indexes, so subtract one for 0-based edges.
        x0, y0 = arr[0] - 1.0, arr[1] - 1.0
        # Width and height carry over unchanged.
        x1, y1 = x0 + arr[2], y0 + arr[3]
        # Area before clipping.
        full_area = (x1 - x0) * (y1 - y0)
        # Clip to the image rectangle (lower edges).
        cx0, cy0 = max(0.0, x0), max(0.0, y0)
        # Upper edges.
        cx1, cy1 = min(float(width), x1), min(float(height), y1)
        # Area that stays inside.
        inside = max(0.0, cx1 - cx0) * max(0.0, cy1 - cy0)
        # Too much of the box is outside the image.
        if inside / full_area < MIN_INSIDE_FRACTION:
            # Count it.
            dropped["out_of_bounds"] += 1
            # Next box.
            continue
        # Tiny by side length or by share of the image.
        if (
            cx1 - cx0 < MIN_SIDE_PX
            or cy1 - cy0 < MIN_SIDE_PX
            or inside / image_area < MIN_AREA_FRACTION
        ):
            # Count it.
            dropped["tiny"] += 1
            # Next box.
            continue
        # Class id for YOLO.
        class_id = FURNITURE_INDEX[name]
        # The clipped box.
        box = (cx0, cy0, cx1, cy1)
        # Any near-identical earlier box of the same class makes this one a duplicate.
        if any(k[0] == class_id and iou(box, k[1:]) >= DUPLICATE_IOU for k in kept):
            # Count it.
            dropped["duplicate"] += 1
            # Next box.
            continue
        # Note boxes that needed clipping.
        if (cx0, cy0, cx1, cy1) != (x0, y0, x1, y1):
            # Count the clip.
            clipped += 1
        # Keep the clipped box.
        kept.append((class_id, cx0, cy0, cx1, cy1))
    # Give everything back.
    return kept, dropped, clipped


def to_yolo_lines(boxes: list[tuple[int, float, float, float, float]], w: int, h: int) -> list[str]:
    """Format (class, x0, y0, x1, y1) boxes as normalised YOLO 'cls xc yc bw bh' lines."""
    # Output lines.
    lines: list[str] = []
    # One line per box.
    for class_id, x0, y0, x1, y1 in boxes:
        # Centre, normalised to [0, 1].
        xc, yc = (x0 + x1) / 2.0 / w, (y0 + y1) / 2.0 / h
        # Normalised width and height.
        bw, bh = (x1 - x0) / w, (y1 - y0) / h
        # Six decimals is well below one pixel.
        lines.append(f"{class_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    # Give the lines back.
    return lines


def split_group(sequence: str) -> str:
    """Return the group id: SUN3D frames of one location stay together, others are per image."""
    # SUN3D sequences share a location folder, and neighbouring frames look alike.
    if "/sun3ddata/" in sequence:
        # Location folder is one level above the sequence folder.
        return sequence.rsplit("/", 1)[0]
    # Every other sensor folder is one capture.
    return sequence


def has_layout(payload: bytes) -> bool:
    """Return True when annotation3Dlayout/index.json holds at least one polygon."""
    # Broken JSON means no usable layout.
    try:
        # Parse the layout file.
        data = json.loads(payload)
    except ValueError:
        # Not JSON.
        return False
    # A polygon list under any object counts.
    return any(obj.get("polygon") for obj in data.get("objects", []) if obj)


def run() -> dict:
    """Export SUN RGB-D YOLO labels, images, and the test geometry benchmark. Return the stats."""
    # Where the zip and box file sit.
    source = raw_dir("sun_rgbd")
    # Output folder (gitignored).
    out = processed_dir("sun_rgbd")
    # About 1.5 GB of JPEGs plus test depth files.
    require_free_space(out, 4 * 1024**3)
    # The updated 2D boxes.
    meta = sio.loadmat(source / "SUNRGBDMeta2DBB_v2.mat", squeeze_me=True, struct_as_record=False)[
        "SUNRGBDMeta2DBB"
    ]
    # Open the image zip once.
    archive = zipfile.ZipFile(source / "SUNRGBD.zip")
    # Set of member names for existence checks.
    names = set(archive.namelist())
    # Extrinsics files per capture folder, indexed once so the test loop stays fast.
    extrinsics_by_prefix: dict[str, list[str]] = {}
    # One pass over the member names.
    for member in names:
        # Only tilt/extrinsics text files.
        if "/extrinsics/" in member and member.endswith(".txt"):
            # Capture folder is everything before 'extrinsics/'.
            extrinsics_by_prefix.setdefault(member.split("extrinsics/")[0], []).append(member)
    # Rows describing each readable image.
    records: list[dict] = []
    # Reasons an image was dropped entirely.
    dropped_images: Counter = Counter()
    # Reasons a box was dropped, over the whole dataset.
    dropped_boxes: Counter = Counter()
    # Total boxes clipped to the image edge.
    clipped_total = 0
    # Raw class-name vocabulary with counts, for the grounding test.
    raw_vocab: Counter = Counter()
    # Boxes kept per image, keyed by the image index.
    kept_by_index: dict[int, list[tuple[int, float, float, float, float]]] = {}
    # Walk every image entry.
    for index, entry in enumerate(meta):
        # Folder of this capture inside the zip.
        prefix = f"{entry.sequenceName}/"
        # Image member.
        image_name = f"{prefix}image/{entry.rgbname}"
        # Scene label file.
        scene_name = f"{prefix}scene.txt"
        # Missing image or scene file.
        if image_name not in names or scene_name not in names:
            # Count it.
            dropped_images["missing_file"] += 1
            # Next image.
            continue
        # Read and decode the JPEG.
        try:
            # Bytes from the zip.
            blob = archive.read(image_name)
            # Decode to prove the file is valid.
            with Image.open(io.BytesIO(blob)) as picture:
                # Force a full decode, not just the header.
                picture.load()
                # Size for the box checks.
                width, height = picture.size
                # Perceptual hash for later near-duplicate checks.
                digest = dhash(picture)
        except (OSError, ValueError):
            # Corrupt JPEG.
            dropped_images["corrupt_image"] += 1
            # Next image.
            continue
        # Raw scene string.
        scene = archive.read(scene_name).decode("latin-1").strip().lower()
        # Raw boxes as (label, [x, y, w, h]).
        raw_boxes = [
            (str(box.classname), list(np.asarray(box.gtBb2D, dtype=float).reshape(-1)))
            for box in np.atleast_1d(entry.groundtruth2DBB)
            if hasattr(box, "classname")
        ]
        # Tally the vocabulary for the grounding test.
        raw_vocab.update(label for label, _ in raw_boxes)
        # Clean the boxes.
        kept, reasons, clipped = clean_boxes(raw_boxes, width, height)
        # Add to the global drop tally.
        dropped_boxes.update(reasons)
        # Add to the clip tally.
        clipped_total += clipped
        # Remember the kept boxes.
        kept_by_index[index] = kept
        # One manifest row per readable image.
        records.append(
            {
                "index": index,
                "sequence": str(entry.sequenceName),
                "sensor": str(entry.sensorType),
                "scene": scene,
                "room_type": map_sun_scene(scene),
                "width": width,
                "height": height,
                "n_raw_boxes": len(raw_boxes),
                "n_boxes": len(kept),
                "dhash": f"{digest:016x}",
                "overlaps_nyu_depth_v2": "/kv1/NYUdata/" in str(entry.sequenceName),
                "image_member": image_name,
                "depth_member": f"{prefix}depth/{entry.depthname}",
            }
        )
    # Split over every readable image so the room-type set can reuse it.
    splits = stratified_group_split(
        [
            (str(r["index"]), split_group(r["sequence"]), f"{r['sensor']}|{r['scene']}")
            for r in records
        ]
    )
    # Test-split geometry rows.
    geometry_rows = 0
    # Write files.
    for record in records:
        # Split name.
        split = splits[str(record["index"])]
        # Stable short id.
        image_id = f"sun_{record['index']:05d}"
        # Store both on the row.
        record["id"], record["split"] = image_id, split
        # Image folder for this split.
        image_dir = out / "images" / split
        # Create it.
        image_dir.mkdir(parents=True, exist_ok=True)
        # Copy the original JPEG bytes without re-encoding.
        (image_dir / f"{image_id}.jpg").write_bytes(archive.read(record["image_member"]))
        # Path relative to the processed folder.
        record["image_path"] = f"images/{split}/{image_id}.jpg"
        # Label file only for images with at least one kept box.
        if record["n_boxes"] > 0:
            # Label folder for this split.
            label_dir = out / "labels" / split
            # Create it.
            label_dir.mkdir(parents=True, exist_ok=True)
            # Kept boxes for this image.
            boxes = kept_by_index[record["index"]]
            # Format the YOLO lines.
            lines = to_yolo_lines(boxes, record["width"], record["height"])
            # Write one box per line.
            (label_dir / f"{image_id}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Default: no geometry benchmark files.
        record["has_test_geometry"] = False
        # Only test images get depth and layout copies.
        if split == "test":
            # Capture folder inside the zip.
            prefix = record["sequence"] + "/"
            # 3D room-layout file.
            layout_name = f"{prefix}annotation3Dlayout/index.json"
            # Require depth and a layout file.
            if record["depth_member"] in names and layout_name in names:
                # Read the layout bytes.
                layout = archive.read(layout_name)
                # Skip captures whose layout has no polygon.
                if has_layout(layout):
                    # Geometry folder for this image.
                    geo = out / "geometry" / "test" / image_id
                    # Create it.
                    geo.mkdir(parents=True, exist_ok=True)
                    # Raw uint16 depth PNG, bit-shifted as the SUN toolbox expects.
                    (geo / "depth.png").write_bytes(archive.read(record["depth_member"]))
                    # 3D layout annotation.
                    (geo / "layout.json").write_bytes(layout)
                    # Camera intrinsics.
                    (geo / "intrinsics.txt").write_bytes(archive.read(f"{prefix}intrinsics.txt"))
                    # Extrinsics (tilt rotation) files, if present.
                    ext = sorted(extrinsics_by_prefix.get(prefix, []))
                    # Copy the first one.
                    if ext:
                        # Write it.
                        (geo / "extrinsics.txt").write_bytes(archive.read(ext[0]))
                    # Mark the row.
                    record["has_test_geometry"] = True
                    # Count it.
                    geometry_rows += 1
    # Drop helper keys that only mattered while exporting.
    for record in records:
        # Zip member names are not needed downstream.
        record.pop("image_member")
        # Depth member name too.
        record.pop("depth_member")
    # Manifest of every readable image.
    write_jsonl(out / "manifest.jsonl", records)
    # YOLO list files: only images that have a label file.
    for split in ("train", "val", "test"):
        # Relative image paths with labels.
        listed = [r["image_path"] for r in records if r["split"] == split and r["n_boxes"] > 0]
        # One path per line.
        (out / f"{split}.txt").write_text("\n".join(listed) + "\n", encoding="utf-8")
    # YOLO dataset file header.
    yaml_lines = ["path: .", "train: train.txt", "val: val.txt", "test: test.txt", "names:"]
    # One line per class.
    yaml_lines += [f"  {i}: {name}" for i, name in enumerate(FURNITURE_CLASSES)]
    # Save it.
    (out / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    # Per-split class histogram over the YOLO labels.
    class_hist: dict[str, dict[str, int]] = {}
    # One split at a time.
    for split in ("train", "val", "test"):
        # Class names of every kept box in the split.
        labels = [
            FURNITURE_CLASSES[box[0]]
            for r in records
            if r["split"] == split
            for box in kept_by_index[r["index"]]
        ]
        # Sorted histogram.
        class_hist[split] = histogram(labels)
    # Stats for the report.
    stats = {
        "images_in_meta": int(len(meta)),
        "images_readable": len(records),
        "images_with_labels": sum(1 for r in records if r["n_boxes"] > 0),
        "images_dropped": dict(dropped_images),
        "boxes_raw": sum(r["n_raw_boxes"] for r in records),
        "boxes_kept": sum(r["n_boxes"] for r in records),
        "boxes_clipped_to_edge": clipped_total,
        "boxes_dropped_by_reason": dict(sorted(dropped_boxes.items())),
        "split_images": histogram([r["split"] for r in records]),
        "split_labeled_images": histogram([r["split"] for r in records if r["n_boxes"] > 0]),
        "split_by_sensor": histogram([f"{r['split']}|{r['sensor']}" for r in records]),
        "scene_histogram": histogram([r["scene"] for r in records]),
        "scene_unmapped_to_room_type": histogram(
            [r["scene"] for r in records if r["room_type"] is None]
        ),
        "room_type_histogram": histogram([r["room_type"] for r in records if r["room_type"]]),
        "class_histogram_by_split": class_hist,
        "test_images_with_depth_and_layout": geometry_rows,
        "images_overlapping_nyu_depth_v2": sum(r["overlaps_nyu_depth_v2"] for r in records),
    }
    # Persist the stats (text only, safe to track).
    write_json(cleaning_dir() / "sun_rgbd_summary.json", stats)
    # Vocabulary with normalized keys for the taxonomy grounding test.
    write_json(
        cleaning_dir() / "sun_rgbd_label_vocabulary.json",
        {
            "raw_counts": dict(sorted(raw_vocab.items())),
            "normalized": sorted({normalize_label(k) for k in raw_vocab}),
        },
    )
    # Give the stats back.
    return stats
