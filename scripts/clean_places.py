"""Phase 2a: build the room-type dataset from Places365 val_256 and SUN RGB-D scenes."""

# Prints the stats.
import json

# The cleaner lives in the package, not in the API.
from spacedesigner.data import places

# Script entry point.
if __name__ == "__main__":
    # Run the build and show the stats.
    print(json.dumps(places.run(), indent=2))
