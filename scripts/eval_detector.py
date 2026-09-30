"""Phase 7a: re-score the detector and its zero-shot baseline. Use .venv-train/bin/python."""

# Prints the metrics.
import json

# Evaluation code lives in the package.
from spacedesigner.training import detector

# Script entry point.
if __name__ == "__main__":
    # Score both models on the test split.
    print(json.dumps(detector.evaluate_saved(), indent=2))
