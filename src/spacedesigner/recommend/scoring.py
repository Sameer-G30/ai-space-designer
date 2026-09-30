"""Deterministic recommendation score for catalog rows (blueprint section 20, no rating term)."""

# hashlib fingerprints item texts so stale cached vectors are detected.
import hashlib

# dataclass keeps score components explicit and immutable.
from dataclasses import dataclass

# Path locates the gitignored local embedding cache.
from pathlib import Path

# numpy holds the cached embedding matrices.
import numpy as np

# The existing fixed material lookup is reused rather than duplicated.
from spacedesigner.optimizer.stage1_cpsat import MATERIAL_SCORES

# Embedder contract; the real CLIP model is only touched when vectors are missing.
from spacedesigner.recommend.embedder import CLIP_CHECKPOINT, TextEmbedder

# Locked catalog row type.
from spacedesigner.schemas import CatalogItem

# Repository root is four parents above this module.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

# Gitignored local cache (datasets/* is ignored) so metrics run without Postgres.
DEFAULT_CACHE_PATH = REPOSITORY_ROOT / "datasets" / "processed" / "phase4" / "clip_text.npz"

# A single item should not take more than this share of the floor to score well on space fit.
SPACE_SHARE_CAP = 0.30

# Backend label used when no cached CLIP vectors cover the request.
FALLBACK_BACKEND = "tag_overlap_fallback"


# Canonical key for a requested style ("Mid Century" -> "mid_century").
def style_key(style: str) -> str:
    """Normalize a style string to the catalog tag vocabulary."""
    # Lowercase, trim, and join words with underscores like the catalog tags.
    return "_".join(style.strip().lower().replace("-", " ").replace("_", " ").split())


# Text that CLIP embeds for one catalog row (there are no product photos).
def item_text(item: CatalogItem) -> str:
    """Build the category, style tag, and material sentence for a row."""
    # Category words without underscores.
    category = item.category.replace("_", " ")
    # Style tags as plain words.
    tags = " and ".join(tag.replace("_", " ") for tag in item.style_tags)
    # Material as plain words.
    material = item.material.replace("_", " ")
    # One short descriptive sentence.
    return f"a {tags} style {category} made of {material}"


# Text that CLIP embeds for a requested style.
def style_text(style: str) -> str:
    """Build the query sentence for a requested style."""
    # Use the same phrasing shape as the item sentences.
    return f"a {style_key(style).replace('_', ' ')} style furniture piece"


# Short hash of an item's text, stored beside its vector.
def _digest(text: str) -> str:
    """Return a stable fingerprint of one text."""
    # Sixteen hex characters are plenty to detect stale rows.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# Per-item components, each in [0, 1], kept for transparency and tests.
@dataclass(frozen=True)
class ItemScore:
    """Score components for one catalog row against one requirement."""

    # Catalog identifier that was scored.
    item_id: str
    # Min-max normalized style similarity.
    style: float
    # One minus the price share of the per-category budget, zero when unaffordable.
    budget_fit: float
    # Zero when the item cannot fit the room, else shrinks with footprint share.
    space_fit: float
    # One for the requested category, else zero (a gate, not a weight).
    function_match: float
    # Fixed material lookup value.
    sustainability: float
    # Final weighted score in [0, 1].
    total: float


