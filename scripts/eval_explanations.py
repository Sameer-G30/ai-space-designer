"""Phase 8 checks: version diffs, counterfactual latency, and explanation faithfulness.

Faithfulness calls local Ollama (qwen2.5:7b) and is skipped when Ollama is down.
The latency and diff checks do not call Ollama and do not write dataset files.

    uv run python scripts/eval_explanations.py
"""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON for the ungrounded reply.
import json

# Median.
import statistics

# Detect a down Ollama daemon.
import urllib.error
import urllib.request

# Warm and cold what-if solves.
from spacedesigner.explain.counterfactual import prepare_counterfactual

# Fact sentences the grounded prompt is allowed to use.
from spacedesigner.explain.facts import build_facts

# The same checker the API stores.
from spacedesigner.explain.faithfulness import claim_is_verified

# What-if body.
from spacedesigner.explain.models import CounterfactualDesign, CounterfactualRequest

# Grounded phrasing. The ungrounded prompt lives only in this script.
from spacedesigner.explain.rephrase import REPHRASE_SCHEMA, phrase_claims

# Stage 1. This script does not run the Pareto sweep or CLIP.
from spacedesigner.optimizer.catalog import load_catalog
from spacedesigner.optimizer.stage1_cpsat import optimize

# Tag-overlap or cached vectors. No weight download.
from spacedesigner.recommend.scoring import load_style_scorer

# The error a down model raises. phrase_claims catches it; the ungrounded call does not.
from spacedesigner.requirements.errors import ParserFailure

# Local qwen2.5:7b. This script does not pull a model.
from spacedesigner.requirements.ollama_client import OllamaChatClient

# Locked records.
from spacedesigner.schemas import Design, ObjectiveWeights, Requirement, SceneGraph

# How many feasible rooms to time.
ROOM_LIMIT = 8

# Fixed rooms. Sizes and budgets are chosen so a desk, chair, and shelf can fit.
ROOMS = (
    (4.5, 4.0, 40000.0),
    (5.0, 4.0, 50000.0),
    (5.5, 4.5, 60000.0),
    (6.0, 5.0, 70000.0),
    (6.5, 5.0, 80000.0),
    (7.0, 5.5, 90000.0),
    (7.5, 6.0, 100000.0),
    (8.0, 6.0, 120000.0),
)


# One manual scene and a three-item requirement.
def room_pair(
    index: int, length: float, width: float, budget: float
) -> tuple[SceneGraph, Requirement]:
    """Build one high-confidence room. No openings, so the door rule cannot reject it."""
    # Scene id is stable for this list.
    scene_id = f"explain-room-{index}"
    # Validate the scene.
    scene = SceneGraph.model_validate(
        {
            "scene_id": scene_id,
            "version": 1,
            "room_type": "home_office",
            "dimensions": {
                "length": length,
                "width": width,
                "height": 2.8,
                "confidence": "high",
            },
            "openings": [],
            "objects": [],
        }
    )
    # Equal weights. The what-if keeps these weights.
    weights = ObjectiveWeights(
        layout=1.0,
        circulation=1.0,
        ergonomics=1.0,
        budget=1.0,
        aesthetics=1.0,
        sustainability=1.0,
    )
    # Validate the requirement.
    requirement = Requirement.model_validate(
        {
            "requirement_id": f"explain-req-{index}",
            "scene_id": scene_id,
            "raw_text": "",
            "budget_inr": budget,
            "must_have": ["desk", "chair", "shelf"],
            "must_keep_object_ids": [],
            "occupant_count": 1,
            "style": "modern",
            "accessibility_required": False,
            "objective_weights": weights,
        }
    )
    # The pair Stage 1 solves.
    return scene, requirement


# True when the local daemon answers /api/tags.
def ollama_up() -> bool:
    """Return False when Ollama is down. This does not pull a model."""
    # Short timeout so a down daemon does not stall the latency numbers.
    try:
        # Tags only. The body is not parsed.
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2):
            # The daemon answered.
            return True
    # Connection refused, timeout, or an HTTP error.
    except (urllib.error.URLError, TimeoutError):
        # Skip the faithfulness half.
        return False


