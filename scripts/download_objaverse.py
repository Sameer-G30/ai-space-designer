"""Select about 160 Objaverse furniture GLBs and log each asset license.

The GLB download does not start unless --confirm-download is passed.
"""

# Opens gzip metadata so a truncated shard can be deleted before reuse.
import gzip

# Writes one JSON object per line for asset licenses.
import json

# Checks free disk space before any GLB transfer.
import shutil

# Gives urllib.request.urlretrieve a deadline. The Objaverse package sets none.
import socket

# Prints errors.
import sys

# Repo paths.
from pathlib import Path

# Lets this file import download_common when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# License-log helper and the shared hash function.
from download_common import (  # noqa: E402
    file_sha256_md5,
    load_catalog,
    parse_args,
    project_root,
    run_dataset,
    write_license_entry,
)

# Refuse to start the GLB set when free space is below this.
MINIMUM_FREE_BYTES = 20 * 1024 * 1024 * 1024

# Stop between assets if free space falls this low.
STOP_FREE_BYTES = 8 * 1024 * 1024 * 1024


def category_plan() -> dict:
    """Load the checked LVIS furniture category list."""
    # The list is commit-safe metadata, not the GLB bytes.
    path = project_root() / "datasets" / "metadata" / "objaverse_furniture_categories.json"
    # Read the category names and the target count.
    with path.open(encoding="utf-8") as handle:
        # Return the plan object.
        return json.load(handle)


def choose_uids(annotations: dict, plan: dict) -> list[tuple[str, str]]:
    """Round-robin sorted uids across the furniture categories."""
    # Category names in catalog order.
    names = [item["name"] for item in plan["categories"]]
    # Names that are not in this LVIS file must stop the script.
    missing = [name for name in names if name not in annotations]
    # Do not invent replacement category names.
    if missing:
        # The plan file and the annotation file disagree.
        raise RuntimeError("LVIS categories missing: " + ", ".join(missing))
    # Sort uids so the sample is stable across machines.
    buckets = {name: sorted(annotations[name]) for name in names}
    # Pairs of category and uid.
    picked: list[tuple[str, str]] = []
    # How many full passes we have made.
    round_index = 0
    # Target count from the plan, 160.
    target = int(plan["target_glb_count"])
    # Keep taking one uid per category per round.
    while len(picked) < target:
        # How many uids this round added.
        added = 0
        # Walk categories in a fixed order.
        for name in names:
            # This category's sorted uid list.
            uids = buckets[name]
            # Skip a category that has already been exhausted.
            if round_index >= len(uids):
                # Next category.
                continue
            # Take the next uid.
            picked.append((name, uids[round_index]))
            # Count it.
            added += 1
            # Stop once the target is reached.
            if len(picked) == target:
                # Leave the category loop.
                break
        # No category had another uid.
        if added == 0:
            # Stop even if we are short of the target.
            break
        # Next round takes the following uid from each category.
        round_index += 1
    # The selected pairs.
    return picked


