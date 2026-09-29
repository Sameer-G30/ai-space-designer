"""Paths, JSONL helpers, seeded splitting, and perceptual hashing shared by the cleaners."""

# Annotations on Python 3.11.
from __future__ import annotations

# Stable seeded shuffling and hashing.
import hashlib

# Reads and writes JSON and JSONL.
import json

# Seeded shuffling for the stratified splits.
import random

# Free-disk check before unpacking.
import shutil

# Counts and groups.
from collections import Counter, defaultdict

# Path objects for every file location.
from pathlib import Path

# Fast array math for hashes and masks.
import numpy as np

# Image loading for the perceptual hash.
from PIL import Image

# One fixed seed so every run gives identical splits.
SEED = 20260929

# Keep this much free space after writing exports.
MIN_FREE_BYTES = 10 * 1024**3


def repo_root() -> Path:
    """Return the repository root (three levels above this file's package)."""
    # data/ -> spacedesigner/ -> src/ -> repo.
    return Path(__file__).resolve().parents[3]


def raw_dir(name: str) -> Path:
    """Return datasets/raw/<name>."""
    # Raw archives never change.
    return repo_root() / "datasets" / "raw" / name


def processed_dir(name: str) -> Path:
    """Return datasets/processed/<name>, creating it."""
    # Cleaned exports live here and stay gitignored.
    path = repo_root() / "datasets" / "processed" / name
    # Create parents as needed.
    path.mkdir(parents=True, exist_ok=True)
    # Give the folder back.
    return path


def cleaning_dir() -> Path:
    """Return datasets/metadata/cleaning, creating it (tracked, text only)."""
    # Summaries and vocabularies are small and safe to commit.
    path = repo_root() / "datasets" / "metadata" / "cleaning"
    # Create if missing.
    path.mkdir(parents=True, exist_ok=True)
    # Give the folder back.
    return path


def require_free_space(path: Path, needed_bytes: int) -> None:
    """Raise if writing needed_bytes under path would leave less than MIN_FREE_BYTES."""
    # Free bytes on the volume that holds path.
    free = shutil.disk_usage(path).free
    # Refuse rather than fill the disk.
    if free - needed_bytes < MIN_FREE_BYTES:
        # Say exactly what was checked.
        raise RuntimeError(f"need {needed_bytes} bytes but only {free} free at {path}")