# Sentences from a prompt that does not include the trace.
def ungrounded_sentences(
    client: OllamaChatClient, room_type: str, categories: list[str]
) -> list[str]:
    """Ask for an explanation without the templated facts."""
    # No numbers are provided. The checker then counts invented ones.
    messages = [
        {
            "role": "system",
            "content": (
                "Explain why this furniture layout was chosen. "
                "Include the budget, clearances, and costs. "
                "Reply with one JSON object whose sentences field is an array of strings."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Room type: {room_type}. Requested categories: {', '.join(categories)}. "
                "You do not have the optimizer trace."
            ),
        },
    ]
    # Same schema as the grounded call, so both sides return a sentence list.
    raw = client.complete(messages, REPHRASE_SCHEMA, num_predict=700)
    # Strip a fence if one was added.
    text = raw.strip()
    # Opening fence.
    if text.startswith("```"):
        # Drop the first line.
        text = text.split("\n", 1)[-1]
        # Drop the closing fence.
        text = text.removesuffix("```").strip()
    # Decode.
    try:
        # Object.
        value = json.loads(text)
    # Not JSON.
    except json.JSONDecodeError:
        # No claims from this call.
        return []
    # Sentences.
    sentences = value.get("sentences") if isinstance(value, dict) else None
    # Not a list.
    if not isinstance(sentences, list):
        # No claims.
        return []
    # Non-empty strings.
    return [item.strip() for item in sentences if isinstance(item, str) and item.strip()]


# Micro rate over every claim.
def _rate(flags: list[bool]) -> float | None:
    """Return verified/total, or None when there are no claims."""
    # Nothing was produced.
    if not flags:
        # Do not invent a rate.
        return None
    # Fraction.
    return sum(1 for flag in flags if flag) / len(flags)


# One solved design kept for the faithfulness prompts.
class _Traced:
    """Scene, requirement, design, and trace from one feasible Stage 1 solve."""

    # Store the four objects the prompts need.
    def __init__(self, scene: SceneGraph, requirement: Requirement, design: Design, trace) -> None:
        """Remember one feasible solve."""
        # Room.
        self.scene = scene
        # Requirement.
        self.requirement = requirement
        # Design, for cost and score facts.
        self.design = design
        # Trace.
        self.trace = trace


# Check one warm-start diff against the two designs.
def _diff_ok(before: Design, after: Design, diff: dict) -> bool:
    """Return True when added, removed, moved, cost, and score match the designs."""
    # Object ids.
    before_ids = {obj.id for obj in before.objects}
    after_ids = {obj.id for obj in after.objects}
    # Added.
    if set(diff["items_added"]) != after_ids - before_ids:
        # Mismatch.
        return False
    # Removed.
    if set(diff["items_removed"]) != before_ids - after_ids:
        # Mismatch.
        return False
    # Cost delta.
    if abs(float(diff["cost_change"]) - (after.cost - before.cost)) > 1e-6:
        # Mismatch.
        return False
    # Score delta.
    if abs(float(diff["score_change"]) - (after.score - before.score)) > 1e-6:
        # Mismatch.
        return False
    # Moved entries.
    moved = diff["items_moved"]
    # The value is a list of objects.
    if not isinstance(moved, list):
        # Mismatch.
        return False
    # Ids that claim to have moved.
    moved_ids = {entry["id"] for entry in moved if isinstance(entry, dict) and "id" in entry}
    # A moved id must exist on both sides.
    return moved_ids <= (before_ids & after_ids)


# Print both rates. A down daemon prints not_run and does not invent a number.
def _faithfulness(client: OllamaChatClient, rows: list[_Traced]) -> int:
    """Print faithfulness rates for the traced designs."""
    # Flags.
    grounded_flags: list[bool] = []
    ungrounded_flags: list[bool] = []
    # Calls that returned model sentences.
    grounded_designs = 0
    ungrounded_designs = 0
    # Each traced design.
    for row in rows:
        # Facts. These designs are not what-ifs, so there is no sensitivity sentence.
        facts = build_facts(row.design, row.trace)
        # Grounded rephrase. phrase_claims turns a daemon failure into the template.
        claims, rephrased, note = phrase_claims(row.design.design_id, facts, client)
        # Count only a real model reply. A template fallback is not the grounded rate.
        if rephrased:
            # This design contributed model claims.
            grounded_designs += 1
            # Every claim.
            grounded_flags.extend(claim.verified for claim in claims)
        # The fallback is visible in the log.
        else:
            # Why the template was kept.
            print(f"grounded fallback {row.design.design_id} {note}", flush=True)
        # Ungrounded prompt. No fact numbers are included.
        try:
            # Categories the requirement asked for.
            sentences = ungrounded_sentences(
                client, row.scene.room_type, list(row.requirement.must_have)
            )
        # Daemon failed.
        except ParserFailure as exc:
            # Latency was already printed. Do not invent a faithfulness rate.
            print(f"faithfulness not_run {exc}", flush=True)
            return 0
        # A sentence list was returned.
        if sentences:
            # Count the design.
            ungrounded_designs += 1
            # Check each sentence against the same facts.
            ungrounded_flags.extend(claim_is_verified(sentence, facts) for sentence in sentences)
    # Rates. None means that side produced no model claims.
    grounded_rate = _rate(grounded_flags)
    ungrounded_rate = _rate(ungrounded_flags)
    # Print only measured values.
    print(
        f"faithfulness grounded_designs {grounded_designs} "
        f"grounded_claims {len(grounded_flags)} "
        f"grounded_verified_rate {grounded_rate} "
        f"ungrounded_designs {ungrounded_designs} "
        f"ungrounded_claims {len(ungrounded_flags)} "
        f"ungrounded_verified_rate {ungrounded_rate}",
        flush=True,
    )
    # Measured.
    return 0


