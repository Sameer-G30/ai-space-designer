"""Load furniture_catalog and rag_chunks into Postgres, or just print the current counts."""

# Command-line flags.
import sys

# Loader functions.
from spacedesigner.data.db_load import db_counts, load

# Run only when executed as a script.
if __name__ == "__main__":
    # "--counts" only reads; anything else reloads both tables.
    counts = db_counts() if "--counts" in sys.argv else load()
    # One line per count.
    for key, value in counts.items():
        # Print it.
        print(f"{key}: {value}")
