"""Hybrid retrieval: pgvector cosine distance, Postgres full-text search, then a rerank."""

# Annotations on Python 3.11.
from __future__ import annotations

# SQL text for the two rankings. Bind parameters carry the vector and the query.
from dataclasses import dataclass

# SQL strings.
from sqlalchemy import text

# Session type.
from sqlalchemy.orm import Session

# Engine factory. Nothing connects at import time.
from spacedesigner.db.session import get_engine

# CPU embedder, constructed by the caller or the script.
from spacedesigner.rag.embed import BgeEmbedder

# CPU reranker.
from spacedesigner.rag.rerank import BgeReranker

# Dense list size before fusion.
DENSE_K = 20

# Sparse list size before fusion.
SPARSE_K = 20

# How many fused candidates the reranker sees.
RERANK_K = 20

# Reciprocal-rank constant. 60 is the usual fusion setting.
RRF_K = 60


# Raised when the chunk table cannot be searched. The message has no database URL.
class RetrievalUnavailable(Exception):
    """Retrieval could not run. The parser may still return a requirement."""


# One retrieved chunk. text is internal and is not copied into the HTTP body.
@dataclass(frozen=True)
class ChunkHit:
    """A ranked chunk. Callers that answer HTTP drop the text after number extraction."""

    # Primary key.
    chunk_id: str
    # ada_2010, mohua_2021, or a summary source.
    source: str
    # PDF page, or None for a summary.
    page: int | None
    # Topic stored in metadata.
    topic: str
    # Chunk text, used only to extract numbers and to rerank.
    text: str
    # Reranker score, higher is better.
    score: float


# Fuse ranked id lists. A document in both lists ranks above a document in one.
def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Return ids sorted by reciprocal rank. Ties break by id."""
    # Score per id.
    scores: dict[str, float] = {}
    # Each ranking contributes 1/(k+rank).
    for ranking in rankings:
        # Rank is 1-based.
        for index, chunk_id in enumerate(ranking, start=1):
            # Add this list's contribution.
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + index)
    # Higher score first. Equal scores use the id so the order is stable.
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


# pgvector literal. Values are floats we produced, not user text.
def _vector_literal(values: list[float]) -> str:
    """Format a unit vector as a pgvector text literal."""
    # Compact decimal form.
    body = ",".join(format(float(value), ".8g") for value in values)
    # Brackets are the pgvector input syntax.
    return f"[{body}]"


# Read a page int out of JSON metadata. Summaries store null.
def _page(metadata: object) -> int | None:
    """Return the page integer, or None."""
    # Metadata must be an object.
    if not isinstance(metadata, dict):
        # No page.
        return None
    # Stored page.
    page = metadata.get("page")
    # Null or missing.
    if page is None:
        # Summary chunk.
        return None
    # JSON numbers may be int or float.
    if isinstance(page, int):
        # Already an int.
        return page
    # A whole float from JSON.
    if isinstance(page, float) and page.is_integer():
        # Convert.
        return int(page)
    # Unexpected shape.
    return None


# Topic string, defaulting to general.
def _topic(metadata: object) -> str:
    """Return the topic, or general when it is missing."""
    # Metadata must be an object.
    if not isinstance(metadata, dict):
        # Fallback topic.
        return "general"
    # Stored topic.
    topic = metadata.get("topic")
    # Use it when it is a non-empty string.
    if isinstance(topic, str) and topic.strip() != "":
        # Done.
        return topic
    # Fallback.
    return "general"


# Turn a SQL row into a hit. The score is filled in later.
def _hit(row: dict, score: float) -> ChunkHit:
    """Build a ChunkHit from a mapping row."""
    # Metadata JSON.
    metadata = row.get("metadata")
    # Assemble the hit.
    return ChunkHit(
        chunk_id=str(row["chunk_id"]),
        source=str(row["source"]),
        page=_page(metadata),
        topic=_topic(metadata),
        text=str(row["text"]),
        score=score,
    )


# Dense top-k. Reads rag_chunks.embedding only.
def _dense_ids(session: Session, vector: list[float], limit: int) -> list[str]:
    """Return chunk ids nearest to the query vector."""
    # Cosine distance on the unbounded vector column.
    statement = text(
        """
        SELECT chunk_id
        FROM rag_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )
    # Bound parameters. The vector is our own floats.
    rows = session.execute(
        statement,
        {"embedding": _vector_literal(vector), "limit": limit},
    ).all()
    # Ids in rank order.
    return [str(row[0]) for row in rows]


