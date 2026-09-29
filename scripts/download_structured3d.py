"""Download the four Structured3D files from the agreement link list."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared downloader reads the catalog rows for this dataset.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset fetches only the files whose dataset_id is structured3d.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # The bbox and perspective zips are over 1 GiB and need --confirm-large.
    raise SystemExit(run_dataset("structured3d"))
