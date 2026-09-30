"""Field-level comparison against synthetic gold. The gold and the schema stay unchanged."""

# Annotations on Python 3.11.
from __future__ import annotations

# isclose compares rupee amounts and weights without exact binary equality.
import math

# Weight names scored one by one.
from spacedesigner.requirements.vocab import WEIGHT_NAMES

# Fields compared for one requirement. Weights are scored separately because gold hides them.
SCORED_FIELDS: tuple[str, ...] = (
    "budget_inr",
    "must_have",
    "must_keep_object_ids",
    "occupant_count",
    "style",
    "accessibility_required",
    *(f"objective_weights.{name}" for name in WEIGHT_NAMES),
)

# Fields the generator actually writes into the sentence. Weights are not in that sentence.
TEXT_GROUNDED_FIELDS: tuple[str, ...] = (
    "budget_inr",
    "must_have",
    "must_keep_object_ids",
    "occupant_count",
    "style",
    "accessibility_required",
)


# True when two rupee or weight numbers are the same at two decimal places.
def _close(left: object, right: object) -> bool:
    """Compare two numbers with a small absolute tolerance."""
    # Both sides must be real numbers. Bool is excluded.
    if isinstance(left, bool) or isinstance(right, bool):
        # Not a numeric field match.
        return False
    # Reject non-numbers.
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        # Not a match.
        return False
    # Gold weights are rounded to 0.01, so this tolerance matches that rounding.
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=0.001)


# Compare one parsed requirement with one gold requirement.
def field_matches(gold: dict, parsed: dict) -> dict[str, bool]:
    """Return a bool for every scored field. Identity fields are not scored."""
    # Budget.
    results = {"budget_inr": _close(gold.get("budget_inr"), parsed.get("budget_inr"))}
    # Class lists match as sets, so order does not count.
    results["must_have"] = set(gold.get("must_have") or []) == set(parsed.get("must_have") or [])
    # Keep ids match as sets.
    results["must_keep_object_ids"] = set(gold.get("must_keep_object_ids") or []) == set(
        parsed.get("must_keep_object_ids") or []
    )
    # People count.
    results["occupant_count"] = gold.get("occupant_count") == parsed.get("occupant_count")
    # Style token.
    results["style"] = gold.get("style") == parsed.get("style")
    # Accessibility flag.
    results["accessibility_required"] = gold.get("accessibility_required") == parsed.get(
        "accessibility_required"
    )
    # Gold weights and parsed weights.
    gold_weights = gold.get("objective_weights") or {}
    # Parsed weights.
    parsed_weights = parsed.get("objective_weights") or {}
    # Each weight is its own field.
    for name in WEIGHT_NAMES:
        # Record the comparison.
        results[f"objective_weights.{name}"] = _close(
            gold_weights.get(name),
            parsed_weights.get(name),
        )
    # Every scored name is present.
    return {name: results[name] for name in SCORED_FIELDS}


# Micro-average over the selected field names.
def micro_accuracy(rows: list[dict[str, bool]], fields: tuple[str, ...] = SCORED_FIELDS) -> float:
    """Return correct/total for the named fields. An empty row list returns 0."""
    # Nothing to score.
    if not rows:
        # Defined rate for an empty run.
        return 0.0
    # Correct comparisons.
    correct = 0
    # Total comparisons.
    total = 0
    # Walk each requirement.
    for row in rows:
        # Walk each requested field.
        for name in fields:
            # One more comparison.
            total += 1
            # Count a match.
            correct += int(row[name])
    # Rate in [0, 1].
    return correct / total


# Per-field rates, in SCORED_FIELDS order.
def per_field_accuracy(rows: list[dict[str, bool]]) -> dict[str, float]:
    """Return the match rate of each scored field."""
    # Empty run.
    if not rows:
        # Every field is zero.
        return {name: 0.0 for name in SCORED_FIELDS}
    # Rate per field.
    return {name: sum(int(row[name]) for row in rows) / len(rows) for name in SCORED_FIELDS}
