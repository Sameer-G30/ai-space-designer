"""Record the manual 3D-FRONT / 3D-FUTURE registration. This does not download."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared helper writes the license-log row for a manual dataset.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset writes the license log and does not fetch manual datasets.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # Registration stays with the user. See docs/DATASETS.md for the steps.
    raise SystemExit(run_dataset("3d_front_future"))
