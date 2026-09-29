"""Generate synthetic rooms and gold requirements under datasets/raw/synthetic/."""

# Entry point for the generator.
from spacedesigner.data.synthetic import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Generate and print the manifest counts without the examples.
    manifest = run()
    # Drop the long examples for the console.
    manifest.pop("examples", None)
    # One line per field.
    for key, value in manifest.items():
        # Print it.
        print(f"{key}: {value}")