# Time warm starts against cold re-solves, then run faithfulness if Ollama is up.
def main() -> int:
    """Return 0 after printing the measured numbers. A bad diff returns 1."""
    # Catalog once.
    catalog = load_catalog()
    # No embedder, so a missing cache uses tag overlap and nothing is downloaded.
    scorer = load_style_scorer(catalog, save=False)
    # Solver clocks in milliseconds.
    cold_ms: list[float] = []
    warm_ms: list[float] = []
    # Designs kept for the prompts.
    traced: list[_Traced] = []
    # Walk the fixed rooms.
    for index, (length, width, budget) in enumerate(ROOMS, start=1):
        # Stop after enough feasible pairs.
        if len(cold_ms) >= ROOM_LIMIT:
            # Done.
            break
        # Build the room.
        scene, requirement = room_pair(index, length, width, budget)
        # Stage 1 placement.
        solved = optimize(scene, requirement, catalog)
        # Skip an infeasible room. It is not a diff failure.
        if not solved.feasible:
            # Next room.
            print(f"room {index} infeasible: {solved.reason}", flush=True)
            continue
        # Ten percent more budget. The same items should still fit.
        request = CounterfactualRequest(budget_inr=round(budget * 1.1, 2))
        # Cold re-solve. Hints are built and then not passed.
        cold = prepare_counterfactual(
            scene, requirement, solved.design, request, catalog, scorer, use_hints=False
        )
        # Warm re-solve.
        warm = prepare_counterfactual(
            scene, requirement, solved.design, request, catalog, scorer, use_hints=True
        )
        # Both must be feasible for a latency pair.
        if not isinstance(cold.result, CounterfactualDesign) or not isinstance(
            warm.result, CounterfactualDesign
        ):
            # Say so and skip.
            print(f"room {index} counterfactual infeasible", flush=True)
            continue
        # Solver clocks.
        cold_ms.append(cold.result.solve_time_ms)
        warm_ms.append(warm.result.solve_time_ms)
        # The warm diff is the one the API stores.
        if not _diff_ok(solved.design, warm.result.design, warm.result.diff):
            # A wrong diff fails the script.
            print(f"room {index} diff mismatch", flush=True)
            return 1
        # Keep the parent design for the prompts.
        traced.append(_Traced(scene, requirement, solved.design, solved.trace))
        # Progress.
        print(
            f"room {index} cold {cold.result.solve_time_ms:.3f} ms "
            f"warm {warm.result.solve_time_ms:.3f} ms hints {warm.result.hint_count}",
            flush=True,
        )
    # No feasible room means there is nothing to report.
    if not cold_ms:
        # Do not invent a latency.
        print("counterfactual_rooms 0", flush=True)
        return 1
    # Medians. These are the latency numbers the report may quote.
    print(
        f"counterfactual_rooms {len(cold_ms)} "
        f"median_full_rerun_ms {statistics.median(cold_ms):.3f} "
        f"median_warm_start_ms {statistics.median(warm_ms):.3f} "
        f"diffs_ok {len(cold_ms)}",
        flush=True,
    )
    # Faithfulness needs the daemon.
    if not ollama_up():
        # The latency numbers above still stand.
        print("faithfulness not_run ollama_down", flush=True)
        return 0
    # qwen2.5:7b is already pulled. This does not call ollama pull.
    return _faithfulness(OllamaChatClient(), traced)


# Script entry.
if __name__ == "__main__":
    # Propagate the status.
    raise SystemExit(main())
