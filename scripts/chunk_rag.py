"""Chunk the ADA PDF, the MoHUA PDF, and the cited summaries into datasets/processed/rag/."""

# Entry point for the chunker.
from spacedesigner.data.rag_chunks import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Chunk and print the counts.
    for key, value in run().items():
        # One line per field.
        print(f"{key}: {value}")
