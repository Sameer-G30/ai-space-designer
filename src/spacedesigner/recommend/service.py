"""Request-time access to the cached style scorer (never loads CLIP)."""

# lru_cache reads the local embedding cache once per process.
from functools import lru_cache

# Same JSONL catalog the solver uses.
from spacedesigner.optimizer.catalog import load_catalog

# Scorer builder; no embedder is passed, so no model is ever loaded here.
from spacedesigner.recommend.scoring import StyleScorer, load_style_scorer


# FastAPI dependency: cached CLIP vectors if present, otherwise the labelled tag-overlap fallback.
@lru_cache(maxsize=1)
def get_style_scorer() -> StyleScorer:
    """Return the process-wide scorer built from the gitignored cache only."""
    # Passing no embedder guarantees the request path cannot import torch or load weights.
    return load_style_scorer(load_catalog())
