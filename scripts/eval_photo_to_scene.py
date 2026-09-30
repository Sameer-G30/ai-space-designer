"""Phase 7b evaluation on public data. Run with .venv-train/bin/python.

Tasks:
  depth  Depth AbsRel, RMSE, delta1 on the NYU Depth V2 test split (654 frames).
  seg    Segmentation IoU on NYU test frames whose SUN RGB-D twin is in the SUN test split.
  dims   Room-dimension error (cm) on the SUN RGB-D test images with a 3D room layout.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Command-line arguments.
import argparse

# Metrics are written as JSON.
import json

# Wall-clock timing.
import time

# Paths.
from pathlib import Path

# Image and array libraries.
import cv2
import numpy as np
from PIL import Image

# Locked furniture classes and the geometry code under test.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES
from spacedesigner.perception.pipeline import geometry_from_depth
from spacedesigner.perception.stages import DepthModel, Detector, Segmenter

# Repo root and data locations.
ROOT = Path(__file__).resolve().parents[1]
NYU = ROOT / "datasets" / "processed" / "nyu_depth_v2"
SUN = ROOT / "datasets" / "processed" / "sun_rgbd"

# Where the numbers go (gitignored with models/).
OUT = ROOT / "models" / "photo_to_scene_metrics.json"

# Seed recorded for any sampling (the run itself is deterministic).
SEED = 20260930

# A 3-D layout is used only when its room is plausible.
GT_HEIGHT_RANGE = (1.8, 5.0)
GT_MIN_SIDE_M = 1.0


# Read a JSON-lines file.
def read_jsonl(path: Path) -> list[dict]:
    """Return every row of a JSON-lines file."""
    # One JSON object per non-empty line.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# Merge new numbers into the metrics file.
def save(section: str, payload: dict) -> None:
    """Write one section of the metrics file."""
    # Load what earlier tasks wrote.
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    # Replace this section.
    data[section] = payload
    # Write it back.
    OUT.write_text(json.dumps(data, indent=2))


# Depth error for one frame against Kinect depth.
def depth_errors(pred: np.ndarray, gt: np.ndarray) -> dict[str, float]:
    """Return AbsRel, RMSE, and delta1 over the valid GT pixels."""
    # GT pixels of 0 are invalid by the Phase 2a rule.
    valid = gt > 0
    # Predicted and true values at valid pixels.
    p, g = pred[valid], gt[valid]
    # Ratio used by delta1.
    ratio = np.maximum(p / g, g / p)
    # The three standard numbers.
    # Median scaling isolates a global scale bias from the depth shape.
    q = p * np.median(g / p)
    # The three standard numbers, plus AbsRel after median scaling.
    return {
        "absrel_median_scaled": float(np.mean(np.abs(q - g) / g)),
        "absrel": float(np.mean(np.abs(p - g) / g)),
        "rmse": float(np.sqrt(np.mean((p - g) ** 2))),
        "delta1": float(np.mean(ratio < 1.25)),
    }


# Task 1: metric depth on NYU test.
def eval_depth(limit: int | None, split: str, size: int) -> None:
    """Score the depth model on the NYU frames of one split (test for the report)."""
    # Rows of the chosen split.
    rows = [r for r in read_jsonl(NYU / "manifest.jsonl") if r["split"] == split][:limit]
    # Load once.
    model = DepthModel(size)
    # Per-frame errors.
    errors = []
    # Walk the frames.
    for row in rows:
        # Photo and Kinect depth.
        image = Image.open(NYU / row["rgb"]).convert("RGB")
        gt = np.load(NYU / row["depth"])
        # Predict and score.
        errors.append(depth_errors(model(image), gt))
    # Peak VRAM over the run.
    peak = model.close()
    # Mean over frames.
    result = {
        k: float(np.mean([e[k] for e in errors]))
        for k in ("absrel", "absrel_median_scaled", "rmse", "delta1")
    }
    # Record the setup.
    result.update({"frames": len(rows), "peak_vram_mib": round(peak, 1), "image_size": size})
    # Print and save (only the test split goes into the report file).
    print("depth", split, result)
    if split == "test":
        # Keep sweep runs on other splits out of the report numbers.
        save("depth_nyu_test", result)


# Task 2: segmentation IoU.
def eval_seg(limit: int | None) -> None:
    """Score detector-prompted SAM2 masks against the NYU label maps."""
    # NYU frame number i is SUN sequence NYU{i+1:04d}.
    sun = {
        r["sequence"].rsplit("/", 1)[-1]: r
        for r in read_jsonl(SUN / "manifest.jsonl")
        if r["overlaps_nyu_depth_v2"]
    }
    # NYU test frames whose SUN twin is also a SUN test image (the detector never trained on them).
    rows = []
    # Walk NYU test rows.
    for row in read_jsonl(NYU / "manifest.jsonl"):
        # Only the official test split.
        if row["split"] != "test":
            # Skip.
            continue
        # Twin name from the frame number.
        twin = sun.get(f"NYU{int(row['id'].split('_')[1]) + 1:04d}")
        # Keep clean frames only.
        if twin is not None and twin["split"] == "test":
            # Keep it.
            rows.append(row)
    # Apply the optional limit.
    rows = rows[:limit]
    # Load both models once.
    detector, segmenter = Detector(), Segmenter()
    # Intersection and union per class id (label value k + 1).
    inter = np.zeros(len(FURNITURE_CLASSES) + 1)
    union = np.zeros(len(FURNITURE_CLASSES) + 1)
    # Walk the frames.
    for row in rows:
        # Photo and label map (255 unlabeled, 0 other, k + 1 class k).
        image = Image.open(NYU / row["rgb"]).convert("RGB")
        gt = np.array(Image.open(NYU / row["labels"]))
        # Detect, then mask each box.
        detections = detector(image)
        masks = segmenter(image, [d[2] for d in detections]) if detections else []
        # Predicted label map: paint weak masks first so strong ones win.
        pred = np.zeros_like(gt)
        # Walk from the weakest.
        for (name, _, _), mask in reversed(list(zip(detections, masks, strict=True))):
            # Class value in the label map.
            pred[mask] = FURNITURE_CLASSES.index(name) + 1
        # Unlabeled GT pixels are ignored.
        keep = gt != 255
        # Score each class.
        for k in range(1, len(FURNITURE_CLASSES) + 1):
            # Pixels of this class in GT and prediction.
            g, p = (gt == k) & keep, (pred == k) & keep
            # Accumulate.
            inter[k] += (g & p).sum()
            union[k] += (g | p).sum()
    # Free the GPU.
    peak = max(detector.close(), segmenter.close())
    # Classes with at least one GT pixel.
    present = {
        FURNITURE_CLASSES[k - 1]: float(inter[k] / union[k]) for k in range(1, 27) if union[k] > 0
    }
    # Classes with GT pixels in these frames.
    result = {
        "frames": len(rows),
        "mean_iou": float(np.mean(list(present.values()))),
        "per_class_iou": present,
        "peak_vram_mib": round(peak, 1),
    }
    # Print and save.
    print("seg", {k: v for k, v in result.items() if k != "per_class_iou"})
    save("segmentation_nyu_test", result)


# Ground-truth room size from a SUN RGB-D 3-D layout.
def layout_dims(path: Path) -> tuple[float, float, float] | None:
    """Return (length, width, height) in metres, or None when the layout is unusable."""
    # Parse the annotation.
    payload = json.loads(path.read_text())
    # Room polygons only.
    polygons = [p for o in payload.get("objects", []) if o for p in o.get("polygon", [])]
    # No polygon.
    if not polygons:
        # Unusable.
        return None
    # Largest floor area wins when there are several.
    best = None
    # Walk the polygons.
    for poly in polygons:
        # Floor outline as float32 points.
        pts = np.array(list(zip(poly["X"], poly["Z"], strict=True)), dtype=np.float32)
        # Need a real polygon.
        if len(pts) < 3:
            # Skip it.
            continue
        # Area of the outline.
        area = cv2.contourArea(pts)
        # Keep the biggest.
        if best is None or area > best[0]:
            # Store it.
            best = (area, pts, poly["Ymax"] - poly["Ymin"])
    # Nothing usable.
    if best is None:
        # Unusable.
        return None
    # Minimum-area rectangle around the outline.
    (_, _), (w, h), _ = cv2.minAreaRect(best[1])
    # Sorted sides and the height.
    length, width, height = max(w, h), min(w, h), float(best[2])
    # Reject implausible rooms.
    if width < GT_MIN_SIDE_M or not GT_HEIGHT_RANGE[0] <= height <= GT_HEIGHT_RANGE[1]:
        # Unusable.
        return None
    # Ground truth.
    return float(length), float(width), height


# Summary of absolute errors in centimetres.
def summarize(values: list[float]) -> dict[str, float]:
    """Return count, mean, median, and 90th percentile of absolute errors."""
    # Array of errors.
    a = np.array(values)
    # Summary numbers.
    return {
        "n": int(len(a)),
        "mae_cm": float(a.mean()),
        "median_cm": float(np.median(a)),
        "p90_cm": float(np.percentile(a, 90)),
    }


# Ground-truth room size limited to what the camera could see.
def visible_dims(
    path: Path, half_tan: float, max_range: float, height: float
) -> tuple[float, float, float] | None:
    """Clip the floor outline to the view wedge and range, then return its rectangle sides."""
    # Parse the annotation.
    payload = json.loads(path.read_text())
    # Room polygons only.
    polygons = [p for o in payload.get("objects", []) if o for p in o.get("polygon", [])]
    # Largest outline.
    poly = max(
        polygons,
        key=lambda p: cv2.contourArea(np.array(list(zip(p["X"], p["Z"]))).astype(np.float32)),
    )
    # Outline points.
    pts = np.array(list(zip(poly["X"], poly["Z"], strict=True)), dtype=np.float32)
    # Raster cell size in metres.
    cell = 0.05
    # Grid origin and size covering the outline and the camera.
    lo = np.minimum(pts.min(axis=0), [0, 0]) - 0.5
    hi = np.maximum(pts.max(axis=0), [0, 0]) + 0.5
    # Grid shape (rows follow Z, columns follow X).
    shape = (int((hi[1] - lo[1]) / cell) + 1, int((hi[0] - lo[0]) / cell) + 1)
    # Rasterize the outline.
    mask = np.zeros(shape, np.uint8)
    # Outline in grid coordinates.
    cv2.fillPoly(mask, [((pts - lo) / cell).astype(np.int32)], 1)
    # Cell centres in metres.
    zz, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    # Metres for each cell.
    x, z = xx * cell + lo[0], zz * cell + lo[1]
    # Keep cells inside the outline, in front of the camera, inside the wedge and the range.
    keep = (mask > 0) & (z > 0) & (np.abs(x) <= z * half_tan) & (z <= max_range)
    # Too little area to measure.
    if keep.sum() < 200:
        # Unusable.
        return None
    # Minimum-area rectangle around the visible floor.
    (_, _), (w, h), _ = cv2.minAreaRect(np.stack([x[keep], z[keep]], axis=1).astype(np.float32))
    # Visible floor sides sorted and the full height.
    return float(max(w, h)), float(min(w, h)), height


# Task 3: room dimensions.
def eval_dims(limit: int | None, size: int) -> None:
    """Measure room-dimension error with three setups on the SUN RGB-D layout images."""
    # Test images with depth and layout.
    rows = [r for r in read_jsonl(SUN / "manifest.jsonl") if r["has_test_geometry"]][:limit]
    # Load the depth model once.
    model = DepthModel(size)
    # Dimension names.
    axes = ("length", "width", "height")
    # Two benchmarks: the whole annotated room, and only the part inside the view.
    names = ("full_room", "visible_part")

    # Error lists per benchmark, setup, and dimension.
    def fresh() -> dict:
        """Return empty error lists for one benchmark."""
        # Metric depth only, sensor-depth geometry, and one-measurement anchors.
        return {
            "no_measurement": {a: [] for a in axes},
            "sensor_depth_geometry": {a: [] for a in axes},
            "one_measurement": {a: {b: [] for b in axes if b != a} for a in axes},
        }

    # Accumulators.
    acc = {n: fresh() for n in names}
    # Counters.
    skipped = {"no_layout": 0, "no_visible_area": 0, "no_floor_pred": 0, "no_floor_sensor": 0}
    # Walk the images.
    for row in rows:
        # Folder with depth, layout, and intrinsics.
        geo = SUN / "geometry" / "test" / row["id"]
        # Ground truth room.
        full = layout_dims(geo / "layout.json")
        # Unusable layout.
        if full is None:
            # Count and skip.
            skipped["no_layout"] += 1
            continue
        # Photo.
        image = Image.open(SUN / row["image_path"]).convert("RGB")
        # Metric depth from the model; the default focal length is used (no GT intrinsics).
        est = geometry_from_depth(model(image), None)
        # Sensor depth decoded as in the SUN RGB-D toolbox (rotate bits, millimetres to metres).
        raw = np.array(Image.open(geo / "depth.png")).astype(np.uint16)
        # Bit rotation by three.
        sensor = (((raw >> 3) | (raw << 13)) & 0xFFFF).astype(np.float32) / 1000.0
        # Geometry from sensor depth shows the error of the plane fitting alone.
        ref = geometry_from_depth(sensor, None)
        # Count failures.
        skipped["no_floor_pred"] += est is None
        # Count failures.
        skipped["no_floor_sensor"] += ref is None
        # Field of view and range of the capture.
        half_tan = 0.5 / (26.0 / 36.0)
        # Far limit of what the sensor returned.
        valid = sensor[(sensor > 0.3) & (sensor < 12)]
        # Visible-part truth.
        vis = visible_dims(geo / "layout.json", half_tan, float(np.percentile(valid, 99)), full[2])
        # Count images with no visible area.
        skipped["no_visible_area"] += vis is None
        # Score each benchmark.
        for name, truth in (("full_room", full), ("visible_part", vis)):
            # Benchmark not available for this image.
            if truth is None:
                # Skip it.
                continue
            # Accumulators for this benchmark.
            a_ = acc[name]
            # Metric-depth-only and one-measurement errors.
            if est is not None:
                # Walk the dimensions.
                for a, t in zip(axes, truth, strict=True):
                    # Error in centimetres.
                    a_["no_measurement"][a].append(abs(est["room"][a] - t) * 100)
                # One measurement: anchor each dimension in turn.
                for a, ta in zip(axes, truth, strict=True):
                    # Scale so the anchored estimate equals the typed truth.
                    s = ta / est["room"][a]
                    # Error on the other dimensions.
                    for b, tb in zip(axes, truth, strict=True):
                        # Skip the anchor itself.
                        if b != a:
                            # Error after scaling.
                            a_["one_measurement"][a][b].append(abs(est["room"][b] * s - tb) * 100)
            # Sensor-depth errors.
            if ref is not None:
                # Walk the dimensions.
                for a, t in zip(axes, truth, strict=True):
                    # Error in centimetres.
                    a_["sensor_depth_geometry"][a].append(abs(ref["room"][a] - t) * 100)
    # Free the GPU.
    peak = model.close()
    # Assemble the result.
    result = {
        "images": len(rows),
        "skipped": {k: int(v) for k, v in skipped.items()},
        "image_size": size,
        "peak_vram_mib": round(peak, 1),
        "focal_35mm_assumed": 26.0,
    }
    # One block per benchmark.
    for name in names:
        # Setups for this benchmark.
        block = acc[name]
        # Summaries.
        result[name] = {
            "no_measurement": {a: summarize(v) for a, v in block["no_measurement"].items()},
            "sensor_depth_geometry": {
                a: summarize(v) for a, v in block["sensor_depth_geometry"].items()
            },
            "one_measurement": {
                f"anchor_{a}": {b: summarize(v) for b, v in others.items()}
                for a, others in block["one_measurement"].items()
            },
        }
    # Print and save.
    print("dims", json.dumps(result, indent=1))
    save("room_dimensions_sun_rgbd_test", result)


# Entry point.
def main() -> None:
    """Parse arguments and run the chosen tasks."""
    # Parse arguments.
    parser = argparse.ArgumentParser(description=__doc__)
    # Which task.
    parser.add_argument("task", choices=["depth", "seg", "dims", "all"])
    # Optional cap for a quick look.
    parser.add_argument("--limit", type=int, default=None)
    # NYU split for the depth task. Sweeps use train; the report uses test.
    parser.add_argument("--split", default="test", choices=["train", "test"])
    # Depth model short-side size in pixels.
    parser.add_argument("--size", type=int, default=518)
    # Read the values.
    args = parser.parse_args()
    # Start the timer.
    start = time.time()
    # Run the tasks in order; each frees the GPU before the next loads.
    if args.task in ("depth", "all"):
        # Depth.
        eval_depth(args.limit, args.split, args.size)
    # Segmentation.
    if args.task in ("seg", "all"):
        # Seg.
        eval_seg(args.limit)
    # Dimensions.
    if args.task in ("dims", "all"):
        # Dims.
        eval_dims(args.limit, args.size)
    # Elapsed time.
    print(f"done in {time.time() - start:.0f}s")


# Run as a script.
if __name__ == "__main__":
    main()
