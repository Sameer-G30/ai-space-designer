"""Phase 2a: export NYU Depth V2 labeled frames with masked depth and taxonomy labels."""

# Prints the stats.
import json

# The cleaner lives in the package, not in the API.
from spacedesigner.data import nyu

# Script entry point.
if __name__ == "__main__":
    # Run the export and show the stats.
    print(json.dumps(nyu.run(), indent=2))
