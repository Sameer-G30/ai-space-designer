"""Build the room-type dataset from Places365 val_256 (indoor classes) plus SUN RGB-D scenes."""

# Annotations on Python 3.11.
from __future__ import annotations

# Decode check for extracted images.
import io

# Seeded sampling for the balance cap.
import random

# Reads the val tar member by member.
import tarfile

# Tallies.
from collections import Counter, defaultdict

# Typing for path arguments.
from pathlib import Path

# Image decode and size.
from PIL import Image

# Shared helpers.
from spacedesigner.data.common import (
    SEED,
    cleaning_dir,
    dhash,
    find_near_duplicates,
    histogram,
    processed_dir,
    raw_dir,
    read_jsonl,
    stratified_group_split,
    write_json,
    write_jsonl,
)

# Taxonomy pieces.
from spacedesigner.data.taxonomy import PLACES_INDOOR_CATEGORIES, ROOM_TYPES

# Places365 256x256 images must be exactly this size.
PLACES_SIZE = (256, 256)

# Hashes this close (Hamming bits out of 64) count as near-duplicates.
NEAR_DUPLICATE_BITS = 4

# Most images kept per room type after the near-duplicate pass.
BALANCE_CAP = 300


def read_pairs(path: Path) -> dict[str, int]:
    """Read a 'name id' text file (categories or val labels) into {name: id}."""
    # Result map.
    result: dict[str, int] = {}
    # One pair per line.
    for line in path.read_text(encoding="utf-8").splitlines():
        # Skip blank lines.
        if line.strip():
            # Name and id are space separated.
            name, index = line.split()
            # Store as int.
            result[name] = int(index)
    # Give the map back.
    return result


