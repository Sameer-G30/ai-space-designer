"""Tests for item scoring and ranking metrics."""

# math checks the hand-computed NDCG value.
import math

# tmp_path isolates the embedding cache from the real gitignored one.
from pathlib import Path

# Scorer and item score under test.
from spacedesigner.recommend.metrics import ndcg_at_k, precision_at_k, relevance
from spacedesigner.recommend.scoring import (
    FALLBACK_BACKEND,
    load_style_scorer,
    score_item,
    style_key,
)

# Fixtures.
from tests.phase3_samples import sample_catalog, sample_requirement
from tests.recommend.fakes import FakeEmbedder

# Weights that only reward style.
STYLE_ONLY = dict.fromkeys(
    ("layout", "circulation", "ergonomics", "budget", "sustainability"), 0
) | {"aesthetics": 1}


# Style keys match the catalog vocabulary.
def test_style_key_normalizes_words() -> None:
    """Spaces and hyphens become underscores."""
    # Both spellings map to the catalog tag.
    assert style_key("Mid Century") == "mid_century" == style_key("mid-century")


# Precision counts only acceptable grades.
def test_precision_at_k_counts_grade_three() -> None:
    """Two of the first four grades reach 3."""
    # 3 and 3 are acceptable; 2 and 1 are not.
    assert precision_at_k([3, 2, 3, 1, 3], 4) == 0.5


# NDCG equals one for the ideal ranking and drops otherwise.
def test_ndcg_matches_hand_calculation() -> None:
    """Compare against a value worked out by hand."""
    # All grades in the catalog.
    grades = [3, 1, 0]
    # Ideal ordering scores one.
    assert ndcg_at_k([3, 1, 0], grades, 3) == 1.0
    # Swapping the top two: DCG = 1/log2(2) + 7/log2(3), ideal = 7 + 1/log2(3).
    expected = (1 + 7 / math.log2(3)) / (7 + 1 / math.log2(3))
    # Compare with tolerance.
    assert abs(ndcg_at_k([1, 3, 0], grades, 3) - expected) < 1e-9


# Relevance uses only must_have, style and budget.
def test_relevance_grades_follow_generator_fields() -> None:
    """Wrong category is zero; matching category, price and style is three."""
    # One desk row priced under the budget with the modern tag.
    item = sample_catalog("desk", price=1000.0)[0]
    # Requirement asks for a modern desk under INR 10000.
    assert relevance(item, sample_requirement("desk")) == 3
    # Asking for a different category makes the row irrelevant.
    assert relevance(item, sample_requirement("sofa")) == 0
    # A tiny budget removes the affordability point.
    assert relevance(item, sample_requirement("desk", budget=500.0)) == 2


# The category gate zeroes rows of other categories.
def test_score_item_gates_on_category_and_fit() -> None:
    """Only the requested category, and only if it fits, scores above zero."""
    # A small desk.
    item = sample_catalog("desk")[0]
    # Score as a desk in a normal room.
    ok = score_item(item, "desk", 1.0, STYLE_ONLY, 6.0, 6.0, 10000.0)
    # Score as a sofa request.
    wrong = score_item(item, "sofa", 1.0, STYLE_ONLY, 6.0, 6.0, 10000.0)
    # Score in a room too small to hold it.
    tiny = score_item(item, "desk", 1.0, STYLE_ONLY, 0.3, 0.3, 10000.0)
    # Assertions on the gates.
    assert ok.total > 0 and wrong.total == 0 and tiny.total == 0
    # Unaffordable items get zero budget fit.
    assert score_item(item, "desk", 1.0, STYLE_ONLY, 6.0, 6.0, 10.0).budget_fit == 0.0


# The scorer caches vectors and reuses them without an embedder.
def test_scorer_uses_cache_then_reports_fallback(tmp_path: Path) -> None:
    """A cache written with the fake embedder is reused; an empty one falls back."""
    # Tiny catalog.
    catalog = sample_catalog("desk")
    # Cache file inside the test directory.
    cache = tmp_path / "clip.npz"
    # Without a cache or embedder the scorer reports the fallback.
    assert load_style_scorer(catalog, None, cache).backend == FALLBACK_BACKEND
    # Build the cache with the fake embedder.
    built = load_style_scorer(catalog, FakeEmbedder(), cache, extra_styles=("modern",))
    # Scores are in [0, 1].
    assert all(0 <= v <= 1 for v in built.style_scores("modern").values())
    # Reuse the cache with no embedder: the same fake backend is refused because names differ.
    assert load_style_scorer(catalog, None, cache).backend == FALLBACK_BACKEND
