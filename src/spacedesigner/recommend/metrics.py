"""Ranking metrics and the synthetic ground-truth relevance definition."""

# math supplies the logarithm for DCG.
import math

# Locked schema types.
from spacedesigner.recommend.scoring import style_key
from spacedesigner.schemas import CatalogItem, Requirement

# An item is "acceptable" (Precision@K) when its graded relevance reaches this level.
ACCEPTABLE_GRADE = 3


# Graded relevance from the generator's own fields: must_have, style, and budget.
def relevance(item: CatalogItem, requirement: Requirement) -> int:
    """Return 0 (wrong category) or 1 to 3 (category, +affordable, +style tag)."""
    # Wrong category is never relevant.
    if item.category not in requirement.must_have:
        # Zero grade.
        return 0
    # Budget is shared across the required categories, so the fair share is budget / n.
    share = requirement.budget_inr / max(1, len(set(requirement.must_have)))
    # Right category earns one point.
    grade = 1
    # Affordable within its share earns a second point.
    grade += int(item.price <= share)
    # A tag equal to the requested style earns a third point.
    grade += int(style_key(requirement.style) in {style_key(tag) for tag in item.style_tags})
    # Final grade in 1..3.
    return grade


# Precision@K over a ranked list of grades.
def precision_at_k(grades: list[int], k: int) -> float:
    """Fraction of the top K whose grade is acceptable."""
    # Count acceptable items in the first K.
    hits = sum(grade >= ACCEPTABLE_GRADE for grade in grades[:k])
    # Divide by K (the list is always at least K long for this catalog).
    return hits / k


# Discounted cumulative gain of the first K grades.
def _dcg(grades: list[int], k: int) -> float:
    """Return DCG@K with the (2^g - 1) gain."""
    # Sum gain over log2 position discounts.
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:k]))


# Normalized DCG against the ideal ordering of the same catalog.
def ndcg_at_k(grades: list[int], all_grades: list[int], k: int) -> float:
    """Return NDCG@K, or 0 when no relevant item exists."""
    # Best possible DCG uses grades sorted in descending order.
    ideal = _dcg(sorted(all_grades, reverse=True), k)
    # No relevant item means the query cannot be scored.
    if ideal == 0:
        # Zero by convention.
        return 0.0
    # Ratio of achieved to ideal gain.
    return _dcg(grades, k) / ideal
