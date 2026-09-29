"""Write docs/reports/data_quality_layout.md."""

# Entry point for the report writer.
from spacedesigner.data.layout_report import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Write and print the path.
    print(run())
