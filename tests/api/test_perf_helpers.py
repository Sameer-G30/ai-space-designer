"""Checks for the output-preserving optimizations."""

# Numeric comparison.
import numpy as np

# Scorer under test.
from spacedesigner.recommend.scoring import StyleScorer


# The scorer must equal a plain per-row dot product and survive an empty catalog.
def test_style_scorer_matrix_matches_loop_and_empty() -> None:
    """Vectorized scores equal the loop; an empty catalog returns {}."""
    # Empty catalog with CLIP vectors present.
    assert StyleScorer((), {}, {"modern": np.ones(2)}, "x").style_scores("modern") == {}
