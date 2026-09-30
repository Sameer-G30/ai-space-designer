"""YOLO-World-S: zero-shot baseline, fine-tune, and held-out evaluation (needs .venv-train)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Metrics files are JSON.
import json

# Paths for data and weights.
from pathlib import Path

# The locked 26 furniture classes are the detector vocabulary.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES
from spacedesigner.training.room_data import MODELS_DIR, PROCESSED_DIR

# Approved checkpoint: the small YOLO-World v2 model.
CHECKPOINT = str(MODELS_DIR / "pretrained" / "yolov8s-worldv2.pt")

# Output folder for the detector (gitignored with models/).
DETECTOR_DIR = MODELS_DIR / "detector"

# Generated dataset file with absolute paths and prompt-friendly class names.
DATA_YAML = DETECTOR_DIR / "data.yaml"

# Fine-tuned weights after training.
BEST_WEIGHTS = DETECTOR_DIR / "finetune" / "weights" / "best.pt"

# Held-out metrics for the report.
METRICS_PATH = DETECTOR_DIR / "detector_metrics.json"

# Image size and batch chosen for the 8 GB GPU.
IMAGE_SIZE = 640
BATCH_SIZE = 8


# Write the dataset yaml that ultralytics reads.
def write_data_yaml() -> Path:
    """Point at the cleaned SUN RGB-D export. Class ids and order match the locked taxonomy."""
    # Make the output folder.
    DETECTOR_DIR.mkdir(parents=True, exist_ok=True)
    # Underscores become spaces so the text encoder reads "coffee table" not "coffee_table".
    names = "\n".join(
        f"  {i}: {name.replace('_', ' ')}" for i, name in enumerate(FURNITURE_CLASSES)
    )
    # Ultralytics resolves relative list entries against the working directory, so write
    # absolute-path copies of the official split lists beside the yaml.
    export = PROCESSED_DIR / "sun_rgbd"
    # One list per official split.
    for split in ("train", "val", "test"):
        # Read the official list of relative image paths.
        lines = (export / f"{split}.txt").read_text(encoding="utf-8").split()
        # Write the same images as absolute paths.
        (DETECTOR_DIR / f"{split}.txt").write_text(
            "\n".join(str(export / line) for line in lines) + "\n", encoding="utf-8"
        )
    # The yaml points at the absolute lists; labels are found by swapping images/ for labels/.
    text = (
        f"path: {DETECTOR_DIR}\n"
        "train: train.txt\nval: val.txt\ntest: test.txt\n"
        f"names:\n{names}\n"
    )
    # Save the file.
    DATA_YAML.write_text(text, encoding="utf-8")
    # Hand back its path.
    return DATA_YAML


# Pull the two headline numbers out of an ultralytics result.
def _numbers(metrics) -> dict:
    """Return mAP50 and mAP50-95 from a validation result."""
    # box.map50 and box.map are the COCO-style averages over classes with labels.
    return {"mAP50": float(metrics.box.map50), "mAP50_95": float(metrics.box.map)}


# Score a model on the test split.
def _val_test(model) -> dict:
    """Run validation on the held-out test split."""
    # plots off so no images are written.
    result = model.val(
        data=str(write_data_yaml()),
        split="test",
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        plots=False,
        project=str(DETECTOR_DIR),
        name="val",
        exist_ok=True,
    )
    # Return the headline numbers.
    return _numbers(result)


# Zero-shot baseline: the same model before any fine-tuning.
def zero_shot() -> dict:
    """Score the pretrained checkpoint with the 26 class prompts and no training."""
    # Import here because ultralytics is only in .venv-train.
    from ultralytics import YOLOWorld

    # Load the pretrained checkpoint.
    model = YOLOWorld(CHECKPOINT)
    # Set the open vocabulary to the 26 classes.
    model.set_classes([name.replace("_", " ") for name in FURNITURE_CLASSES])
    # Score the test split.
    return _val_test(model)


# Fine-tune on the SUN RGB-D train split.
def train(epochs: int = 30, seed: int = 20260930) -> dict:
    """Fine-tune, then score the best checkpoint on the test split."""
    # Torch and ultralytics imports.
    import torch
    from ultralytics import YOLOWorld

    # GPU is required.
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; run this with .venv-train/bin/python.")
    # Baseline first so both numbers come from the same pretrained weights.
    baseline = zero_shot()
    # Reset the peak counter so the VRAM figure covers training only.
    torch.cuda.reset_peak_memory_stats()
    # Fresh pretrained model for training.
    model = YOLOWorld(CHECKPOINT)
    # Fine-tune with mixed precision.
    model.train(
        data=str(write_data_yaml()),
        epochs=epochs,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        amp=True,
        workers=4,
        seed=seed,
        plots=False,
        project=str(DETECTOR_DIR),
        name="finetune",
        exist_ok=True,
    )
    # Peak reserved memory in MiB for this process.
    peak_mib = torch.cuda.max_memory_reserved() / 2**20
    # Score the best checkpoint on the held-out test split.
    tuned = _val_test(YOLOWorld(str(BEST_WEIGHTS)))
    # Collect everything for the report.
    metrics = {
        "model": "yolov8s-worldv2.pt",
        "image_size": IMAGE_SIZE,
        "batch_size": BATCH_SIZE,
        "epochs": epochs,
        "peak_vram_mib": round(peak_mib, 1),
        "zero_shot_test": baseline,
        "finetuned_test": tuned,
    }
    # Persist.
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    # Hand back.
    return metrics


# Re-score saved weights and the baseline.
def evaluate_saved() -> dict:
    """Score the fine-tuned weights and the zero-shot baseline on the test split."""
    # Import here because ultralytics is only in .venv-train.
    from ultralytics import YOLOWorld

    # Both numbers side by side.
    return {
        "zero_shot_test": zero_shot(),
        "finetuned_test": _val_test(YOLOWorld(str(BEST_WEIGHTS))),
    }
