"""Phase 7a: fine-tune YOLO-World-S and report mAP vs zero-shot. Use .venv-train/bin/python."""

# Prints the metrics.
import json

# Training code lives in the package.
from spacedesigner.training import detector

# Script entry point.
if __name__ == "__main__":
    # Train and score.
    print(json.dumps(detector.train(), indent=2))