# Sparse top-k using the text column. No extra tsvector column, so no migration.
def _sparse_ids(session: Session, query: str, limit: int) -> list[str]:
    """Return chunk ids by Postgres full-text rank."""
    # A blank query cannot build a tsquery.
    if query.strip() == "":
        # No sparse hits.
        return []
    # plainto_tsquery ignores punctuation in a user sentence.
    statement = text(
        """
        SELECT chunk_id
        FROM rag_chunks
        WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank_cd(to_tsvector('english', text), plainto_tsquery('english', :query)) DESC,
                 chunk_id
        LIMIT :limit
        """
    )
    # Bound query text.
    rows = session.execute(statement, {"query": query, "limit": limit}).all()
    # Ids in rank order.
    return [str(row[0]) for row in rows]


# Load the fused candidates with their text and metadata.
def _load_chunks(session: Session, chunk_ids: list[str]) -> dict[str, dict]:
    """Return rows keyed by chunk id. The text stays inside this process."""
    # Nothing to load.
    if not chunk_ids:
        # Empty map.
        return {}
    # One query for the candidate set.
    statement = text(
        """
        SELECT chunk_id, source, text, metadata
        FROM rag_chunks
        WHERE chunk_id = ANY(:chunk_ids)
        """
    )
    # Execute.
    rows = session.execute(statement, {"chunk_ids": chunk_ids}).mappings().all()
    # Key by id.
    return {str(row["chunk_id"]): dict(row) for row in rows}


# Count embedded chunks. Zero means the embed script has not been run.
def _embedded_count(session: Session) -> int:
    """Return how many rag_chunks rows have a vector."""
    # Count only this table.
    statement = text("SELECT count(*) FROM rag_chunks WHERE embedding IS NOT NULL")
    # Scalar count.
    count = session.execute(statement).scalar()
    # Null becomes zero.
    return int(count or 0)


# The search object the route and the recall script share.
class HybridRetriever:
    """Embed a query, fuse dense and sparse ranks, rerank the top 20, return the top n."""

    # Store collaborators. Models load on the first search, not at construction.
    def __init__(
        self,
        embedder: BgeEmbedder | None = None,
        reranker: BgeReranker | None = None,
    ) -> None:
        """Keep the embedder and reranker. Both default to the approved CPU checkpoints."""
        # Query vectors.
        self.embedder = embedder if embedder is not None else BgeEmbedder()
        # Cross-encoder.
        self.reranker = reranker if reranker is not None else BgeReranker()

    # One search.
    def search(self, query: str, limit: int = 5) -> list[ChunkHit]:
        """Return up to limit chunks, best reranker score first."""
        # A blank query has nothing to retrieve.
        if query.strip() == "":
            # No hits.
            return []
        # Embed before opening a session so the first model load does not hold a connection.
        vector = self.embedder.embed([query], query=True)[0]
        # Database errors become a stable message with no URL.
        try:
            # One session for the three reads.
            with Session(get_engine()) as session:
                # Refuse to pretend an empty index is a search.
                if _embedded_count(session) == 0:
                    # The caller records this beside the parse.
                    raise RetrievalUnavailable(
                        "rag_chunks.embedding is empty. Run scripts/embed_rag_chunks.py."
                    )
                # Dense ranking.
                dense = _dense_ids(session, vector, DENSE_K)
                # Sparse ranking.
                sparse = _sparse_ids(session, query, SPARSE_K)
                # Fused ids, then the top 20 for the reranker.
                fused = reciprocal_rank_fusion([dense, sparse])[:RERANK_K]
                # Row map.
                rows = _load_chunks(session, fused)
        # Our own empty-index signal.
        except RetrievalUnavailable:
            # Let the service record it.
            raise
        # Any driver or SQL error. Do not pass the message through; it can contain the URL.
        except Exception as exc:
            # A missing setting is already a safe sentence.
            if isinstance(exc, RuntimeError) and "DATABASE_URL" in str(exc):
                # Repeat that sentence.
                raise RetrievalUnavailable(str(exc)) from None
            # Hide connection strings.
            raise RetrievalUnavailable("The standards index could not be read.") from None
        # Passages in fused order, skipping an id that disappeared.
        passages = [rows[chunk_id]["text"] for chunk_id in fused if chunk_id in rows]
        # Matching ids.
        present = [chunk_id for chunk_id in fused if chunk_id in rows]
        # Rerank on CPU.
        scores = self.reranker.score(query, passages)
        # Pair id and score.
        ranked = sorted(zip(present, scores, strict=True), key=lambda item: (-item[1], item[0]))
        # Top n hits.
        hits: list[ChunkHit] = []
        # Keep the requested count.
        for chunk_id, score in ranked[:limit]:
            # Build the hit.
            hits.append(_hit(rows[chunk_id], score))
        # Best first.
        return hits


# Process-wide retriever. The models load on the first search.
_retriever: HybridRetriever | None = None


# FastAPI dependency.
def get_hybrid_retriever() -> HybridRetriever:
    """Return the shared retriever. Tests override this dependency."""
    # Module singleton.
    global _retriever
    # Build once.
    if _retriever is None:
        # Defaults are the CPU checkpoints.
        _retriever = HybridRetriever()
    # Reuse it.
    return _retriever
