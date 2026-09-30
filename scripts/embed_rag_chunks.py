"""Write bge vectors into rag_chunks.embedding. Catalog CLIP vectors are not touched."""

# Annotations on Python 3.11.
from __future__ import annotations

# Arrays for the gitignored cache.
import numpy as np

# DATABASE_URL from .env when it is not already exported.
from dotenv import load_dotenv

# SQL reads and updates.
from sqlalchemy import text

# Sessions.
from sqlalchemy.orm import Session

# Paths.
from spacedesigner.data.common import processed_dir

# Engine. Nothing connects at import time.
from spacedesigner.db.session import get_engine

# CPU embedder. Weights load inside embed(), not at import.
from spacedesigner.rag.embed import BGE_DIM, BgeEmbedder

# How many chunk texts to encode at once on CPU.
BATCH = 16

# Gitignored cache so a rerun does not re-encode.
CACHE_NAME = "bge_chunks.npz"


# Load DATABASE_URL, embed the existing chunks, and update only rag_chunks.embedding.
def main() -> int:
    """Return 0 when 876 chunk vectors of 384 dims are stored and the catalog is unchanged."""
    # Pick up .env without printing it.
    load_dotenv()
    # Encoder. The first embed call may download the approved checkpoint.
    embedder = BgeEmbedder()
    # Read ids and text. Do not print the text.
    with Session(get_engine()) as session:
        # Catalog snapshot before any write.
        catalog_before = _catalog_snapshot(session)
        # Existing chunk rows, ordered so the cache is stable.
        rows = session.execute(
            text("SELECT chunk_id, text FROM rag_chunks ORDER BY chunk_id")
        ).all()
    # This phase embeds the loaded corpus. It does not re-chunk the PDFs.
    if len(rows) != 876:
        # Stop rather than rebuild.
        print(f"expected 876 rag_chunks rows, found {len(rows)}")
        # Failure.
        return 1
    # Ids in order.
    chunk_ids = [str(row[0]) for row in rows]
    # Texts in the same order. They stay in memory for encoding only.
    texts = [str(row[1]) for row in rows]
    # Cache path under the gitignored processed tree.
    cache_path = processed_dir("phase6") / CACHE_NAME
    # Reuse vectors when the ids match.
    vectors = _load_cache(cache_path, chunk_ids)
    # Encode whatever the cache did not cover.
    if vectors is None:
        # Fresh matrix.
        encoded: list[list[float]] = []
        # Batches of 16.
        for start in range(0, len(texts), BATCH):
            # This batch. Documents do not get the query prefix.
            encoded.extend(embedder.embed(texts[start : start + BATCH], query=False))
            # Progress without the text.
            print(f"embedded {min(start + BATCH, len(texts))}/{len(texts)}")
        # Store as a float32 matrix.
        vectors = np.asarray(encoded, dtype=np.float32)
        # Write the cache for the next run.
        np.savez(cache_path, chunk_ids=np.array(chunk_ids), vectors=vectors)
        # Say where it went.
        print(f"cache: {cache_path}")
    # Shape check before the database write.
    if vectors.shape != (876, BGE_DIM):
        # Stop before writing a bad width.
        print(f"expected vectors (876, {BGE_DIM}), got {vectors.shape}")
        # Failure.
        return 1
    # Update embeddings only.
    with Session(get_engine()) as session, session.begin():
        # One row at a time, by primary key.
        for chunk_id, vector in zip(chunk_ids, vectors, strict=True):
            # pgvector literal of our own floats.
            literal = "[" + ",".join(format(float(value), ".8g") for value in vector) + "]"
            # This statement names rag_chunks and no other table.
            session.execute(
                text(
                    "UPDATE rag_chunks SET embedding = CAST(:embedding AS vector) "
                    "WHERE chunk_id = :chunk_id"
                ),
                {"embedding": literal, "chunk_id": chunk_id},
            )
        # Catalog snapshot after the writes.
        catalog_after = _catalog_snapshot(session)
        # Chunk snapshot.
        chunk_dims = session.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE embedding IS NULL), "
                "min(vector_dims(embedding)) FROM rag_chunks"
            )
        ).one()
    # The catalog row count and width must be unchanged.
    if catalog_before != catalog_after:
        # This would mean a CLIP vector was overwritten.
        print("furniture_catalog.embedding changed; that is not allowed")
        # Failure.
        return 1
    # All 876 chunks must now have a 384-dim vector.
    if tuple(chunk_dims) != (876, 0, BGE_DIM):
        # Report the counts only.
        print(
            f"rag_chunks after write: rows={chunk_dims[0]} "
            f"nulls={chunk_dims[1]} dims={chunk_dims[2]}"
        )
        # Failure.
        return 1
    # Success line. No URL and no chunk text.
    print(
        f"wrote 876 rag_chunks embeddings dim={BGE_DIM}; "
        f"furniture_catalog non_null={catalog_after[0]} dims={catalog_after[1]}"
    )
    # Done.
    return 0


# Non-null catalog count and one vector width, or None when every catalog embedding is null.
def _catalog_snapshot(session: Session) -> tuple[int, int | None]:
    """Return (non-null count, dims) for furniture_catalog.embedding."""
    # Count and width. Width is null when the filtered set is empty.
    row = session.execute(
        text(
            "SELECT count(*) FILTER (WHERE embedding IS NOT NULL), "
            "min(vector_dims(embedding)) FROM furniture_catalog"
        )
    ).one()
    # Count.
    count = int(row[0] or 0)
    # Width, if any vector exists.
    dims = None if row[1] is None else int(row[1])
    # Pair.
    return count, dims


# Load the npz cache when its ids match this database order.
def _load_cache(path, chunk_ids: list[str]) -> np.ndarray | None:
    """Return the cached matrix, or None when the cache is missing or stale."""
    # First run.
    if not path.exists():
        # Encode.
        return None
    # Load ids and vectors.
    cached = np.load(path, allow_pickle=False)
    # Stored ids.
    cached_ids = [str(value) for value in cached["chunk_ids"].tolist()]
    # A different row set is not reused.
    if cached_ids != chunk_ids:
        # Encode again.
        return None
    # Matrix.
    vectors = np.asarray(cached["vectors"], dtype=np.float32)
    # Wrong width.
    if vectors.shape != (len(chunk_ids), BGE_DIM):
        # Encode again.
        return None
    # Reuse.
    print(f"cache hit: {path}")
    # Matrix.
    return vectors


# Run only as a script.
if __name__ == "__main__":
    # Exit with the write result.
    raise SystemExit(main())