def download_glbs() -> int:
    """Download the selected GLBs after --confirm-download."""
    # The package is installed only when you approve this step.
    try:
        # Import inside the confirm path so a dry run does not need the package.
        import objaverse
    # The package is an optional install until this flag is used.
    except ImportError:
        # Tell the user the exact install command.
        print("objaverse is not installed. From the repo root, run: uv add objaverse==0.1.7")
        # Do not start a download.
        return 1
    # Dataset bytes stay under datasets/raw/.
    raw_root = project_root() / "datasets" / "raw" / "objaverse"
    # Create the directory before the disk check.
    raw_root.mkdir(parents=True, exist_ok=True)
    # Free space on that filesystem.
    free = shutil.disk_usage(raw_root).free
    # A 160-GLB set can be several gigabytes, so require a large margin up front.
    if free < MINIMUM_FREE_BYTES:
        # Refuse rather than fill the disk.
        print(f"refusing Objaverse download: free {free} bytes is below {MINIMUM_FREE_BYTES}")
        # Not started.
        return 1
    # Point the package at the project raw directory. It otherwise uses ~/.objaverse.
    objaverse.BASE_PATH = str(raw_root)
    # The package joins this path with metadata and glbs.
    objaverse._VERSIONED_PATH = str(raw_root / "hf-objaverse-v1")
    # urlretrieve inside the package will abort a stalled shard instead of hanging.
    socket.setdefaulttimeout(180)
    # Drop truncated metadata from the earlier stalled transfer.
    metadata_dir = Path(objaverse._VERSIONED_PATH) / "metadata"
    # The directory exists only after a previous attempt.
    if metadata_dir.is_dir():
        # Check every shard the package may treat as complete.
        for shard in metadata_dir.glob("*.json.gz"):
            # A gzip header can be valid while the body is cut off.
            try:
                # Read the whole member so a short file fails.
                with gzip.open(shard, "rb") as handle:
                    # Drain the member.
                    while handle.read(1024 * 1024):
                        # Keep reading until EOF.
                        pass
            # Truncated or corrupt shards must be fetched again.
            except (OSError, EOFError, gzip.BadGzipFile):
                # Remove the bad shard.
                shard.unlink()
                # Tell the terminal which shard will be retried.
                print(f"removed incomplete metadata shard {shard.name}")
    # Category plan with the exact LVIS keys.
    plan = category_plan()
    # This fetches the annotation gzip (under 1 MB compressed), not the GLBs.
    annotations = objaverse.load_lvis_annotations()
    # Stable furniture sample.
    picked = choose_uids(annotations, plan)
    # Uid list for the package.
    uids = [uid for _name, uid in picked]
    # Category lookup for the license log.
    category_of = {uid: name for name, uid in picked}
    # Metadata includes the per-asset license field. It is not the GLB bytes.
    metadata = objaverse.load_annotations(uids)
    # Refuse to download a GLB whose metadata has no license string.
    missing_license = [uid for uid in uids if not (metadata.get(uid) or {}).get("license")]
    # Stop before the GLB transfers if the log would be incomplete.
    if missing_license:
        # Name a few uids so the failure is actionable.
        sample = ", ".join(missing_license[:5])
        # Do not start the asset download.
        raise RuntimeError(f"{len(missing_license)} uids have no license field, including {sample}")
    # Download one object at a time so we can stop if disk space gets low.
    paths: dict[str, str] = {}
    # Walk the selected uids in order.
    for uid in uids:
        # Re-check free space before each GLB.
        if shutil.disk_usage(raw_root).free < STOP_FREE_BYTES:
            # Stop before filling the disk.
            print(f"stopping: free space fell below {STOP_FREE_BYTES} bytes")
            # Partial set is a failure until you free space and re-run.
            return 1
        # The package downloads this uid if it is not already present.
        one = objaverse.load_objects(uids=[uid], download_processes=1)
        # Keep the returned path.
        paths.update(one)
    # License lines live in metadata so they can be committed.
    license_path = project_root() / "datasets" / "metadata" / "objaverse_asset_licenses.jsonl"
    # One JSON object per asset.
    lines: list[str] = []
    # Hash and record every downloaded file.
    for uid in uids:
        # The package returns a local path.
        local = paths.get(uid)
        # A missing path means that uid was skipped by the package.
        if not local:
            # Do not claim the asset was downloaded.
            raise RuntimeError(f"no file returned for uid {uid}")
        # Path object for hashing.
        file_path = Path(local)
        # Both digests.
        sha256, md5 = file_sha256_md5(file_path)
        # Sketchfab metadata for this uid.
        info = metadata.get(uid, {})
        # The license field is the per-asset license we must log.
        license_name = info.get("license")
        # Refuse a silent empty license.
        if not license_name:
            # The log would be incomplete.
            raise RuntimeError(f"uid {uid} has no license field")
        # One record.
        row = {
            # Objaverse uid.
            "uid": uid,
            # LVIS furniture category we selected.
            "category": category_of[uid],
            # Per-asset license string from the metadata.
            "license": license_name,
            # Byte size.
            "bytes": file_path.stat().st_size,
            # SHA-256 of the GLB.
            "sha256": sha256,
            # MD5 of the GLB.
            "md5": md5,
            # Path relative to the repo when it is under the repo.
            "relative_path": str(file_path.resolve().relative_to(project_root())),
        }
        # Store a compact line.
        lines.append(json.dumps(row, ensure_ascii=False))
    # Write the whole license log.
    license_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Mark the dataset acquired in the license log.
    dataset = next(item for item in load_catalog()["datasets"] if item["dataset_id"] == "objaverse")
    # One synthetic file row so the status becomes acquired.
    write_license_entry(dataset, [{"file_id": "objaverse_furniture_glbs", "status": "acquired"}])
    # Tell the terminal how many assets were logged.
    print(f"acquired {len(lines)} Objaverse GLBs; licenses in {license_path}")
    # Success.
    return 0


def main() -> int:
    """Record the pending license row, or download when confirmed."""
    # Shared flags. Only --confirm-download matters here.
    args = parse_args()
    # Without the flag, record the pending license entry and stop.
    if not args.confirm_download:
        # Explain the gate.
        print(
            "Objaverse GLB download not started. "
            "Re-run with --confirm-download to fetch 160 furniture GLBs."
        )
        # This writes status awaiting_approval and does not fetch GLBs.
        return run_dataset("objaverse")
    # Confirmed path.
    try:
        # Download and log licenses.
        return download_glbs()
    # Disk, license, or category errors fail the script.
    except (RuntimeError, OSError) as error:
        # Print the reason.
        print(f"error: {error}", file=sys.stderr)
        # Non-zero.
        return 1


# Script entry point.
if __name__ == "__main__":
    # Propagate the status code.
    raise SystemExit(main())
