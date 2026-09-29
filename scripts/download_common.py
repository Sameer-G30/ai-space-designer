"""Shared resume, checksum, and license-log helpers for Phase 1 downloads."""

# Annotations on Python 3.11 so optional fields can use dict | None.
from __future__ import annotations

# Parses --confirm-large and --accept-terms.
import argparse

# File lock so two download scripts can update the logs without clobbering.
import fcntl

# MD5 and SHA-256 for the files that publish a checksum, and for our own log.
import hashlib

# Reads the expected-file catalog and writes the license and acquisition logs.
import json

# Renames a finished partial download over the destination.
import os

# Checks free disk space before a download starts.
import shutil

# Prints skip and error messages to the terminal.
import sys

# Pauses between retries when a server drops the connection.
import time

# URLError and HTTPError are the failures we retry.
import urllib.error

# HTTP download with a Range header so a partial file can resume.
import urllib.request

# Project paths are Path objects, not strings.
from pathlib import Path

# Files at or above 1 GiB are multi-gigabyte and need --confirm-large.
LARGE_FILE_MIN_BYTES = 1024 * 1024 * 1024

# Keep this much free after each file so the disk is not filled.
DISK_MARGIN_BYTES = 5 * 1024 * 1024 * 1024

# Read and write size for the download loop.
CHUNK_BYTES = 1024 * 1024

# Identifies this client to dataset hosts.
USER_AGENT = "PhotoSpace-Phase1/0.1 (research dataset acquisition)"

# How many connection attempts in a row may add zero bytes before giving up.
MAX_ATTEMPTS = 40


def project_root() -> Path:
    """Return the repository root (the parent of scripts/)."""
    # This file lives in scripts/, one level under the project root.
    return Path(__file__).resolve().parents[1]


def catalog_path() -> Path:
    """Return the commit-safe expected-file catalog."""
    # The catalog is tracked because it lives under datasets/metadata/.
    return project_root() / "datasets" / "metadata" / "expected_files.json"


def license_log_path() -> Path:
    """Return the commit-safe license log."""
    # Verification reads this file to confirm every dataset has a license entry.
    return project_root() / "datasets" / "metadata" / "license_log.json"


def acquisition_log_path() -> Path:
    """Return the commit-safe record of downloaded sizes and checksums."""
    # Dataset bytes stay gitignored; only this log is committed.
    return project_root() / "datasets" / "metadata" / "acquisition_log.json"


def load_json(path: Path) -> dict:
    """Load a JSON object from disk."""
    # The catalog and logs are UTF-8 JSON objects.
    with path.open(encoding="utf-8") as handle:
        # json.load returns the top-level object.
        return json.load(handle)


def _with_log_lock(path: Path, update) -> None:
    """Read-modify-write one JSON log while holding an exclusive lock."""
    # The lock lives in /tmp so it is not committed.
    lock_path = Path("/tmp/photospace-phase1-metadata.lock")
    # Create the lock file if this is the first writer.
    with lock_path.open("a") as lock_handle:
        # Block until any other download script finishes its log update.
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            # Load the current log inside the lock.
            payload = load_log(path)
            # The caller mutates the object.
            update(payload)
            # Write the updated object before releasing the lock.
            save_json(path, payload)
        finally:
            # Release the lock even when the update raises.
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def save_json(path: Path, payload: dict) -> None:
    """Write a JSON object atomically enough for a single local user."""
    # metadata/ must exist before the first log write.
    path.parent.mkdir(parents=True, exist_ok=True)
    # A temporary file keeps a crash from leaving a half-written log.
    temporary = path.with_suffix(path.suffix + ".tmp")
    # indent makes the committed log readable in review.
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    # Write the full document, then replace the previous log.
    temporary.write_text(text, encoding="utf-8")
    # os.replace is atomic on the same filesystem.
    os.replace(temporary, path)


def load_catalog() -> dict:
    """Load datasets/metadata/expected_files.json."""
    # Every download script and the verifier share this catalog.
    return load_json(catalog_path())


