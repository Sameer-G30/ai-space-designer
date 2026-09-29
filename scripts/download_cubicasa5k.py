"""Download the CubiCasa5K floor-plan archive from Zenodo."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared downloader reads the catalog row for this dataset.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset fetches only the files whose dataset_id is cubicasa5k.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # The zip is about 5.1 GiB and stays skipped unless --confirm-large is passed.
    raise SystemExit(run_dataset("cubicasa5k"))
