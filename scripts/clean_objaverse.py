"""Clean the 160 acquired Objaverse GLBs into datasets/processed/objaverse/."""

# Entry point for the cleaner.
from spacedesigner.data.objaverse_clean import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Clean everything and print the counts without the per-asset list.
    result = run()
    # Drop the long list for the console.
    result.pop("dropped_assets", None)
    # Print each field.
    for key, value in result.items():
        # One line per field.
        print(f"{key}: {value}")