def load_log(path: Path) -> dict:
    """Load a log object, or an empty one if this is the first run."""
    # Missing logs are created on the first successful script run.
    if not path.exists():
        # files/entries are filled in by the caller.
        return {}
    # An existing log is updated in place by dataset id or file id.
    return load_json(path)


def file_sha256_md5(path: Path) -> tuple[str, str]:
    """Hash a file once and return (sha256 hex, md5 hex)."""
    # SHA-256 is our own integrity check when the host published no checksum.
    sha256 = hashlib.sha256()
    # MD5 is used when the host published an MD5, as Zenodo and Places365 do.
    md5 = hashlib.md5()
    # Stream the file so a multi-gigabyte archive is not loaded into memory.
    with path.open("rb") as handle:
        # Read until the file ends.
        while True:
            # One mebibyte keeps the loop simple and the disk busy.
            chunk = handle.read(CHUNK_BYTES)
            # An empty read means the hasher has seen every byte.
            if not chunk:
                # Leave the loop and return both digests.
                break
            # Update both digests from the same chunk.
            sha256.update(chunk)
            # MD5 is recorded even when the catalog only checks size.
            md5.update(chunk)
    # Hex digests are what the catalog and the logs store.
    return sha256.hexdigest(), md5.hexdigest()


def magic_matches(path: Path, prefix: str | None) -> bool:
    """Return True when prefix is empty or the file starts with that text."""
    # Some records have no magic check.
    if not prefix:
        # Size or checksum is the only check for those files.
        return True
    # Read only the prefix, not the whole archive.
    with path.open("rb") as handle:
        # The catalog stores the magic as a short ASCII string.
        found = handle.read(len(prefix.encode("ascii")))
    # Compare bytes so a UTF-8 BOM or HTML error page fails the check.
    return found == prefix.encode("ascii")


