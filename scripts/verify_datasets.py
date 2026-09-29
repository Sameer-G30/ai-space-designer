"""Check Phase 1 files, checksums, and the license log. Does not download."""

# Hash files independently of the downloader.
import hashlib

# Read the catalog and the logs.
import json

# Repo-relative paths.
from pathlib import Path

# Read size for the hash loop.
CHUNK_BYTES = 1024 * 1024


def project_root() -> Path:
    """Return the repository root."""
    # This file lives in scripts/.
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    """Load one JSON object."""
    # Logs and the catalog are UTF-8.
    with path.open(encoding="utf-8") as handle:
        # Return the object.
        return json.load(handle)


def hash_file(path: Path) -> tuple[str, str]:
    """Return (sha256 hex, md5 hex) for path."""
    # SHA-256 is compared to the acquisition log.
    sha256 = hashlib.sha256()
    # MD5 is compared to a published checksum when the catalog has one.
    md5 = hashlib.md5()
    # Stream so large archives are not loaded whole.
    with path.open("rb") as handle:
        # Read until EOF.
        while True:
            # One mebibyte per iteration.
            chunk = handle.read(CHUNK_BYTES)
            # Stop at the end of the file.
            if not chunk:
                # Both digests are complete.
                break
            # Update SHA-256.
            sha256.update(chunk)
            # Update MD5 from the same bytes.
            md5.update(chunk)
    # Hex strings match the logs.
    return sha256.hexdigest(), md5.hexdigest()


