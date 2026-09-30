"""Torch-free helpers for the room-type set: split loading and confusion-matrix maths."""

# Annotations on Python 3.11.
from __future__ import annotations

# Manifest rows are JSON lines.
import json

# Paths are relative to datasets/processed/.
from pathlib import Path

# The locked 15 room types give the class order.
from spacedesigner.data.taxonomy import ROOM_TYPE_INDEX, ROOM_TYPES

# Repo root is three parents above this file (src/spacedesigner/training/).
REPO_ROOT = Path(__file__).resolve().parents[3]

# Cleaned exports live here (gitignored).
PROCESSED_DIR = REPO_ROOT / "datasets" / "processed"

# Weights live here (gitignored).
MODELS_DIR = REPO_ROOT / "models"

# Official Phase 2a split names.
SPLITS = ("train", "val", "test")


# Read one split of the cleaned room-type manifest.
def load_split(split: str, processed_dir: Path = PROCESSED_DIR) -> list[tuple[Path, int]]:
    """Return (absolute image path, class index) pairs for one official split."""
    # Reject unknown split names early.
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    # Accumulate the pairs here.
    pairs: list[tuple[Path, int]] = []
    # Open the manifest written by scripts/clean_places.py.
    with (processed_dir / "room_types" / "manifest.jsonl").open(encoding="utf-8") as handle:
        # One JSON object per line.
        for line in handle:
            # Parse the row.
            row = json.loads(line)
            # Keep only rows from the requested split.
            if row["split"] == split:
                # Class index comes from the locked taxonomy, not from the file's label field.
                pairs.append((processed_dir / row["path"], ROOM_TYPE_INDEX[row["room_type"]]))
    # Hand back the pairs.
    return pairs


# Count predictions per (true, predicted) cell.
def confusion_matrix(y_true: list[int], y_pred: list[int], n_classes: int) -> list[list[int]]:
    """Return an n x n matrix where rows are true classes and columns are predictions."""
    # Start from zeros.
    matrix = [[0] * n_classes for _ in range(n_classes)]
    # Count each pair.
    for truth, pred in zip(y_true, y_pred, strict=True):
        # Row is truth, column is prediction.
        matrix[truth][pred] += 1
    # Hand back the counts.
    return matrix


# Turn a matrix into the numbers the report quotes.
def summarize_confusion(matrix: list[list[int]]) -> dict:
    """Return top-1, per-class recall, and the most frequent confusions."""
    # Number of classes.
    size = len(matrix)
    # Total examples and correct ones.
    total = sum(sum(row) for row in matrix)
    # Diagonal is the correct count.
    correct = sum(matrix[i][i] for i in range(size))
    # Recall per class, or None when a class has no held-out examples.
    recall = {
        ROOM_TYPES[i]: (matrix[i][i] / sum(matrix[i]) if sum(matrix[i]) else None)
        for i in range(size)
    }
    # Off-diagonal cells, largest first.
    confusions = sorted(
        (
            (matrix[i][j], ROOM_TYPES[i], ROOM_TYPES[j])
            for i in range(size)
            for j in range(size)
            if i != j and matrix[i][j] > 0
        ),
        reverse=True,
    )
    # Package the summary.
    return {
        "top1": correct / total if total else 0.0,
        "n": total,
        "per_class_recall": recall,
        "top_confusions": [
            {"true": t, "predicted": p, "count": c} for c, t, p in confusions[:5]
        ],
    }
