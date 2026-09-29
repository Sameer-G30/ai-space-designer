"""Phase 2a: write docs/reports/data_quality_cv.md from the cleaning summaries."""

# The report builder lives in the package.
from spacedesigner.data import report

# Script entry point.
if __name__ == "__main__":
    # Write the file and print its path.
    print(report.run())