# Holds style similarities for a catalog and answers per-style queries.
class StyleScorer:
    """Score how well each catalog row matches a requested style."""

    # Store vectors, style vectors, and the backend name.
    def __init__(
        self,
        catalog: tuple[CatalogItem, ...],
        item_vectors: dict[str, np.ndarray] | None,
        style_vectors: dict[str, np.ndarray] | None,
        backend: str,
    ) -> None:
        """Create a scorer from cached vectors or a tag-overlap fallback."""
        # Catalog rows in source order.
        self._catalog = catalog
        # Item id to unit vector, or None for the fallback.
        self._item_vectors = item_vectors
        # Normalized style key to unit vector, or None for the fallback.
        self._style_vectors = style_vectors
        # Stacked item vectors, built lazily on the first CLIP query.
        self._matrix: np.ndarray | None = None
        # Human-readable backend recorded in API responses and reports.
        self.backend = backend

    # Backend that will actually score this style (CLIP only if its query vector is cached).
    def backend_for(self, style: str) -> str:
        """Return the CLIP checkpoint name or the fallback label for this style."""
        # CLIP applies only when both row vectors and this style's vector exist.
        has_vector = self._item_vectors is not None and style_key(style) in (
            self._style_vectors or {}
        )
        # Report honestly which path scored the request.
        return self.backend if has_vector else FALLBACK_BACKEND

    # Style similarity in [0, 1] for every catalog row.
    def style_scores(self, style: str) -> dict[str, float]:
        """Return an id-to-score mapping for the requested style."""
        # Canonical vocabulary key.
        key = style_key(style)
        # CLIP path: needs both cached vectors and a cached query vector.
        if self._item_vectors is not None and self._style_vectors and key in self._style_vectors:
            # Query vector for the requested style.
            query = self._style_vectors[key]
            # Raw cosine per row (vectors are unit length).
            if not self._catalog:
                # Nothing to score; avoids min() on an empty sequence.
                return {}
            # Stack the vectors once, then score every row with one matrix product.
            if self._matrix is None:
                self._matrix = np.stack([self._item_vectors[i.item_id] for i in self._catalog])
            # Cosine for every row at once.
            sims = self._matrix @ query
            # Same mapping as before, in catalog order.
            raw = {item.item_id: float(v) for item, v in zip(self._catalog, sims, strict=True)}
            # Range over the whole catalog so scores are comparable across categories.
            low, high = min(raw.values()), max(raw.values())
            # Guard against a degenerate constant range.
            span = high - low if high > low else 1.0
            # Min-max normalize into [0, 1].
            return {item_id: (value - low) / span for item_id, value in raw.items()}
        # Fallback: one when the requested style is one of the row's tags.
        return {
            item.item_id: 1.0 if key in {style_key(tag) for tag in item.style_tags} else 0.0
            for item in self._catalog
        }


# Build a scorer from the local cache, embedding only what is missing when an embedder is given.
def load_style_scorer(
    catalog: tuple[CatalogItem, ...],
    embedder: TextEmbedder | None = None,
    cache_path: Path = DEFAULT_CACHE_PATH,
    extra_styles: tuple[str, ...] = (),
    save: bool = True,
) -> StyleScorer:
    """Return a CLIP-backed scorer, or the tag-overlap fallback when nothing is cached."""
    # Style vocabulary: every catalog tag plus any caller-supplied style.
    keys = sorted({style_key(tag) for item in catalog for tag in item.style_tags}
                  | {style_key(style) for style in extra_styles})
    # Model name that must match the cache.
    backend = embedder.name if embedder is not None else CLIP_CHECKPOINT
    # Cached vectors keyed by fingerprint of the text that produced them.
    cached: dict[str, np.ndarray] = {}
    # Read the cache when it exists.
    if cache_path.exists():
        # Load the npz archive (no pickle needed).
        with np.load(cache_path, allow_pickle=False) as archive:
            # Only reuse vectors made by the same checkpoint.
            if str(archive["checkpoint"]) == backend:
                # Map each stored fingerprint to its vector.
                for digest, vector in zip(archive["digests"], archive["vectors"], strict=True):
                    # Keep a copy of the row.
                    cached[str(digest)] = vector
    # Texts we need vectors for: items first, then styles.
    item_texts = {item.item_id: item_text(item) for item in catalog}
    # Style query texts by key.
    style_texts = {key: style_text(key) for key in keys}
    # Fingerprints that are not cached yet.
    missing = sorted(
        {_digest(t) for t in [*item_texts.values(), *style_texts.values()]} - cached.keys()
    )
    # Embed the gaps only when a model was supplied.
    if missing and embedder is not None:
        # Map each missing fingerprint back to one text.
        by_digest = {_digest(t): t for t in [*item_texts.values(), *style_texts.values()]}
        # Embed in one batch (the catalog is small).
        vectors = embedder.embed_texts([by_digest[d] for d in missing])
        # Store the new vectors.
        for digest, vector in zip(missing, vectors, strict=True):
            # Keep the row for scoring and saving.
            cached[digest] = vector
        # Persist the cache so later runs never reload the model.
        if save:
            # Create the gitignored directory on demand.
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Save fingerprints, vectors, and the checkpoint name.
            np.savez(
                cache_path,
                checkpoint=np.array(backend),
                digests=np.array(sorted(cached)),
                vectors=np.stack([cached[d] for d in sorted(cached)]),
            )
        # Nothing is missing any more.
        missing = []
    # Without full coverage, fall back to deterministic tag overlap and say so.
    if missing:
        # Fallback scorer has no vectors.
        return StyleScorer(catalog, None, None, FALLBACK_BACKEND)
    # Vectors per item id.
    item_vectors = {item_id: cached[_digest(text)] for item_id, text in item_texts.items()}
    # Vectors per style key.
    style_vectors = {key: cached[_digest(text)] for key, text in style_texts.items()}
    # Full CLIP-backed scorer.
    return StyleScorer(catalog, item_vectors, style_vectors, backend)


