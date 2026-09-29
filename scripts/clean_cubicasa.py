"""Phase 2a: parse CubiCasa5K SVGs into polygons and masks. Does not train a parser."""

# Prints the stats.
import json

# The cleaner lives in the package, not in the API.
from spacedesigner.data import cubicasa

# Script entry point.
if __name__ == "__main__":
    # Run the parse and show the stats.
    print(json.dumps(cubicasa.run(), indent=2))
