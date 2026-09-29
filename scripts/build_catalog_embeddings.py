"""Embed catalog rows and styles with CLIP; cache locally, optionally write to Postgres."""

# argparse exposes the optional database write flag.
import argparse

# Catalog rows come from the tracked JSONL, not from Postgres.
from spacedesigner.optimizer.catalog import load_catalog

# The real CLIP text tower is created here, in a script, never in a request handler.
from spacedesigner.recommend.embedder import ClipTextEmbedder

# Scorer builder writes the gitignored cache and returns item vectors.
from spacedesigner.recommend.scoring import DEFAULT_CACHE_PATH, item_text, load_style_scorer


# Build the cache and optionally write furniture_catalog.embedding.
def main() -> int:
    """Run the embedding build and return a process exit code."""
    # Parse the command line.
    parser = argparse.ArgumentParser(description=__doc__)
    # Postgres write is opt-in because the database may be down.
    parser.add_argument("--write-db", action="store_true", help="write furniture_catalog.embedding")
    # Read the flags.
    args = parser.parse_args()
    # Validated catalog rows.
    catalog = load_catalog()
    # Compute (or reuse) vectors and save the local cache.
    scorer = load_style_scorer(catalog, embedder=ClipTextEmbedder())
    # Report the cache location and size.
    print(f"cache: {DEFAULT_CACHE_PATH} backend={scorer.backend} items={len(catalog)}")
    # Stop here unless the database write was requested.
    if not args.write_db:
        # Local cache is enough for the metric script.
        return 0
    # Import database pieces only when needed.
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from spacedesigner.db.models import CatalogItemRow
    from spacedesigner.db.session import get_engine

    # One short transaction updates every row's vector; rag_chunks.embedding is never touched.
    with Session(get_engine()) as session, session.begin():
        # Update rows one at a time by primary key.
        for item in catalog:
            # Cached unit vector as plain floats for the unbounded pgvector column.
            vector = [float(x) for x in scorer._item_vectors[item.item_id]]
            # Write only the embedding column.
            session.execute(
                update(CatalogItemRow)
                .where(CatalogItemRow.item_id == item.item_id)
                .values(embedding=vector)
            )
    # Confirm the write.
    print(f"wrote {len(catalog)} catalog embeddings; text example: {item_text(catalog[0])!r}")
    # Success.
    return 0


# Run only when invoked as a script.
if __name__ == "__main__":
    # Exit with the build result.
    raise SystemExit(main())
