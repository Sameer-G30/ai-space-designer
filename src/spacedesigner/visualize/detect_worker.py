"""Re-run the saved Phase 7a detector on one generated image, then exit.

The parent spawns this with .venv-train so ultralytics is not imported in the API process.
This module does not train and does not download weights.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Image path.
import argparse

# One JSON line.
import json

# Exit code.
import sys

# Pillow opens the composited image.
from PIL import Image


# Detect and print boxes in the image's pixel space.
def main() -> int:
    """Return 0 and one JSON line. A missing weight file is an error JSON, not a download."""
    # Arguments.
    parser = argparse.ArgumentParser(description=__doc__)
    # Composited PNG.
    parser.add_argument("image")
    # Parsed.
    args = parser.parse_args()
    # Failures stay on the last stdout line.
    try:
        # Load, detect, unload.
        _detect(args.image)
    # Missing weights or a runtime error.
    except Exception as exc:
        # The parent records not_run.
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        # Non-zero so a crash is visible, but the parent also reads the JSON.
        return 1
    # Success already printed.
    return 0


# Import the detector only when this process is the worker.
def _detect(path: str) -> None:
    """Print detections and the peak MiB, then free the GPU."""
    # The chat model must not share the GPU with the detector.
    from spacedesigner.perception.runner import unload_llm
    from spacedesigner.perception.stages import Detector

    # Drop qwen2.5:7b if it is still resident.
    unload_llm()
    # CUDA torch, when this venv has it.
    import torch

    # Reset the peak so this process does not inherit another counter.
    if torch.cuda.is_available():
        # Start at zero.
        torch.cuda.reset_peak_memory_stats()
    # The saved fine-tune. Detector raises MissingWeights when the file is absent.
    detector = Detector()
    # One image.
    found = detector(Image.open(path).convert("RGB"))
    # Free the model and read the peak.
    peak = detector.close()
    # JSON-safe boxes.
    detections = [
        {
            "category": name,
            "score": score,
            "xyxy": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
        }
        for name, score, box in found
    ]
    # Last stdout line.
    print(json.dumps({"detections": detections, "peak_vram_mib": round(float(peak), 1)}))


# Run as a module.
if __name__ == "__main__":
    # Propagate the code.
    sys.exit(main())