def write_json(path: Path, payload: object) -> None:
    """Write a UTF-8 JSON file with two-space indent and a trailing newline."""
    # Make sure the folder exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sorted keys keep diffs small.
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    """Read one UTF-8 JSON file."""
    # Plain read.
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write one JSON object per line."""
    # Make sure the folder exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Open once and stream rows.
    with path.open("w", encoding="utf-8") as handle:
        # One compact line per row.
        for row in rows:
            # Sorted keys keep runs identical.
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    # Skip blank lines.
    with path.open(encoding="utf-8") as handle:
        # Parse each non-empty line.
        return [json.loads(line) for line in handle if line.strip()]


def stratified_group_split(
    items: list[tuple[str, str, str]],
    fractions: tuple[float, float, float] = (0.8, 0.1, 0.1),
    min_stratum_items: int = 10,
) -> dict[str, str]:
    """Split (item_id, group_id, stratum) rows into train/val/test without splitting a group.

    Groups are shuffled with a fixed seed inside each stratum and dealt out by item count, so
    every stratum keeps roughly the requested fractions. Returns item_id -> split name.
    """
    # Collect group -> item ids, and group -> stratum (first item wins).
    group_items: dict[str, list[str]] = defaultdict(list)
    # Stratum of each group.
    group_stratum: dict[str, str] = {}
    # Walk every row once.
    for item_id, group_id, stratum in items:
        # Remember the item under its group.
        group_items[group_id].append(item_id)
        # The first item decides the stratum for the whole group.
        group_stratum.setdefault(group_id, stratum)
    # Group ids per stratum.
    by_stratum: dict[str, list[str]] = defaultdict(list)
    # Fill it from the map above.
    for group_id, stratum in group_stratum.items():
        # Append the group to its stratum.
        by_stratum[stratum].append(group_id)
    # Result map.
    assignment: dict[str, str] = {}
    # Split names in dealing order.
    names = ("train", "val", "test")
    # Handle strata in sorted order so the seed gives the same result every time.
    for stratum in sorted(by_stratum):
        # Sorted groups first, then a seeded shuffle.
        groups = sorted(by_stratum[stratum])
        # Per-stratum RNG so adding a stratum does not reshuffle the others.
        rng = random.Random(f"{SEED}:{stratum}")
        # Shuffle in place.
        rng.shuffle(groups)
        # Total items in this stratum.
        total = sum(len(group_items[g]) for g in groups)
        # Target item counts for val and test (train gets the rest).
        targets = [total * fractions[1], total * fractions[2]]
        # A tiny stratum cannot be split fairly, so it stays entirely in train.
        if total < min_stratum_items:
            # Zero targets send every group to train below.
            targets = [0.0, 0.0]
        # Running counts for val and test.
        filled = [0, 0]
        # Deal each group to the split that is furthest below its target.
        for group_id in groups:
            # Size of this group.
            size = len(group_items[group_id])
            # Deficit for val and test.
            deficits = [targets[0] - filled[0], targets[1] - filled[1]]
            # Pick val or test only if the group still fits its remaining target.
            if deficits[0] > 0 and deficits[0] >= deficits[1]:
                # Assign to val.
                choice = 1
            elif deficits[1] > 0:
                # Assign to test.
                choice = 2
            else:
                # Everything else is train.
                choice = 0
            # Update the running count for val or test.
            if choice:
                # Count these items.
                filled[choice - 1] += size
            # Record every item in the group.
            for item_id in group_items[group_id]:
                # Store the split name.
                assignment[item_id] = names[choice]
    # Every item has a split.
    return assignment


def dhash(image: Image.Image, size: int = 8) -> int:
    """Return a 64-bit difference hash of a PIL image as a Python int."""
    # Grayscale, (size+1) x size, so each row yields `size` left-vs-right comparisons.
    small = image.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    # Pixel array as int16 so the subtraction cannot wrap.
    pixels = np.asarray(small, dtype=np.int16)
    # True where a pixel is brighter than its right neighbour.
    bits = pixels[:, 1:] > pixels[:, :-1]
    # Pack the 64 booleans into one integer.
    value = 0
    # Walk bits in row-major order.
    for bit in bits.flatten():
        # Shift and append.
        value = (value << 1) | int(bit)
    # 64-bit hash.
    return value


def hamming(a: int, b: int) -> int:
    """Return the number of differing bits between two hashes."""
    # XOR then count ones.
    return bin(a ^ b).count("1")


def find_near_duplicates(hashes: list[int], max_distance: int) -> set[int]:
    """Return indexes to drop: any item within max_distance of an earlier kept item."""
    # Hashes as an unsigned 64-bit array for vectorised XOR.
    arr = np.array(hashes, dtype=np.uint64)
    # Indexes of items we keep so far.
    kept: list[int] = []
    # Indexes we drop.
    dropped: set[int] = set()
    # Bit-count lookup for bytes.
    table = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    # Compare each item to all kept items in one numpy call.
    for index in range(len(arr)):
        # First item is always kept.
        if kept:
            # XOR against the kept hashes.
            xor = arr[kept] ^ arr[index]
            # View as bytes and count bits per row.
            counts = table[xor.view(np.uint8).reshape(-1, 8)].sum(axis=1)
            # Any close match means this one is a duplicate.
            if counts.min() <= max_distance:
                # Drop it.
                dropped.add(index)
                # Move on without keeping it.
                continue
        # Keep this item.
        kept.append(index)
    # Caller drops these.
    return dropped


def histogram(values: list[str]) -> dict[str, int]:
    """Return a sorted {value: count} histogram."""
    # Counter does the tally; sorted keeps the JSON stable.
    return dict(sorted(Counter(values).items()))


def stable_hash(text: str) -> int:
    """Return a deterministic integer for text (Python's hash() is salted per run)."""
    # First 8 bytes of SHA-256 as an integer.
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
