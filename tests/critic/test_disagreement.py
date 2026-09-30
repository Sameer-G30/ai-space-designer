"""Disagreement lines between the advisory VLM and the geometric checker."""

# The logger and the summary.
from spacedesigner.critic.disagreement import (
    disagreement_lines,
    summarize_disagreements,
    violation_kinds,
)


# Phrase mapping.
def test_violation_kinds_follow_the_checker_phrases() -> None:
    """Overlap, clearance, budget, and missing are the four hard kinds."""
    # One string of each family, using phrases the checker actually emits.
    found = violation_kinds(
        [
            "objects 'a' and 'b' overlap",
            "object 'a' blocks opening 0 clearance",
            "design cost INR 10.00 exceeds budget INR 1.00",
            "must-keep object 'c' is absent from design",
        ]
    )
    # All four.
    assert found == {"overlap", "clearance", "budget", "missing"}


# The VLM can disagree without the design changing. This test only checks the lines.
def test_disagreement_lines_are_symmetric() -> None:
    """A VLM-only flag and a checker-only kind are both logged."""
    # Checker found overlap. VLM flagged budget and not overlap.
    lines = disagreement_lines(
        ["objects 'a' and 'b' overlap"],
        {"overlap": False, "clearance": False, "budget": True, "missing": False},
    )
    # Both directions.
    assert "vlm flagged budget and the geometric checker did not" in lines
    # The other direction.
    assert "geometric checker found overlap and the vlm did not flag it" in lines
    # Counts.
    summary = summarize_disagreements(
        [{"disagreements": lines}, {"disagreements": []}]
    )
    # Two rows, one of them disagreed.
    assert summary["rows"] == 2
    # One design disagreed.
    assert summary["rows_with_disagreement"] == 1
    # One line each way.
    assert summary["vlm_only"] == 1
    # Checker side.
    assert summary["checker_only"] == 1


# Agreement is an empty list, including when both are clean.
def test_clean_agreement_has_no_lines() -> None:
    """No violations and no flags is not a disagreement."""
    # Both quiet.
    quiet = {"overlap": False, "clearance": False, "budget": False, "missing": False}
    # No lines.
    assert disagreement_lines([], quiet) == []
