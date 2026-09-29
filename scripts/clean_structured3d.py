"""Phase 2a: extract Structured3D room and plane labels from the annotation and bbox zips."""

# Prints the stats.
import json

# The cleaner lives in the package, not in the API.
from spacedesigner.data import structured3d

# Script entry point.
if __name__ == "__main__":
    # Run the extraction and show the stats.
    print(json.dumps(structured3d.run(), indent=2))
