"""Load furniture_catalog and rag_chunks rows into Postgres. Embeddings stay null until Phase 6."""

# Annotations on Python 3.11.
from __future__ import annotations

# Reads DATABASE_URL from .env like Alembic does.
from dotenv import load_dotenv

# SQL helpers.
from sqlalchemy import delete, func, select

# Session factory from SQLAlchemy.
from sqlalchemy.orm import Session

# Paths and helpers.
from spacedesigner.data.common import cleaning_dir, processed_dir, read_jsonl
from spacedesigner.db.models import CatalogItemRow, RagChunkRow
from spacedesigner.db.session import get_engine

# Locked catalog contract validates each row before insert.
from spacedesigner.schemas.catalog import CatalogItem


def load() -> dict:
    """Replace the catalog and RAG rows with the files on disk. Return the counts."""
    # Pick up DATABASE_URL from .env when it is not exported.
    load_dotenv()
    # Catalog rows from the tracked JSONL.
    catalog = read_jsonl(cleaning_dir() / "furniture_catalog.jsonl")
    # RAG rows from the ignored processed folder.
    chunks = read_jsonl(processed_dir("rag") / "chunks.jsonl")
    # One transaction for both tables.
    with Session(get_engine()) as session, session.begin():
        # Reloading is idempotent: clear only these two tables.
        session.execute(delete(CatalogItemRow))
        # Clear the chunk table.
        session.execute(delete(RagChunkRow))
        # Insert validated catalog rows.
        for row in catalog:
            # Contract check; embedding must be null in this phase.
            item = CatalogItem.model_validate(row)
            # Embedding is never stored in Phase 2b.
            assert item.embedding is None
            # Add the row.
            session.add(
                CatalogItemRow(
                    item_id=item.item_id,
                    category=item.category,
                    dims=item.dims.model_dump(),
                    price=item.price,
                    style_tags=item.style_tags,
                    material=item.material,
                    embedding=None,
                )
            )
        # Insert chunk rows with the metadata column mapped to chunk_metadata.
        for chunk in chunks:
            # Add the row.
            session.add(
                RagChunkRow(
                    chunk_id=chunk["chunk_id"],
                    source=chunk["source"],
                    text=chunk["text"],
                    embedding=None,
                    chunk_metadata=chunk["metadata"],
                )
            )
    # Read the counts back from the database.
    return db_counts()


def db_counts() -> dict:
    """Return row counts and null-embedding counts for both tables."""
    # Pick up DATABASE_URL from .env when it is not exported.
    load_dotenv()
    # Read-only session.
    with Session(get_engine()) as session:
        # Catalog total.
        catalog_rows = session.scalar(select(func.count()).select_from(CatalogItemRow))
        # Catalog rows with a null embedding.
        catalog_null = session.scalar(
            select(func.count())
            .select_from(CatalogItemRow)
            .where(CatalogItemRow.embedding.is_(None))
        )
        # Chunk total.
        chunk_rows = session.scalar(select(func.count()).select_from(RagChunkRow))
        # Chunk rows with a null embedding.
        chunk_null = session.scalar(
            select(func.count()).select_from(RagChunkRow).where(RagChunkRow.embedding.is_(None))
        )
    # Give the counts back.
    return {
        "furniture_catalog_rows": catalog_rows,
        "furniture_catalog_null_embeddings": catalog_null,
        "rag_chunks_rows": chunk_rows,
        "rag_chunks_null_embeddings": chunk_null,
    }
