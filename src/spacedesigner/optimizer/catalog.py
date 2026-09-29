"""Read the tracked furniture JSONL without requiring PostgreSQL."""

# json parses one catalog object per line.
import json

# cache avoids reparsing the source for every synthetic room.
from functools import lru_cache

# Path resolves the repository-relative default source.
from pathlib import Path

# CatalogItem validates every source row against the locked contract.
from spacedesigner.schemas import CatalogItem

# Repository root is four parents above this module.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# The tracked JSONL remains the Phase 3 source of truth.
DEFAULT_CATALOG_PATH = (
    REPOSITORY_ROOT / "datasets" / "metadata" / "cleaning" / "furniture_catalog.jsonl"
)


# Cache the immutable validated catalog by source path.
@lru_cache(maxsize=4)
def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> tuple[CatalogItem, ...]:
    """Load and validate catalog rows in deterministic file order."""
    # Normalize the argument before opening and caching it.
    source = Path(path)
    # Collect validated rows without mutating source data.
    items: list[CatalogItem] = []
    # Open UTF-8 JSONL text for sequential parsing.
    with source.open("r", encoding="utf-8") as handle:
        # Process each physical line in source order.
        for line in handle:
            # Ignore accidental blank lines safely.
            if not line.strip():
                # Continue with the next catalog record.
                continue
            # Validate parsed JSON against CatalogItem.
            items.append(CatalogItem.model_validate(json.loads(line)))
    # Return an immutable collection suitable for reuse.
    return tuple(items)
