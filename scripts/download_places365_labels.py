"""Fetch only the two small official Places365 label files (no images, no train tar)."""

# Annotations on Python 3.11.
from __future__ import annotations

# SHA-256 and MD5 for the acquisition log.
import hashlib

# Writes the log rows.
import json

# Prints progress.
import sys

# HTTP Range requests.
import urllib.request

# Path objects for repo-relative files.
from pathlib import Path

# Official category list (about 6 KB) from the Places365 GitHub repository.
CATEGORIES_URL = (
    "https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt"
)

# Official file-list tar (about 64 MiB, plain text lists). We read only the val member with Range.
FILELIST_URL = "https://data.csail.mit.edu/places/places365/filelist_places365-standard.tar"

# The val label list is this member of the file-list tar.
VAL_MEMBER = "places365_val.txt"

# Tar headers are 512 bytes.
BLOCK = 512

# Identifies this client to the hosts.
USER_AGENT = "PhotoSpace-Phase2a/0.1 (research label fetch)"


def root() -> Path:
    """Return the repository root."""
    # This file lives in scripts/.
    return Path(__file__).resolve().parents[1]


def fetch(url: str, start: int | None = None, length: int | None = None) -> bytes:
    """GET url, optionally only bytes [start, start + length)."""
    # Base request with our user agent.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # A Range header asks for just one slice of the tar.
    if start is not None and length is not None:
        # Inclusive end byte per RFC 7233.
        request.add_header("Range", f"bytes={start}-{start + length - 1}")
    # Read the whole (small) response body.
    with urllib.request.urlopen(request, timeout=60) as response:
        # Return raw bytes.
        return response.read()


def fetch_tar_member(url: str, member: str) -> bytes:
    """Walk tar headers with Range reads and return the bytes of one member."""
    # Start at the first header.
    offset = 0
    # Stop after a bounded number of members so a bad file cannot loop forever.
    for _ in range(64):
        # Read one 512-byte header.
        header = fetch(url, offset, BLOCK)
        # An all-zero block ends the archive.
        if not header.strip(b"\0"):
            # Member not found.
            break
        # Name is the first 100 bytes, NUL padded.
        name = header[:100].split(b"\0", 1)[0].decode("utf-8")
        # Size is octal ASCII at bytes 124..136.
        size = int(header[124:136].split(b"\0", 1)[0].strip() or b"0", 8)
        # Data starts right after the header.
        data_start = offset + BLOCK
        # Match on the base name so a leading directory does not matter.
        if name.rsplit("/", 1)[-1] == member:
            # Fetch exactly the member bytes.
            return fetch(url, data_start, size)
        # Skip the data, rounded up to whole blocks.
        offset = data_start + ((size + BLOCK - 1) // BLOCK) * BLOCK
    # The caller handles a missing member.
    raise SystemExit(f"member {member} not found in {url}")


def record(log: dict, file_id: str, path: Path, url: str) -> None:
    """Add one acquired row to the acquisition log."""
    # Read the bytes back so the hash matches the file on disk.
    payload = path.read_bytes()
    # Same field names as the Phase 1 rows.
    log["files"][file_id] = {
        "file_id": file_id,
        "dataset_id": "places365",
        "relative_path": str(path.relative_to(root())),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "md5": hashlib.md5(payload).hexdigest(),
        "status": "acquired",
        "url": url,
    }


def main() -> int:
    """Download both files and log them."""
    # Destination folder already exists from Phase 1.
    folder = root() / "datasets" / "raw" / "places365"
    # Make sure it exists.
    folder.mkdir(parents=True, exist_ok=True)
    # Category strings.
    categories = folder / "categories_places365.txt"
    # Val labels.
    val_labels = folder / "places365_val.txt"
    # Fetch and write the category list.
    categories.write_bytes(fetch(CATEGORIES_URL))
    # Fetch and write only the val member of the file-list tar.
    val_labels.write_bytes(fetch_tar_member(FILELIST_URL, VAL_MEMBER))
    # Acquisition log path.
    log_path = root() / "datasets" / "metadata" / "acquisition_log.json"
    # Load the existing log.
    log = json.loads(log_path.read_text(encoding="utf-8"))
    # Add the two rows.
    record(log, "places365_categories", categories, CATEGORIES_URL)
    # Second row.
    record(log, "places365_val_labels", val_labels, FILELIST_URL + "#" + VAL_MEMBER)
    # Save with the same two-space indent as the other logs.
    log_path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    # Report sizes.
    print(f"categories {categories.stat().st_size} bytes, val labels {val_labels.stat().st_size}")
    # Success.
    return 0


# Script entry point.
if __name__ == "__main__":
    # Propagate the exit code.
    sys.exit(main())