def run() -> dict:
    """Extract, dedupe, balance, and split the room-type images. Return the stats."""
    # Raw Places folder.
    source = raw_dir("places365")
    # Output folders (gitignored).
    out = processed_dir("room_types")
    # Official category strings like '/b/bedroom' -> 11.
    categories = read_pairs(source / "categories_places365.txt")
    # Val labels like 'Places365_val_00000001.jpg' -> 165.
    val_labels = read_pairs(source / "places365_val.txt")
    # Every chosen string must exist in the official list.
    missing = [c for c in PLACES_INDOOR_CATEGORIES if c not in categories]
    # Refuse to invent class names.
    assert not missing, f"not official Places365 categories: {missing}"
    # Class id -> (official string, room type).
    chosen = {categories[c]: (c, room) for c, room in PLACES_INDOOR_CATEGORIES.items()}
    # File names we want from the tar.
    wanted = {name: chosen[cid] for name, cid in val_labels.items() if cid in chosen}
    # Places candidates that survive decoding.
    places: list[dict] = []
    # Drop reasons.
    dropped: Counter = Counter()
    # Raw bytes by file name.
    payload: dict[str, bytes] = {}
    # Walk the tar once.
    with tarfile.open(source / "val_256.tar") as archive:
        # Every member.
        for member in archive:
            # Base file name.
            base = member.name.rsplit("/", 1)[-1]
            # Only files we chose.
            if member.isfile() and base in wanted:
                # Read the bytes.
                payload[base] = archive.extractfile(member).read()
    # Images in the val labels but absent from the tar.
    dropped["label_without_image"] = len(wanted) - len(payload)
    # Decode each candidate in sorted name order for determinism.
    for name in sorted(payload):
        # Official string and room type.
        category, room = wanted[name]
        # Decode check.
        try:
            # Open and fully decode.
            with Image.open(io.BytesIO(payload[name])) as picture:
                # Force decode.
                picture.load()
                # Size check.
                if picture.size != PLACES_SIZE:
                    # Wrong size.
                    dropped["wrong_size"] += 1
                    # Next image.
                    continue
                # Perceptual hash.
                digest = dhash(picture)
        except (OSError, ValueError):
            # Corrupt file.
            dropped["corrupt_image"] += 1
            # Next image.
            continue
        # Keep the row.
        places.append(
            {
                "source": "places365_val",
                "name": name,
                "places_category": category,
                "room_type": room,
                "dhash": f"{digest:016x}",
            }
        )
    # SUN RGB-D rows that map to a room type.
    sun_rows = [
        r
        for r in read_jsonl(processed_dir("sun_rgbd") / "manifest.jsonl")
        if r["room_type"] in ROOM_TYPES
    ]
    # Group all candidates by room type, Places first so it wins near-duplicate ties.
    by_room: dict[str, list[dict]] = defaultdict(list)
    # Places first.
    for row in places:
        # Append under the room type.
        by_room[row["room_type"]].append(row)
    # Then SUN.
    for row in sun_rows:
        # SUN rows carry their own id and detection split.
        by_room[row["room_type"]].append(
            {
                "source": "sun_rgbd",
                "name": row["id"],
                "room_type": row["room_type"],
                "sun_scene": row["scene"],
                "dhash": row["dhash"],
                "split": row["split"],
                "path": f"sun_rgbd/{row['image_path']}",
            }
        )
    # Candidate counts before any filtering, for the report.
    before_dedupe = {room: len(rows) for room, rows in sorted(by_room.items())}
    # Balanced, deduplicated rows.
    final: list[dict] = []
    # Per-room near-duplicate tallies.
    dupes_by_room: Counter = Counter()
    # Per-room balance-cap drops.
    capped_by_room: Counter = Counter()
    # Process each room type.
    for room in sorted(by_room):
        # Candidates in a stable order.
        rows = by_room[room]
        # Near-duplicate indexes to drop.
        dup_idx = find_near_duplicates([int(r["dhash"], 16) for r in rows], NEAR_DUPLICATE_BITS)
        # Count them.
        dupes_by_room[room] = len(dup_idx)
        # Survivors keep their order.
        survivors = [r for i, r in enumerate(rows) if i not in dup_idx]
        # Balance: keep Places rows first, then a seeded sample of SUN rows up to the cap.
        keep_places = [r for r in survivors if r["source"] == "places365_val"][:BALANCE_CAP]
        # SUN survivors.
        sun_left = [r for r in survivors if r["source"] == "sun_rgbd"]
        # Seeded shuffle so the sample is reproducible.
        random.Random(f"{SEED}:{room}").shuffle(sun_left)
        # Room left under the cap.
        keep_sun = sun_left[: max(0, BALANCE_CAP - len(keep_places))]
        # Rows dropped by the cap.
        capped_by_room[room] = len(survivors) - len(keep_places) - len(keep_sun)
        # Add the kept rows.
        final.extend(keep_places + keep_sun)
    # Split the Places rows 80/10/10 per room type; SUN rows keep their detection split.
    places_split = stratified_group_split(
        [(r["name"], r["name"], r["room_type"]) for r in final if r["source"] == "places365_val"]
    )
    # Copy Places files and finish the rows.
    for row in final:
        # Places rows get a split and a copied file.
        if row["source"] == "places365_val":
            # Split from the stratified assignment.
            row["split"] = places_split[row["name"]]
            # Target folder.
            folder = out / "places365" / row["split"] / row["room_type"]
            # Create it.
            folder.mkdir(parents=True, exist_ok=True)
            # Copy the original bytes.
            (folder / row["name"]).write_bytes(payload[row["name"]])
            # Path relative to datasets/processed/.
            row["path"] = f"room_types/places365/{row['split']}/{row['room_type']}/{row['name']}"
        # Numeric label for the classifier.
        row["label"] = ROOM_TYPES.index(row["room_type"])
    # Manifest.
    write_jsonl(out / "manifest.jsonl", final)
    # Stats for the report.
    stats = {
        "places_categories_total": len(categories),
        "places_categories_chosen": dict(sorted(PLACES_INDOOR_CATEGORIES.items())),
        "places_val_images_total": len(val_labels),
        "places_val_images_in_chosen_classes": len(wanted),
        "places_val_images_not_indoor_class": len(val_labels) - len(wanted),
        "places_dropped_by_reason": dict(dropped),
        "places_train_archive": "not on disk: no Places train split can be built in Phase 2a",
        "sun_scene_images_mapped": len(sun_rows),
        "candidates_before_dedupe_by_room": before_dedupe,
        "near_duplicate_bits": NEAR_DUPLICATE_BITS,
        "near_duplicates_dropped_by_room": dict(sorted(dupes_by_room.items())),
        "balance_cap_per_room": BALANCE_CAP,
        "balance_cap_dropped_by_room": dict(sorted(capped_by_room.items())),
        "final_images": len(final),
        "final_by_room_type": histogram([r["room_type"] for r in final]),
        "final_by_source": histogram([r["source"] for r in final]),
        "final_by_split": histogram([r["split"] for r in final]),
        "final_by_split_and_room": histogram([f"{r['split']}|{r['room_type']}" for r in final]),
        "room_types_without_any_image": [
            room for room in ROOM_TYPES if room not in {r["room_type"] for r in final}
        ],
    }
    # Persist the stats.
    write_json(cleaning_dir() / "places_summary.json", stats)
    # Give the stats back.
    return stats
