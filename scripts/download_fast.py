"""Resume Phase 1 archives with many HTTP range connections per file."""

# Annotations for optional values on Python 3.11.
from __future__ import annotations

# Integer byte counts and pwrite.
import os

# curl is the client that this host actually answers.
import subprocess

# Repo paths and stderr.
import sys

# Runs one worker pool per archive.
import threading

# Sleeps between progress lines.
import time

# Path objects for the partial files.
from pathlib import Path

# Lets this file import the shared catalog helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Catalog, hashing, and the acquisition log.
from download_common import (  # noqa: E402
    _store_acquisition,
    file_sha256_md5,
    load_catalog,
    magic_matches,
    project_root,
)

# Earlier runs stored progress as 8 MiB slices.
OLD_RANGE_BYTES = 8 * 1024 * 1024

# Each parallel request fetches this many bytes. Small slices finish before the socket times out.
RANGE_BYTES = 512 * 1024

# Two connections are faster on this host than one, and four get slower.
WORKERS_PER_FILE = 2


def fetch_range(url: str, start: int, end: int) -> bytes:
    """Download inclusive byte range [start, end] with curl."""
    # curl is the client this host answers. A 206 body is written to stdout.
    result = subprocess.run(
        [
            "curl",
            "-fsS",
            "--retry",
            "2",
            "--max-time",
            "60",
            "-A",
            "Mozilla/5.0",
            "-r",
            f"{start}-{end}",
            url,
        ],
        check=False,
        capture_output=True,
    )
    # A non-zero status is a failed slice.
    if result.returncode != 0:
        # Keep the short curl error for the retry loop.
        detail = result.stderr.decode("utf-8", "replace").strip()
        # Tell the caller to try this slice again.
        raise RuntimeError(detail or f"curl exit {result.returncode}")
    # The slice body.
    body = result.stdout
    # The slice must be exactly the requested length.
    if len(body) != end - start + 1:
        # A short body is a failed slice.
        raise RuntimeError(f"short range {start}-{end}: got {len(body)}")
    # The exact bytes for this slice.
    return body


def archive_tail_ok(path: Path, magic_prefix: str | None) -> bool:
    """Return whether a full-size zip still has its end-of-central-directory record."""
    # Only zip files are rejected when the tail is empty.
    if magic_prefix != "PK":
        # MATLAB, tar, and PDF files are judged by size and checksum.
        return True
    # Open the candidate and look for the zip end record.
    try:
        # Read the ending window.
        with path.open("rb") as handle:
            # Length of the file on disk.
            handle.seek(0, os.SEEK_END)
            # Byte length.
            size = handle.tell()
            # The end record is in the last 64 KiB plus the 22-byte header.
            handle.seek(max(0, size - 65557))
            # Bytes that must contain PK\\x05\\x06.
            tail = handle.read()
    # A file that cannot be read is not a finished archive.
    except OSError:
        # Ask the caller to fetch it again.
        return False
    # Present when the zip central directory was actually written.
    return b"PK\x05\x06" in tail


