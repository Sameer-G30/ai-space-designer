"""Closed lists the parser may emit. They match the generator and the catalog."""

# Annotations on Python 3.11.
from __future__ import annotations

# Style words already used by the synthetic generator.
from spacedesigner.data.synthetic import STYLES

# The 26 furniture classes. Rug, door, and window are not catalog choices.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES

# Catalog categories with no items. Doors and windows are scene openings.
ABSENT_CATALOG_CLASSES = frozenset({"rug", "door", "window"})

# The 23 classes a must_have list may name.
MUST_HAVE_CLASSES: tuple[str, ...] = tuple(
    name for name in FURNITURE_CLASSES if name not in ABSENT_CATALOG_CLASSES
)

# The nine generator style words, in generator order.
STYLE_WORDS: tuple[str, ...] = STYLES

# The six objective weights. The parser must emit every one.
WEIGHT_NAMES: tuple[str, ...] = (
    "layout",
    "circulation",
    "ergonomics",
    "budget",
    "aesthetics",
    "sustainability",
)

# Fast membership tests.
MUST_HAVE_SET = frozenset(MUST_HAVE_CLASSES)

# Fast membership tests for style words.
STYLE_SET = frozenset(STYLE_WORDS)

# How many model calls one parse may make, including the first.
MAX_PARSE_ATTEMPTS = 2


# Turn "coffee table" and "mid-century" into catalog tokens.
def canonicalize_token(raw: str) -> str:
    """Lowercase a label and join its words with one underscore."""
    # Trim and lowercase before splitting.
    lowered = raw.strip().lower().replace("-", " ").replace("_", " ")
    # Drop empty pieces left by repeated separators.
    parts = [part for part in lowered.split() if part]
    # Join the words the way the taxonomy stores them.
    return "_".join(parts)