def free_bytes(path: Path) -> int:
    """Return free bytes on the filesystem that holds path."""
    # disk_usage needs an existing directory.
    path.mkdir(parents=True, exist_ok=True)
    # .free is the space still available to this user.
    return shutil.disk_usage(path).free


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the flags shared by every download script."""
    # The description is replaced by each script's own help when wanted.
    parser = argparse.ArgumentParser(description="Download one PhotoSpace dataset.")
    # Multi-gigabyte files stay skipped until this flag is present.
    parser.add_argument(
        "--confirm-large",
        # store_true so the default is to refuse large files.
        action="store_true",
        # The help text states the gate in one line.
        help="Allow files of 1 GiB or more.",
    )
    # Places365 says downloading the images accepts their terms.
    parser.add_argument(
        "--accept-terms",
        # Default is to leave terms-gated files untouched.
        action="store_true",
        # The Places365 terms are quoted in docs/LICENSES.md.
        help="Accept a dataset terms-of-use that is granted by downloading.",
    )
    # Objaverse GLB downloads use this flag. Other scripts ignore it.
    parser.add_argument(
        "--confirm-download",
        # Default refuses the Objaverse GLB download.
        action="store_true",
        # The help text names the asset download, not the annotation index.
        help="Allow the Objaverse furniture GLB download.",
    )
    # argv=None reads the real command line.
    return parser.parse_args(argv)


def _needs_gate(record: dict, args: argparse.Namespace) -> str | None:
    """Return a skip reason when a confirmation flag is missing."""
    # Large files need an explicit flag even if the catalog also sets a boolean.
    expected = record.get("expected_bytes") or 0
    # The catalog boolean covers files we want gated even under 1 GiB.
    large = bool(record.get("requires_confirm_large")) or expected >= LARGE_FILE_MIN_BYTES
    # Places365 val is under 1 GiB but still needs the terms flag.
    if large and not args.confirm_large:
        # The caller records this as awaiting approval.
        return "awaiting_approval"
    # Terms-gated files are not fetched until the flag is passed.
    if record.get("requires_accept_terms") and not args.accept_terms:
        # The caller records this separately from the size gate.
        return "awaiting_terms"
    # No gate blocked this file.
    return None


def _request(url: str, start_at: int) -> urllib.request.addinfourl:
    """Open a URL, sending a Range header when resuming."""
    # Identify the client on every request.
    headers = {"User-Agent": USER_AGENT}
    # A non-zero start asks the server to continue the partial file.
    if start_at > 0:
        # HTTP Range is inclusive of the first missing byte.
        headers["Range"] = f"bytes={start_at}-"
    # Build the request with those headers.
    request = urllib.request.Request(url, headers=headers)
    # timeout is the wait between socket operations, not the whole file.
    return urllib.request.urlopen(request, timeout=120)


def _already_good(dest: Path, record: dict) -> bool:
    """Return True when dest already matches the catalog size, magic, and checksum."""
    # A missing file still needs a download.
    if not dest.is_file():
        # The caller will create it.
        return False
    # Size is the first check because it is cheap.
    expected = record.get("expected_bytes")
    # When we know the size, a short or long file is not done.
    if expected is not None and dest.stat().st_size != expected:
        # The caller replaces the bad file.
        return False
    # Magic rejects an HTML error page that happens to have the right size.
    if not magic_matches(dest, record.get("magic_prefix")):
        # The caller deletes and retries.
        return False
    # Published MD5 is checked before we trust the file.
    if record.get("md5"):
        # Hash only when a published checksum exists, on the already-good path.
        _sha, md5 = file_sha256_md5(dest)
        # A mismatch means the file must be downloaded again.
        if md5.lower() != str(record["md5"]).lower():
            # Not good.
            return False
    # Size, magic, and any published MD5 all matched.
    return True


def download_record(record: dict, args: argparse.Namespace) -> str:
    """Download one catalog file. Return acquired, awaiting_approval, or awaiting_terms."""
    # Manual and skipped rows are not fetched by this function.
    if record.get("disposition") != "download":
        # The caller handles those dispositions.
        return str(record.get("disposition"))
    # Honor the size and terms gates before any socket opens.
    gated = _needs_gate(record, args)
    # A gate reason means this file is intentionally left for later.
    if gated:
        # Tell the terminal which file was left, and why.
        print(f"skip {record['file_id']}: {gated}")
        # The license log stores the same reason.
        return gated
    # Destination is relative to the repository root.
    dest = project_root() / record["relative_path"]
    # Create the dataset directory before the disk check.
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A finished file that already matches is not downloaded again.
    if _already_good(dest, record):
        # Hash it so the acquisition log has the checksum the verifier recomputes.
        sha256, md5 = file_sha256_md5(dest)
        # Record the size and both digests.
        _store_acquisition(record, dest.stat().st_size, sha256, md5, "acquired")
        # Report the skip so a second run is obviously a no-op.
        print(f"ok {record['file_id']}: already matches sha256={sha256}")
        # acquired means the verifier should hash this path.
        return "acquired"
    # A bad complete file is removed so the partial path starts clean.
    if dest.exists():
        # The next attempt writes a new partial.
        dest.unlink()
    # Partials sit beside the destination so resume survives a crash.
    partial = dest.with_suffix(dest.suffix + ".partial")
    # Expected size drives the disk check and the final size check.
    expected = record.get("expected_bytes")
    # A partial that already has every expected byte is finalized instead of resumed.
    if (
        expected is not None
        and partial.exists()
        and partial.stat().st_size == expected
        and magic_matches(partial, record.get("magic_prefix"))
    ):
        # Hash the finished partial before promoting it.
        sha256, md5 = file_sha256_md5(partial)
        # A published MD5 that does not match means the partial is corrupt.
        bad_md5 = bool(record.get("md5")) and md5.lower() != str(record["md5"]).lower()
        # Drop a corrupt full-size partial so the next attempt starts clean.
        if bad_md5:
            # Remove the bad partial.
            partial.unlink()
        else:
            # Promote the checked partial.
            os.replace(partial, dest)
            # Log the checksums.
            _store_acquisition(record, dest.stat().st_size, sha256, md5, "acquired")
            # Tell the terminal we reused the partial.
            print(f"acquired {record['file_id']}: finalized partial sha256={sha256}")
            # Done.
            return "acquired"
    # Bytes already in the partial count toward the size we still need.
    have = partial.stat().st_size if partial.exists() else 0
    # Unknown sizes still require the margin so a surprise file cannot fill the disk.
    remaining = (expected - have) if expected is not None else DISK_MARGIN_BYTES
    # Negative remaining means the partial is already too big.
    if remaining < 0:
        # Drop the bad partial and start over.
        partial.unlink()
        # Nothing is downloaded yet.
        have = 0
        # The full file is still required.
        remaining = expected if expected is not None else DISK_MARGIN_BYTES
    # Free space must cover the rest of the file plus the margin.
    available = free_bytes(dest.parent)
    # Refuse before writing when the disk cannot hold this file.
    if available < remaining + DISK_MARGIN_BYTES:
        # Stop this file rather than filling the disk.
        raise RuntimeError(
            f"Not enough free disk for {record['file_id']}: "
            f"need about {remaining + DISK_MARGIN_BYTES} bytes, have {available}."
        )
    # How many connection closes in a row added no bytes.
    stalls = 0
    # The last error is reported if the transfer stops making progress.
    last_error: Exception | None = None
    # Servers often close a long transfer early. Resume until the file is complete.
    while stalls < MAX_ATTEMPTS:
        # Bytes on disk before this connection.
        before = partial.stat().st_size if partial.exists() else 0
        # A previous iteration already wrote every expected byte.
        if expected is not None and before == expected:
            # Leave the loop and verify the full partial.
            break
        # Tell the terminal this connection is starting.
        print(f"get {record['file_id']}: resume from byte {before}")
        try:
            # Open the connection, with Range when we already have bytes.
            with _request(record["url"], before) as response:
                # 206 means the server honored Range. 200 means it sent the whole file.
                status = getattr(response, "status", 200)
                # Do not wipe a partial when the server ignores Range.
                if before > 0 and status != 206:
                    # Count this as a stall and keep the bytes we already have.
                    stalls += 1
                    # Remember why this connection was skipped.
                    last_error = RuntimeError(f"{record['file_id']} range was ignored")
                    # Show the skip.
                    print(f"retry {record['file_id']}: range ignored", file=sys.stderr)
                    # Try the range request again.
                    continue
                # Append only when the server confirmed a partial response.
                mode = "ab" if before > 0 and status == 206 else "wb"
                # Download into the partial path until this connection ends.
                with partial.open(mode) as handle:
                    # Count bytes in this connection for the progress line.
                    seen = 0
                    # Read until the server closes the body.
                    while True:
                        # One chunk per iteration.
                        chunk = response.read(CHUNK_BYTES)
                        # Empty chunk ends the body, which may be before the full file.
                        if not chunk:
                            # Stop reading this connection.
                            break
                        # Persist the chunk before the next read.
                        handle.write(chunk)
                        # Track progress inside this connection.
                        seen += len(chunk)
                        # Print every 64 MiB, and also once for a short file.
                        if seen % (64 * CHUNK_BYTES) < CHUNK_BYTES:
                            # Flush so the reported size includes this chunk.
                            handle.flush()
                            # Include the partial size, which includes resumed bytes.
                            print(f"  {record['file_id']}: {partial.stat().st_size} bytes")
        # A dropped connection is fine when the partial grew.
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # Remember the latest failure for the final message.
            last_error = error
            # Show the drop without a traceback.
            print(f"retry {record['file_id']}: {error}", file=sys.stderr)
        # Bytes on disk after this connection.
        after = partial.stat().st_size if partial.exists() else 0
        # A body longer than the catalog size is the wrong object.
        if expected is not None and after > expected:
            # Drop it and count a stall.
            partial.unlink()
            # This connection did not help.
            stalls += 1
            # Remember why.
            last_error = RuntimeError(f"{record['file_id']} grew past {expected} bytes")
            # Try again from an empty partial.
            continue
        # New bytes mean the transfer is still healthy.
        if after > before:
            # Reset the stall counter.
            stalls = 0
            # The catalog size is complete, or this file has no expected size.
            if expected is None or after == expected:
                # Leave the loop and verify.
                break
            # Otherwise open another connection at the new offset.
            continue
        # This connection added nothing.
        stalls += 1
        # Back off before the next try.
        time.sleep(min(stalls * 2, 10))
    # No-progress retries are exhausted and the file is still short.
    if expected is not None and (not partial.exists() or partial.stat().st_size != expected):
        # Stop rather than pretending a short file is complete.
        raise RuntimeError(f"download failed for {record['file_id']}: {last_error}")
    # Magic is checked on the finished partial.
    if not magic_matches(partial, record.get("magic_prefix")):
        # An error page is not a dataset archive.
        raise RuntimeError(f"{record['file_id']} magic mismatch")
    # Hash the finished partial once.
    sha256, md5 = file_sha256_md5(partial)
    # Compare a published MD5 when the catalog has one.
    if record.get("md5") and md5.lower() != str(record["md5"]).lower():
        # The bytes are the wrong object.
        raise RuntimeError(f"{record['file_id']} md5 {md5} != {record['md5']}")
    # Move the checked partial to the final name.
    os.replace(partial, dest)
    # Store both digests for the verifier.
    _store_acquisition(record, dest.stat().st_size, sha256, md5, "acquired")
    # Tell the terminal the file is in place.
    print(f"acquired {record['file_id']}: {dest.stat().st_size} bytes sha256={sha256}")
    # This file is done.
    return "acquired"


def _store_acquisition(
    record: dict,
    size: int,
    sha256: str,
    md5: str,
    status: str,
) -> None:
    """Upsert one file into the acquisition log."""

    # Mutate the log while the metadata lock is held.
    def update(payload: dict) -> None:
        # The files map is keyed by file_id.
        files = payload.setdefault("files", {})
        # Replace any earlier row for this file.
        files[record["file_id"]] = {
            # The id matches the catalog.
            "file_id": record["file_id"],
            # Which dataset this byte stream belongs to.
            "dataset_id": record["dataset_id"],
            # Repo-relative path the verifier opens.
            "relative_path": record["relative_path"],
            # Size after the successful write.
            "bytes": size,
            # Our SHA-256 of those bytes.
            "sha256": sha256,
            # MD5 of those bytes, compared to the host when one was published.
            "md5": md5,
            # acquired, or a later status if a caller reuses this helper.
            "status": status,
            # The URL that produced the file.
            "url": record.get("url"),
        }

    # Read and write the acquisition log under the lock.
    _with_log_lock(acquisition_log_path(), update)


def record_file_status(record: dict, status: str) -> None:
    """Record a file that was skipped or is waiting, without inventing a checksum."""

    # Mutate the log while the metadata lock is held.
    def update(payload: dict) -> None:
        # Ensure the files object exists.
        files = payload.setdefault("files", {})
        # Keep a previous acquired row if we are only skipping a re-run.
        previous = files.get(record["file_id"], {})
        # Do not wipe a checksum that already matched.
        if previous.get("status") == "acquired" and status != "acquired":
            # The file is already on disk from an earlier run.
            return
        # Waiting rows have no checksum yet.
        files[record["file_id"]] = {
            # Catalog id.
            "file_id": record["file_id"],
            # Dataset id.
            "dataset_id": record["dataset_id"],
            # Where the file will land.
            "relative_path": record["relative_path"],
            # The expected size, which is not a measured size.
            "bytes": record.get("expected_bytes"),
            # No hash until the file is acquired.
            "sha256": None,
            # Published MD5 is copied when the catalog has one.
            "md5": record.get("md5"),
            # awaiting_approval, awaiting_terms, or another non-acquired status.
            "status": status,
            # The URL we would fetch.
            "url": record.get("url"),
        }

    # Read and write the acquisition log under the lock.
    _with_log_lock(acquisition_log_path(), update)


def write_license_entry(dataset: dict, file_statuses: list[dict]) -> None:
    """Upsert one dataset into the license log, including per-file status."""

    # Mutate the license log while the metadata lock is held.
    def update(payload: dict) -> None:
        # The rest of this function fills the entry and stores it.
        _write_license_unlocked(payload, dataset, file_statuses)

    # Read and write the license log under the lock.
    _with_log_lock(license_log_path(), update)


def _write_license_unlocked(payload: dict, dataset: dict, file_statuses: list[dict]) -> None:
    """Fill one license-log entry. Caller holds the log lock."""
    # Entries are keyed by dataset id.
    entries = payload.setdefault("entries", {})
    # Derive a dataset status from the file rows.
    statuses = {row["status"] for row in file_statuses}
    # No downloadable files means the catalog disposition is the status.
    if not file_statuses:
        # manual, skipped, or pending_user.
        status = dataset["disposition"]
    # Every downloadable file is on disk.
    elif statuses <= {"acquired"}:
        # The dataset's downloadable Phase 1 files are present.
        status = "acquired"
    # A mix of acquired and waiting files.
    elif "acquired" in statuses:
        # Part of the dataset is on disk.
        status = "partial"
    # Nothing acquired, and at least one file waits on a flag.
    elif "awaiting_approval" in statuses or "awaiting_terms" in statuses:
        # The user has not approved this download yet.
        status = "awaiting_approval"
    # Fall back to the set of statuses joined for debugging.
    else:
        # Unusual statuses are stored as a single label.
        status = dataset["disposition"]
    # Map catalog dispositions that are not downloads onto log statuses.
    if dataset["disposition"] == "manual":
        # Registration is still required even if a note file exists.
        status = "manual_registration"
    # A dataset we checked and will not fetch.
    if dataset["disposition"] == "skipped":
        # FurniScene uses this status.
        status = "skipped"
    # Objaverse GLBs stay pending until the asset download records acquired.
    if dataset["disposition"] == "pending_user" and status != "acquired":
        # The category plan can be on disk while the GLBs are not.
        status = "awaiting_approval"
    # Replace the entry for this dataset.
    entries[dataset["dataset_id"]] = {
        # Stable id used by the verifier.
        "dataset_id": dataset["dataset_id"],
        # Human name.
        "name": dataset["name"],
        # License label recorded from the official page.
        "license_name": dataset["license_name"],
        # Page we checked.
        "source_url": dataset["source_url"],
        # acquired, partial, awaiting_approval, manual_registration, or skipped.
        "status": status,
        # Longer note from the catalog.
        "notes": dataset["notes"],
        # Per-file statuses for this run.
        "files": file_statuses,
    }


def run_dataset(dataset_id: str, argv: list[str] | None = None) -> int:
    """Download the catalog files for one dataset and update both logs."""
    # Flags for this invocation.
    args = parse_args(argv)
    # The shared catalog.
    catalog = load_catalog()
    # Find the dataset object.
    dataset = next(item for item in catalog["datasets"] if item["dataset_id"] == dataset_id)
    # Files that belong to this dataset.
    records = [item for item in catalog["files"] if item["dataset_id"] == dataset_id]
    # Status rows collected for the license log.
    file_statuses: list[dict] = []
    # Download or skip each file.
    try:
        # Preserve catalog order.
        for record in records:
            # Only disposition download opens a socket.
            if record.get("disposition") != "download":
                # Record the non-download disposition and continue.
                file_statuses.append(
                    {"file_id": record["file_id"], "status": record["disposition"]}
                )
                # Next file.
                continue
            # Fetch or skip.
            status = download_record(record, args)
            # Persist waiting rows. acquired rows are stored inside download_record.
            if status != "acquired":
                # No checksum for a file we did not fetch.
                record_file_status(record, status)
            # Remember the status for the license entry.
            file_statuses.append({"file_id": record["file_id"], "status": status})
    # A disk, checksum, or network failure fails the script.
    except (RuntimeError, urllib.error.URLError, OSError) as error:
        # Print the reason.
        print(f"error: {error}", file=sys.stderr)
        # Non-zero so a caller can see the failure.
        return 1
    # Always update the license log, including after intentional skips.
    write_license_entry(dataset, file_statuses)
    # Zero means no transfer failed. Waiting files are not failures.
    return 0