def download_record(record: dict, progress: dict[str, int]) -> None:
    """Finish one catalog file using parallel range requests."""
    # Final path relative to the repository root.
    dest = project_root() / record["relative_path"]
    # In-progress bytes stay beside the final name.
    partial = dest.with_suffix(dest.suffix + ".partial")
    # Bitmap of finished 8 MiB slices.
    bitmap_path = Path(str(partial) + ".map")
    # Catalog size. Every accelerated file has one.
    expected = int(record["expected_bytes"])
    # Parent folder for this archive.
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A finished file is left untouched when its ending is real.
    if (
        dest.is_file()
        and dest.stat().st_size == expected
        and archive_tail_ok(dest, record.get("magic_prefix"))
    ):
        # Count it as already received.
        progress[record["file_id"]] = expected
        # Nothing to fetch.
        print(f"ok {record['file_id']}: already complete")
        # Leave this archive.
        return
    # A full-size file with an empty zip tail is not a finished archive.
    if dest.is_file() and dest.stat().st_size == expected:
        # Drop it so the range download starts from an empty partial.
        dest.unlink()
    # How many slices cover the file.
    slice_count = (expected + RANGE_BYTES - 1) // RANGE_BYTES
    # How many 8 MiB slices the previous fast run used.
    old_count = (expected + OLD_RANGE_BYTES - 1) // OLD_RANGE_BYTES
    # One byte per slice, 1 when that slice is on disk.
    bitmap = bytearray(slice_count)
    # A saved bitmap from this slice size.
    saved = bitmap_path.read_bytes() if bitmap_path.is_file() else b""
    # Resume the current slice size.
    if len(saved) == slice_count:
        # Load the saved bitmap.
        bitmap = bytearray(saved)
    # Expand an 8 MiB bitmap into 512 KiB slices.
    elif len(saved) == old_count:
        # Sixteen small slices fit in one old slice.
        scale = OLD_RANGE_BYTES // RANGE_BYTES
        # Walk the old flags.
        for index, flag in enumerate(saved):
            # Only completed old slices are kept.
            if flag:
                # Mark each small slice inside that old slice.
                for offset in range(scale):
                    # Index in the new bitmap.
                    new_index = index * scale + offset
                    # Ignore a tail past the end of the file.
                    if new_index < slice_count:
                        # This small slice is already on disk.
                        bitmap[new_index] = 1
    # A short partial from the single-connection downloader, before allocation.
    elif partial.is_file() and partial.stat().st_size < expected:
        # Bytes already fetched.
        have = partial.stat().st_size
        # Mark every slice that ends at or before the saved prefix.
        for index in range(have // RANGE_BYTES):
            # Mark the slice done.
            bitmap[index] = 1
    # Create or extend the partial up to the full size so later slices can be written in place.
    file_handle = os.open(str(partial), os.O_RDWR | os.O_CREAT, 0o644)
    # Allocate the full archive. Existing prefix bytes stay in place.
    os.posix_fallocate(file_handle, 0, expected)
    # Save the bitmap before any worker runs.
    bitmap_path.write_bytes(bitmap)
    # Count bytes already on disk, capped at the archive size.
    progress[record["file_id"]] = min(expected, sum(bitmap) * RANGE_BYTES)
    # Guards the bitmap and the claim index.
    lock = threading.Lock()
    # Next slice index to offer a worker.
    cursor = 0

    def claim() -> int | None:
        """Return the next unfinished slice index, or None when all are claimed."""
        # The cursor is shared by every worker.
        nonlocal cursor
        # Only one worker updates the cursor.
        with lock:
            # Scan from the cursor to the end.
            while cursor < slice_count:
                # This slice still needs bytes.
                if bitmap[cursor] == 0:
                    # Hand it out and move past it.
                    index = cursor
                    # Next claim starts after this slice.
                    cursor += 1
                    # The caller downloads this slice.
                    return index
                # Skip slices that are already stored.
                cursor += 1
        # No unfinished slice remains.
        return None

    def mark(index: int) -> None:
        """Record that one slice is on disk."""
        # Publish the bitmap update.
        with lock:
            # This slice is complete.
            bitmap[index] = 1
            # Persist the bitmap so a crash can resume.
            bitmap_path.write_bytes(bitmap)
            # Bytes received, capped at the file size.
            received = min(expected, sum(bitmap) * RANGE_BYTES)
            # Share progress with the status line.
            progress[record["file_id"]] = received

    def worker() -> None:
        """Download claimed slices until none remain."""
        # Keep taking work.
        while True:
            # Next hole in the file.
            index = claim()
            # No holes left.
            if index is None:
                # This worker is finished.
                return
            # First byte of the slice.
            start = index * RANGE_BYTES
            # Last inclusive byte of the slice.
            end = min(start + RANGE_BYTES, expected) - 1
            # Retry this slice until it is stored.
            while True:
                try:
                    # Fetch the slice.
                    body = fetch_range(record["url"], start, end)
                    # Write it at the right offset.
                    os.pwrite(file_handle, body, start)
                    # Remember the slice.
                    mark(index)
                    # Move to another slice.
                    break
                # A dropped transfer retries this same slice.
                except Exception:
                    # Wait a moment before the same slice is tried again.
                    time.sleep(2)
                    # Try this slice again.
                    continue

    # Start the pool for this archive.
    threads = [
        threading.Thread(target=worker, name=record["file_id"])
        for _ in range(WORKERS_PER_FILE)
    ]
    # Launch every connection.
    for thread in threads:
        # Run alongside the other archives.
        thread.start()
    # Wait until every slice of this archive is stored.
    for thread in threads:
        # Join this worker.
        thread.join()
    # Close the allocated file.
    os.close(file_handle)
    # The bitmap must be full before we rename.
    if any(flag == 0 for flag in bitmap):
        # Leave the partial in place.
        raise RuntimeError(f"{record['file_id']} still has missing slices")
    # Magic rejects an HTML error page.
    if not magic_matches(partial, record.get("magic_prefix")):
        # Do not rename a bad download.
        raise RuntimeError(f"{record['file_id']} magic mismatch")
    # Hash the finished archive once.
    sha256, md5 = file_sha256_md5(partial)
    # Compare a published MD5 when the catalog has one.
    if record.get("md5") and md5.lower() != str(record["md5"]).lower():
        # Keep the partial for inspection.
        raise RuntimeError(f"{record['file_id']} md5 {md5} != {record['md5']}")
    # Move the checked partial to the catalog name.
    os.replace(partial, dest)
    # The bitmap is no longer needed.
    bitmap_path.unlink(missing_ok=True)
    # Record the checksum for the verifier.
    _store_acquisition(record, expected, sha256, md5, "acquired")
    # Tell the terminal this archive is done.
    print(f"acquired {record['file_id']}: {expected} bytes sha256={sha256}")


def incomplete_records(catalog: dict) -> list[dict]:
    """Return download rows whose final file is not the expected size yet."""
    # Rows that still need bytes.
    pending: list[dict] = []
    # Walk the catalog in order.
    for record in catalog["files"]:
        # Skip manual and already-finished bookkeeping rows.
        if record.get("disposition") != "download":
            # Not a file this script fetches.
            continue
        # Every accelerated file has a known size.
        if not record.get("expected_bytes"):
            # Nothing to split into ranges.
            continue
        # Final location.
        dest = project_root() / record["relative_path"]
        # Keep going when the final file is the right size and a real archive.
        if (
            dest.is_file()
            and dest.stat().st_size == record["expected_bytes"]
            and archive_tail_ok(dest, record.get("magic_prefix"))
        ):
            # This archive is done.
            continue
        # This archive still needs a faster resume.
        pending.append(record)
    # The archives to fetch.
    return pending


def main() -> int:
    """Resume every incomplete catalog archive with parallel connections."""
    # Shared received-byte counts for the status line.
    progress: dict[str, int] = {}
    # Catalog of Phase 1 files.
    records = incomplete_records(load_catalog())
    # Nothing left to fetch.
    if not records:
        # Say so.
        print("nothing incomplete")
        # Success.
        return 0
    # One coordinator thread per archive.
    threads = []
    # Failures from archives are collected here.
    errors: list[str] = []
    # Lock around the error list.
    error_lock = threading.Lock()

    def run(record: dict) -> None:
        """Download one archive and remember a failure."""
        try:
            # Fetch the remaining slices.
            download_record(record, progress)
        # Keep the other archives going.
        except Exception as error:  # noqa: BLE001
            # Record the message.
            with error_lock:
                # Store the file id and the reason.
                errors.append(f"{record['file_id']}: {error}")

    # Build one thread per incomplete archive.
    for record in records:
        # Name the thread after the file.
        thread = threading.Thread(target=run, args=(record,), name=record["file_id"])
        # Keep the list for joining.
        threads.append(thread)
        # Start this archive.
        thread.start()
    # Status loop until every archive thread exits.
    while any(thread.is_alive() for thread in threads):
        # Snapshot the byte counters.
        total = sum(progress.values())
        # One short line of progress.
        print(f"received_bytes {total}", flush=True)
        # Wait before the next line.
        time.sleep(10)
    # Collect the workers.
    for thread in threads:
        # Wait for this archive.
        thread.join()
    # Report failures.
    for message in errors:
        # One failure per line.
        print(f"error: {message}", file=sys.stderr)
    # Non-zero when any archive failed.
    return 1 if errors else 0


# Script entry point.
if __name__ == "__main__":
    # Propagate the status code.
    raise SystemExit(main())
