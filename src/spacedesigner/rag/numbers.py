"""Pull clearance and ergonomic numbers out of retrieved chunks. The prose is not returned."""

# Annotations on Python 3.11.
from __future__ import annotations

# Patterns for millimetres, inches, and metres.
import re

# The hit type. Only its source fields and text are read.
from spacedesigner.rag.hybrid import ChunkHit

# Millimetres, as in "915 mm".
_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.IGNORECASE)

# Inches written as a word, so "mm" cannot match.
_INCH = re.compile(r"(\d+(?:\.\d+)?)\s*(?:inches|inch)\b", re.IGNORECASE)

# Metres, as in "1.525 m". The boundary stops this from matching the first m of "mm".
_METRE = re.compile(r"(\d+(?:\.\d+)?)\s*m\b", re.IGNORECASE)

# Room-scale range. A 61 m passing interval is not a furniture clearance.
_MIN_M = 0.05

# Upper bound for a single clearance or ergonomic height.
_MAX_M = 3.0

# How many numbers one chunk may contribute.
_PER_CHUNK = 4

# How many numbers the response may carry.
_MAX_NUMBERS = 12

# Keywords in priority order. The first hit in the preceding window names the number.
_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("turning_space", ("turning",)),
    ("door_clear_width", ("door", "doorway")),
    ("knee_clearance", ("knee",)),
    ("work_surface_height", ("work surface", "counter")),
    ("seat_height", ("seat", "bench")),
    ("bed_height", ("bed",)),
    ("storage_height", ("shelf", "storage")),
    ("clear_width", ("corridor", "passage", "clear width", "walking", "route")),
)


# Name a number from the words just before it.
def _label(window: str) -> str:
    """Return a short name, or measurement when no keyword is in the window."""
    # Lowercase once.
    lowered = window.lower()
    # First matching group wins, so "door" beats a later "clear width".
    for name, words in _LABELS:
        # Any keyword.
        if any(word in lowered for word in words):
            # Use that name.
            return name
    # Unclassified room-scale number.
    return "measurement"


# Convert one regex match to metres, or return None when it is out of range.
def _metres(number: str, unit: str) -> float | None:
    """Convert mm, inches, or m into metres inside the room-scale range."""
    # Parse the digits.
    value = float(number)
    # Unit scale.
    if unit == "mm":
        # Millimetres to metres.
        metres = value / 1000.0
    elif unit == "inch":
        # Inches to metres.
        metres = value * 0.0254
    else:
        # Already metres.
        metres = value
    # Drop values that are not a clearance or an ergonomic height.
    if metres < _MIN_M or metres > _MAX_M:
        # Skip.
        return None
    # Round to millimetres so 915 mm and a float inch stay stable.
    return round(metres, 3)


# One returned number. No chunk text.
class RetrievedClearance:
    """A number plus the chunk it came from."""

    # Store the fields the HTTP model copies.
    def __init__(
        self,
        name: str,
        value_m: float,
        source: str,
        page: int | None,
        topic: str,
        chunk_id: str,
    ) -> None:
        """Keep the source fields and drop the passage."""
        # Short name.
        self.name = name
        # Metres.
        self.value_m = value_m
        # Document id.
        self.source = source
        # Page or None.
        self.page = page
        # Topic.
        self.topic = topic
        # Chunk id.
        self.chunk_id = chunk_id


# Collect numbers from hits that are already in rerank order.
def extract_clearances(hits: list[ChunkHit]) -> list[RetrievedClearance]:
    """Return up to 12 numbers. Each carries source, page, and topic, not the passage."""
    # Output, best chunks first.
    found: list[RetrievedClearance] = []
    # Dedupe key.
    seen: set[tuple[str, str, float]] = set()
    # Walk the reranked hits.
    for hit in hits:
        # Numbers taken from this chunk.
        taken = 0
        # Three patterns.
        matches: list[tuple[int, str, str]] = []
        # Millimetres.
        for match in _MM.finditer(hit.text):
            # Record the start, the digits, and the unit.
            matches.append((match.start(), match.group(1), "mm"))
        # Inches.
        for match in _INCH.finditer(hit.text):
            # Record them.
            matches.append((match.start(), match.group(1), "inch"))
        # Metres.
        for match in _METRE.finditer(hit.text):
            # Record them.
            matches.append((match.start(), match.group(1), "m"))
        # Left-to-right so the preceding window is the local phrase.
        for start, digits, unit in sorted(matches):
            # Stop this chunk at the cap.
            if taken >= _PER_CHUNK or len(found) >= _MAX_NUMBERS:
                # Next chunk, or stop if the response is full.
                break
            # Convert.
            metres = _metres(digits, unit)
            # Out of range.
            if metres is None:
                # Next match.
                continue
            # Words before the number, capped so a long sentence cannot rename it from far away.
            window = hit.text[max(0, start - 80) : start]
            # Name.
            name = _label(window)
            # Dedupe within the chunk.
            key = (hit.chunk_id, name, metres)
            # Already recorded.
            if key in seen:
                # Next match.
                continue
            # Remember it.
            seen.add(key)
            # Append the structured number.
            found.append(
                RetrievedClearance(
                    name=name,
                    value_m=metres,
                    source=hit.source,
                    page=hit.page,
                    topic=hit.topic,
                    chunk_id=hit.chunk_id,
                )
            )
            # Count it against the per-chunk cap.
            taken += 1
        # Stop once the response is full.
        if len(found) >= _MAX_NUMBERS:
            # Done.
            break
    # Give the numbers back.
    return found
