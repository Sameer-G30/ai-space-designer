"""Hybrid retrieval over the standards chunks, with a CPU reranker."""

# Query embedder.
from spacedesigner.rag.embed import BgeEmbedder

# Fusion and search.
from spacedesigner.rag.hybrid import (
    ChunkHit,
    HybridRetriever,
    RetrievalUnavailable,
    get_hybrid_retriever,
    reciprocal_rank_fusion,
)

# Number extraction.
from spacedesigner.rag.numbers import extract_clearances

# Passage reranker.
from spacedesigner.rag.rerank import BgeReranker

# Names re-exported from this package.
__all__ = [
    "BgeEmbedder",
    "BgeReranker",
    "ChunkHit",
    "HybridRetriever",
    "RetrievalUnavailable",
    "extract_clearances",
    "get_hybrid_retriever",
    "reciprocal_rank_fusion",
]