def main() -> int:
    """Verify the catalog. Return 0, 1, or 2."""
    # Repository root for relative paths.
    root = project_root()
    # Commit-safe catalog.
    catalog_path = root / "datasets" / "metadata" / "expected_files.json"
    # Commit-safe license log.
    license_path = root / "datasets" / "metadata" / "license_log.json"
    # Commit-safe checksum log.
    acquisition_path = root / "datasets" / "metadata" / "acquisition_log.json"
    # The catalog is required.
    if not catalog_path.is_file():
        # Tell the user what is missing.
        print(f"FAIL missing catalog {catalog_path}")
        # Hard failure.
        return 1
    # Load the expected files and dataset rows.
    catalog = load_json(catalog_path)
    # Failures are size, checksum, magic, or missing required small files.
    failures: list[str] = []
    # Phase 1 archives that still need approval.
    waiting: list[str] = []
    # Files that matched.
    acquired: list[str] = []
    # The license log must exist after the download scripts have been run.
    if not license_path.is_file():
        # Record the missing log.
        failures.append(f"missing license log {license_path}")
        # An empty map lets the rest of the checks report each dataset too.
        license_entries = {}
    else:
        # The log stores entries keyed by dataset id.
        license_entries = load_json(license_path).get("entries", {})
    # The acquisition log may be missing before the first download.
    if acquisition_path.is_file():
        # File rows keyed by file id.
        acquired_files = load_json(acquisition_path).get("files", {})
    else:
        # No checksums recorded yet.
        acquired_files = {}
    # Every catalog dataset needs a license-log entry.
    for dataset in catalog["datasets"]:
        # Stable id.
        dataset_id = dataset["dataset_id"]
        # The log row, if the matching script has been run.
        entry = license_entries.get(dataset_id)
        # A missing row means the license log is incomplete.
        if entry is None:
            # Name the dataset.
            failures.append(f"license log missing {dataset_id}")
            # Keep checking other datasets.
            continue
        # The license label has to be non-empty.
        if not str(entry.get("license_name", "")).strip():
            # Incomplete license text.
            failures.append(f"license name empty for {dataset_id}")
        # The source page has to be recorded.
        if not str(entry.get("source_url", "")).strip():
            # Incomplete source.
            failures.append(f"license source empty for {dataset_id}")
        # Notes have to explain skips, manual steps, and terms.
        if not str(entry.get("notes", "")).strip():
            # An empty note is an incomplete log.
            failures.append(f"license notes empty for {dataset_id}")
        # Expected status depends on the catalog disposition.
        disposition = dataset["disposition"]
        # Status written by the download script.
        status = entry.get("status")
        # Skipped datasets must say so.
        if disposition == "skipped" and status != "skipped":
            # FurniScene should be skipped.
            failures.append(f"{dataset_id} status {status} != skipped")
        # Manual datasets must say registration is still open.
        if disposition == "manual" and status != "manual_registration":
            # 3D-FRONT and Structured3D use this status.
            failures.append(f"{dataset_id} status {status} != manual_registration")
        # Hand-written files use the local disposition.
        if disposition == "local" and status != "local":
            # The summary dataset should stay local.
            failures.append(f"{dataset_id} status {status} != local")
        # Objaverse may be waiting or finished.
        if disposition == "pending_user" and status not in {"awaiting_approval", "acquired"}:
            # Any other status is unexpected.
            failures.append(f"{dataset_id} status {status} is not awaiting_approval or acquired")
        # Local files listed on the dataset must exist and be non-empty.
        for relative in dataset.get("local_files", []):
            # Resolve under the repo.
            local_path = root / relative
            # The summary or category list must be present.
            if not local_path.is_file() or local_path.stat().st_size == 0:
                # Name the missing local file.
                failures.append(f"missing local file {relative}")
    # Check each downloadable archive.
    for record in catalog["files"]:
        # Only downloaded rows have byte checks.
        if record.get("disposition") != "download":
            # Manual rows are covered by the license log.
            continue
        # File id for messages.
        file_id = record["file_id"]
        # Destination path.
        path = root / record["relative_path"]
        # Acquisition row, if any.
        logged = acquired_files.get(file_id, {})
        # True when this file fails any check, so it is not listed as OK.
        file_failed = False
        # A missing file is either waiting on a flag, still transferring, or a failure.
        if not path.is_file():
            # A partial from an interrupted or still-running download.
            partial = path.with_suffix(path.suffix + ".partial")
            # Gated files are allowed to be absent until you approve them.
            gated = record.get("requires_confirm_large") or record.get("requires_accept_terms")
            # The log should say why a gated file is absent.
            waiting_status = logged.get("status") in {"awaiting_approval", "awaiting_terms"}
            # Resume file present means the transfer is not finished.
            if partial.is_file():
                # Report the partial size. This is not a checksum failure.
                waiting.append(f"{file_id} (partial {partial.stat().st_size} bytes)")
            # Phase 1 still expects the file eventually.
            elif gated and waiting_status:
                # Report it as waiting, not as a corrupt download.
                waiting.append(f"{file_id} ({logged.get('status')})")
            else:
                # A small direct file, or a gated file with no log row, is a failure.
                failures.append(f"missing {file_id} at {record['relative_path']}")
            # Nothing more to hash.
            continue
        # Size on disk.
        size = path.stat().st_size
        # Catalog size, when we measured Content-Length or an API size.
        expected = record.get("expected_bytes")
        # Reject a short or long file.
        if expected is not None and size != expected:
            # Include both sizes.
            failures.append(f"{file_id} size {size} != {expected}")
            # This file is not an OK row.
            file_failed = True
        # Magic prefix rejects HTML error pages.
        prefix = record.get("magic_prefix")
        # Only check when the catalog set one.
        if prefix:
            # Read the prefix bytes.
            with path.open("rb") as handle:
                # ASCII magic from the catalog.
                found = handle.read(len(prefix.encode("ascii")))
            # Compare to the expected magic.
            if found != prefix.encode("ascii"):
                # The file is the wrong type.
                failures.append(f"{file_id} magic mismatch")
                # This file is not an OK row.
                file_failed = True
        # Hash when we have a published MD5 or a logged SHA-256.
        need_hash = bool(record.get("md5")) or bool(logged.get("sha256"))
        # Small files and checksummed archives both go through one hash pass.
        if need_hash:
            # Compute both digests.
            sha256, md5 = hash_file(path)
            # Published MD5.
            if record.get("md5") and md5.lower() != str(record["md5"]).lower():
                # The host checksum does not match.
                failures.append(f"{file_id} md5 {md5} != {record['md5']}")
                # This file is not an OK row.
                file_failed = True
            # Logged SHA-256 from the downloader.
            if logged.get("sha256") and sha256.lower() != str(logged["sha256"]).lower():
                # The log and the bytes disagree.
                failures.append(f"{file_id} sha256 mismatch")
                # This file is not an OK row.
                file_failed = True
        # The acquisition row should say acquired when the file is present.
        if logged.get("status") != "acquired":
            # A file on disk without a log row is incomplete.
            failures.append(f"{file_id} on disk but acquisition status is {logged.get('status')}")
            # This file is not an OK row.
            file_failed = True
        # List the file only when every check above passed.
        if not file_failed:
            # Size, magic, and checksums matched.
            acquired.append(file_id)
    # When the Objaverse download has finished, every logged GLB must match.
    objaverse_entry = license_entries.get("objaverse", {})
    # Only hash the GLBs after the download script marks the dataset acquired.
    if objaverse_entry.get("status") == "acquired":
        # Per-asset license log written by scripts/download_objaverse.py.
        license_lines = root / "datasets" / "metadata" / "objaverse_asset_licenses.jsonl"
        # The log has to exist.
        if not license_lines.is_file():
            # Missing log is a failure.
            failures.append("missing objaverse_asset_licenses.jsonl")
        else:
            # One JSON object per line.
            rows = [
                json.loads(line)
                for line in license_lines.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            # The plan target is 160 furniture GLBs.
            if len(rows) != 160:
                # The sample is the wrong size.
                failures.append(f"objaverse license rows {len(rows)} != 160")
            # Check each asset's bytes and SHA-256.
            for row in rows:
                # Path recorded by the downloader.
                asset = root / row["relative_path"]
                # The GLB must be on disk.
                if not asset.is_file():
                    # Name the uid.
                    failures.append(f"missing objaverse uid {row.get('uid')}")
                    # Next asset.
                    continue
                # Size must match the log.
                if asset.stat().st_size != row["bytes"]:
                    # The file changed after the log was written.
                    failures.append(f"objaverse size mismatch {row.get('uid')}")
                # Recompute SHA-256.
                sha256, _md5 = hash_file(asset)
                # Compare with the logged digest.
                if sha256 != row["sha256"]:
                    # The bytes do not match the license log.
                    failures.append(f"objaverse sha256 mismatch {row.get('uid')}")
                # Every asset needs a license string.
                if not str(row.get("license", "")).strip():
                    # An empty license fails the log.
                    failures.append(f"objaverse license empty {row.get('uid')}")
            # True when any Objaverse row failed above.
            objaverse_failed = any(
                item.startswith("objaverse") or item.startswith("missing objaverse")
                for item in failures
            )
            # Count this set as one acquired group when every row passed.
            if not objaverse_failed:
                # The 160 GLBs matched the license log.
                acquired.append("objaverse_furniture_glbs")
    # Print the report.
    print(f"acquired_ok: {len(acquired)}")
    # List acquired ids.
    for item in acquired:
        # One id per line.
        print(f"  OK {item}")
    # List archives still waiting on approval.
    print(f"waiting_for_approval: {len(waiting)}")
    # One waiting file per line.
    for item in waiting:
        # Include the gate status.
        print(f"  WAIT {item}")
    # List hard failures.
    print(f"failures: {len(failures)}")
    # One failure per line.
    for item in failures:
        # Prefix so it is easy to scan.
        print(f"  FAIL {item}")
    # Hard failures take priority.
    if failures:
        # Checksum, missing small file, or incomplete license log.
        return 1
    # Phase 1 direct archives that are still gated.
    required_waiting = [
        record["file_id"]
        for record in catalog["files"]
        if record.get("phase1_required") and record.get("disposition") == "download"
        and not (root / record["relative_path"]).is_file()
    ]
    # Exit 2 when the license log is complete but large archives are not on disk yet.
    if required_waiting:
        # Name them again in one line for the exit summary.
        print("phase1_incomplete: " + ", ".join(required_waiting))
        # Not a checksum failure. The downloads have not been approved.
        return 2
    # Every required file matched and the license log is complete.
    print("phase1_complete")
    # Success.
    return 0


# Script entry point.
if __name__ == "__main__":
    # Propagate 0, 1, or 2.
    raise SystemExit(main())
