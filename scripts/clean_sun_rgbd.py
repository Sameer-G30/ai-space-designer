"""Phase 2a: clean SUN RGB-D boxes into YOLO labels. Does not train anything."""

# Prints the stats.
import json

# The cleaner lives in the package, not in the API.
from spacedesigner.data import sun_rgbd

# Script entry point.
if __name__ == "__main__":
    # Run the export and show the stats.
    print(json.dumps(sun_rgbd.run(), indent=2))
