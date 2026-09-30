"""Phase 7a: score the saved room classifier on a held-out split. Use .venv-train/bin/python."""

# Command-line options and JSON output.
import argparse
import json

# Evaluation code lives in the package.
from spacedesigner.training import classifier

# Script entry point.
if __name__ == "__main__":
    # One option: which split to score.
    parser = argparse.ArgumentParser()
    # Default is the untouched test split.
    parser.add_argument("--split", default="test", choices=["val", "test"])
    # Parse the command line.
    args = parser.parse_args()
    # Score the saved weights.
    result = classifier.evaluate_saved(args.split)
    # Print everything including the confusion matrix.
    print(json.dumps(result, indent=2))
