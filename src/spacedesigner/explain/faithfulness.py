"""Check that a sentence's numbers and domain words already appear in the templated facts."""

# re extracts numbers and words. No model is involved.
import re

# TemplatedFact holds the allowed text.
from spacedesigner.explain.models import TemplatedFact

# A number token, including thousands separators.
_NUMBER = re.compile(r"(?<![\w])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(?![\w])")

# Words a design explanation is allowed to use only when the facts already use them.
_DOMAIN_WORDS = (
    "budget",
    "clearance",
    "circulation",
    "ergonomics",
    "accessibility",
    "turning",
    "margin",
    "sustainability",
    "aesthetics",
    "layout",
    "rejected",
    "cost",
    "score",
    "occupant",
    "door",
    "window",
    "catalog",
)


# Pull the numeric tokens out of one string.
def numbers_in(text: str) -> list[float]:
    """Return each number in reading order."""
    # Parsed values. The original spelling is not needed once the float matches.
    found: list[float] = []
    # Walk every token the pattern accepts.
    for match in _NUMBER.finditer(text):
        # Drop grouping commas before parsing.
        found.append(float(match.group(1).replace(",", "")))
    # Order is the sentence order.
    return found


# True when value is one of the allowed numbers, within a small relative tolerance.
def number_allowed(value: float, allowed: list[float]) -> bool:
    """Match a claim number to a fact number."""
    # Compare against every allowed number.
    for other in allowed:
        # Scale the tolerance so 10000 and 0.000001 both match their own spelling.
        scale = max(1.0, abs(other))
        # Accept the same quantity written with fewer decimals.
        if abs(value - other) <= 1e-6 * scale:
            # This number is grounded.
            return True
    # No fact contains this quantity.
    return False


# Pick the fact that shares the most numbers with the claim, then the most domain words.
def supporting_ref(claim: str, facts: list[TemplatedFact]) -> str:
    """Return the best trace pointer for one claim."""
    # Numbers in the claim.
    claim_numbers = numbers_in(claim)
    # Lowercased claim for the word check.
    lowered = claim.lower()
    # Best fact so far.
    best_ref = "trace"
    # Higher is a closer match. Negative means nothing has been chosen.
    best_score = -1
    # Score every fact.
    for fact in facts:
        # Numbers this fact contributes.
        fact_numbers = numbers_in(fact.text)
        # How many claim numbers this fact explains.
        overlap = sum(1 for number in claim_numbers if number_allowed(number, fact_numbers))
        # Domain words shared with this fact.
        words = sum(1 for word in _DOMAIN_WORDS if word in lowered and word in fact.text.lower())
        # Numbers matter more than words.
        score = overlap * 10 + words
        # Keep the closer fact.
        if score > best_score:
            # New best.
            best_score = score
            # Its pointer.
            best_ref = fact.ref
    # A pointer even when the claim matches nothing. The verified flag carries the failure.
    return best_ref


# Decide whether one sentence is faithful to the fact list.
def claim_is_verified(claim: str, facts: list[TemplatedFact]) -> bool:
    """Return True only when every number and domain word is already in the facts."""
    # The whole fact text is the allowed corpus.
    corpus = "\n".join(fact.text for fact in facts).lower()
    # Numbers the facts state.
    allowed = numbers_in(corpus)
    # A number the facts do not state is an invented quantity.
    if any(not number_allowed(number, allowed) for number in numbers_in(claim)):
        # Reject the claim.
        return False
    # A domain word the facts never use is an invented reason.
    for word in _DOMAIN_WORDS:
        # The claim uses this word.
        if word in claim.lower() and word not in corpus:
            # Reject the claim.
            return False
    # A sentence with neither a number nor a domain word is not a trace claim.
    has_domain_word = any(word in claim.lower() for word in _DOMAIN_WORDS)
    # Fluff such as "the room feels welcoming" is not verified.
    if not numbers_in(claim) and not has_domain_word:
        # Reject the claim.
        return False
    # The sentence stays inside the facts.
    return True
