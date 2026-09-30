"""Compare the advisory VLM flags with the deterministic checker. Neither path edits a design."""

# Annotations on Python 3.11.
from __future__ import annotations

# JSONL log of disagreements. The file is gitignored under datasets/processed.
import json

# Log path.
from pathlib import Path

# Hard-issue names the VLM is asked to flag. Aesthetic notes are not in this set.
HARD_KINDS = ("overlap", "clearance", "budget", "missing")


# Map a deterministic violation string onto those kinds.
def violation_kinds(violations: list[str]) -> set[str]:
    """Return the hard kinds named by the geometric checker."""
    # Kinds seen in this list.
    found: set[str] = set()
    # One finding.
    for text in violations:
        # Case-insensitive match against the checker's own phrases.
        low = text.lower()
        # Furniture overlap.
        if "overlap" in low:
            # Record it.
            found.add("overlap")
        # Opening clearance, circulation approach, or the turning circle.
        if "clearance" in low or "turning" in low or "blocks opening" in low:
            # Record it.
            found.add("clearance")
        # Budget or the BOM total the checker recomputes.
        if "budget" in low or "cost" in low or "bom" in low:
            # Record it.
            found.add("budget")
        # Missing, moved must-keep, or outside the room.
        if "absent" in low or "outside" in low or "must-keep" in low or "changed pose" in low:
            # Record it.
            found.add("missing")
    # Kinds the checker actually reported.
    return found


# Sentences that describe a mismatch. An empty list means the two checkers agree.
def disagreement_lines(violations: list[str], flags: dict[str, bool]) -> list[str]:
    """Return one line per hard kind that only one checker raised."""
    # Kinds from the Shapely checker.
    checker = violation_kinds(violations)
    # Kinds the VLM set to true. Unknown keys are ignored.
    vlm = {kind for kind in HARD_KINDS if flags.get(kind)}
    # Lines.
    lines: list[str] = []
    # The VLM raised a hard issue the geometry checker did not.
    for kind in sorted(vlm - checker):
        # Advisory only. The caller must not reject the design for this line.
        lines.append(f"vlm flagged {kind} and the geometric checker did not")
    # The geometry checker found a hard issue the VLM did not flag.
    for kind in sorted(checker - vlm):
        # Logged, not applied.
        lines.append(f"geometric checker found {kind} and the vlm did not flag it")
    # Empty when they agree, including when both are clean.
    return lines


# Append one JSON object. The directory is created when needed.
def append_disagreement(path: Path, row: dict) -> None:
    """Append one disagreement record as a JSON line."""
    # Gitignored processed folder, or a test tmp path.
    path.parent.mkdir(parents=True, exist_ok=True)
    # One record per line.
    with path.open("a", encoding="utf-8") as handle:
        # Compact JSON.
        handle.write(json.dumps(row, sort_keys=True) + "\n")


# Counts for the report. This does not call a model.
def summarize_disagreements(rows: list[dict]) -> dict[str, int]:
    """Count rows and how the two checkers split."""
    # Rows that contain at least one disagreement line.
    disagreed = 0
    # Lines where only the VLM raised the kind.
    vlm_only = 0
    # Lines where only the geometric checker raised the kind.
    checker_only = 0
    # One stored row.
    for row in rows:
        # Lines written for this design.
        lines = row.get("disagreements", [])
        # A row with any line is a disagreement.
        if lines:
            # Count the design.
            disagreed += 1
        # One line.
        for line in lines:
            # VLM-only phrasing from disagreement_lines.
            if str(line).startswith("vlm flagged"):
                # Count it.
                vlm_only += 1
            # Checker-only phrasing.
            elif str(line).startswith("geometric checker"):
                # Count it.
                checker_only += 1
    # Totals the report can print.
    return {
        "rows": len(rows),
        "rows_with_disagreement": disagreed,
        "vlm_only": vlm_only,
        "checker_only": checker_only,
    }
