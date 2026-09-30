"""Phase 7a: fine-tune the room classifier. Run with .venv-train/bin/python."""

# Prints the metrics.
import json

# Training code lives in the package.
from spacedesigner.training import classifier

# Script entry point.
if __name__ == "__main__":
    # Train, then print the held-out summary without the big matrix.
    result = classifier.train()
    # Show the headline numbers.
    print(json.dumps({k: v for k, v in result.items() if k != "test"}, indent=2))
    # Show the test top-1.
    print("test top1", result["test"]["top1"], "n", result["test"]["n"])
