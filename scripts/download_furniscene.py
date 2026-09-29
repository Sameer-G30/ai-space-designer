"""Record that FurniScene has no public download. This does not fetch data."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared helper writes the skipped license-log row.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset writes the license log and does not invent a download URL.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # The skip reason is the catalog note checked on 2026-09-29.
    raise SystemExit(run_dataset("furniscene"))