# Turn user weights into item-level weights over the four scored axes.
def item_weights(weights: dict[str, float]) -> dict[str, float]:
    """Map the six objective weights onto style, budget, space, and sustainability."""
    # Aesthetics drives style similarity.
    style = weights["aesthetics"]
    # Budget drives budget fit.
    budget = weights["budget"]
    # Layout and circulation together drive space fit.
    space = (weights["layout"] + weights["circulation"]) / 2
    # Sustainability drives the material lookup.
    sustainability = weights["sustainability"]
    # Ergonomics is constant per catalog row here, so it does not change the item ranking.
    return {"style": style, "budget": budget, "space": space, "sustainability": sustainability}


# Score one catalog row against a requirement.
def score_item(
    item: CatalogItem,
    category: str,
    style: float,
    weights: dict[str, float],
    room_length: float,
    room_width: float,
    budget_share: float,
) -> ItemScore:
    """Return the deterministic item score and its components."""
    # Category gate: only the requested function scores above zero.
    function_match = 1.0 if item.category == category else 0.0
    # Budget fit is zero above the per-category share and grows as the item gets cheaper.
    unaffordable = budget_share <= 0 or item.price > budget_share
    # Zero when unaffordable, else the unspent fraction of the share.
    budget_fit = 0.0 if unaffordable else 1.0 - item.price / budget_share
    # Footprint area of the item.
    area = item.dims.length * item.dims.width
    # The item fits if both edges fit in either orientation.
    fits = (item.dims.length <= room_length and item.dims.width <= room_width) or (
        item.dims.width <= room_length and item.dims.length <= room_width
    )
    # Space fit is zero when it cannot fit, else falls as the item takes more of the floor.
    space_fit = (
        max(0.0, 1.0 - area / (SPACE_SHARE_CAP * room_length * room_width)) if fits else 0.0
    )
    # Fixed material lookup; unknown materials get the neutral 0.5 used by Stage 1.
    sustainability = MATERIAL_SCORES.get(item.material, 0.5)
    # Item-level weights.
    w = item_weights(weights)
    # Total weight for the weighted mean.
    denominator = sum(w.values())
    # A zero vector falls back to equal weights so ranking stays deterministic.
    if denominator == 0:
        # Equal weights over the four axes.
        w, denominator = {name: 1.0 for name in w}, 4.0
    # Weighted mean of the four axes.
    mean = (
        w["style"] * style
        + w["budget"] * budget_fit
        + w["space"] * space_fit
        + w["sustainability"] * sustainability
    ) / denominator
    # Multiply by the category gate and by fit (an item that cannot fit is unusable).
    total = function_match * mean * (1.0 if fits else 0.0)
    # Return all components.
    return ItemScore(
        item.item_id, style, budget_fit, space_fit, function_match, sustainability, total
    )
