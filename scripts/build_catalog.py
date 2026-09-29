"""Build datasets/metadata/cleaning/furniture_catalog.jsonl (synthetic INR prices)."""

# Entry point for the builder.
from spacedesigner.data.catalog import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Build and print the stats.
    for key, value in run().items():
        # One line per field.
        print(f"{key}: {value}")
