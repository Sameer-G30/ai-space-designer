"""Download the Places365-Standard 256x256 train and val archives."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared downloader reads the catalog row for this dataset.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset fetches only the files whose dataset_id is places365.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # Both archives need --accept-terms. The train archive also needs --confirm-large.
    raise SystemExit(run_dataset("places365"))
