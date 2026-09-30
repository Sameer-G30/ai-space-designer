"""Worker entry point: run with .venv-train/bin/python -m spacedesigner.perception.worker."""

# Annotations on Python 3.11.
from __future__ import annotations

# Command-line arguments.
import argparse

# Result is printed as JSON.
import json

# Exit codes.
import sys

# Pillow opens the sanitized file.
from PIL import Image

# The full pipeline.
from spacedesigner.perception.pipeline import run_pipeline


# Read one image file and print the result as one JSON line.
def main() -> int:
    """Return 0 and print JSON on success; return 1 and print an error JSON on failure."""
    # Parse arguments.
    parser = argparse.ArgumentParser(description=__doc__)
    # Path of the sanitized PNG.
    parser.add_argument("image")
    # Optional focal length read from EXIF before it was stripped.
    parser.add_argument("--focal-35mm", type=float, default=None)
    # Read the values.
    args = parser.parse_args()
    # Any failure becomes a readable JSON error.
    try:
        # Run every stage.
        result = run_pipeline(Image.open(args.image).convert("RGB"), args.focal_35mm)
    # Missing weights and unusable photos both land here.
    except Exception as exc:
        # One JSON line with the reason.
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        # Non-zero exit tells the caller.
        return 1
    # One JSON line with the result; the last stdout line is the payload.
    print(json.dumps(result))
    # Success.
    return 0


# Run when executed as a module.
if __name__ == "__main__":
    # Propagate the exit code.
    sys.exit(main())
