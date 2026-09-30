"""Phase 11 ablation ladder on a new seed. Previously recorded gates are not rerun.

Synthetic rooms use the existing generator. SUN RGB-D rooms use annotated floor
rectangles. NYU layout is not run. Diffusion-only, RoomGPT, RAG-inside-CP-SAT,
and a critic that rejects a design are not run.

    uv run python scripts/eval_ablation.py
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Image bytes for the critic.
import base64

# JSON metrics.
import json

# Seeded SUN sample and pair order.
import random

# Medians.
import statistics

# Ollama presence, without pulling a model.
import urllib.error
import urllib.request

# Paths.
from pathlib import Path

# DATABASE_URL from .env when it is not already exported.
from dotenv import load_dotenv

# Live checker, used again on Pareto points.
from spacedesigner.critic import audit_design

# Disagreement lines. The design is not passed back into the solver.
from spacedesigner.critic.disagreement import disagreement_lines, summarize_disagreements

# Advisory critic. keep_alive 0 unloads it after each call.
from spacedesigner.critic.vlm import advise, vl_model_present

# Existing generator.
from spacedesigner.data.synthetic import generate

# Layout metrics and the coordinate-guess parser.
from spacedesigner.eval.ablation import (
    LAYOUT_SCHEMA,
    REAL_MUST_HAVE,
    aggregate_layouts,
    clearance_gaps,
    design_from_guess,
    diff_matches,
    eligible_sun_rows,
    layout_messages,
    missing_categories,
    no_design_row,
    parse_layout_payload,
    rectangle_scene,
    score_design,
    shortlist_items,
    summarize_gaps,
    sun_layout_rectangle,
    template_budget,
    template_requirement,
)

# Report text, the plot, and the blank sheet.
from spacedesigner.eval.report import (
    answer_key,
    blind_assignment,
    rater_sheet,
    render_report,
    violation_svg,
)

# What-if solves.
from spacedesigner.explain.counterfactual import prepare_counterfactual
from spacedesigner.explain.models import CounterfactualDesign, CounterfactualRequest

# BOM for a guessed purchase list.
from spacedesigner.optimizer.bom import build_bom

# Catalog file.
from spacedesigner.optimizer.catalog import load_catalog

# Stage 1.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Stage 2 dominance test and entry point.
from spacedesigner.optimizer.stage2_pareto import dominates, optimize_pareto

# Unload qwen2.5:7b before the vision critic.
from spacedesigner.perception.runner import unload_llm

# Retrieval beside the parse. Numbers are not applied.
from spacedesigner.rag.hybrid import HybridRetriever

# Style vectors from the existing cache. No download: embedder is omitted.
from spacedesigner.recommend.scoring import load_style_scorer

# ParserFailure is a down or invalid model, not a layout violation.
from spacedesigner.requirements.errors import ParserFailure

# Field accuracy on this sample only.
from spacedesigner.requirements.metrics import TEXT_GROUNDED_FIELDS, field_matches, micro_accuracy

# Local chat model. This script does not pull one.
from spacedesigner.requirements.ollama_client import OllamaChatClient

# Product parser.
from spacedesigner.requirements.parser import parse_requirement

# Retrieval helper that already refuses to edit solver constants.
from spacedesigner.requirements.service import retrieve_numbers

# Locked records.
from spacedesigner.schemas import Requirement, SceneGraph

# Plan images for the sheet and the critic.
from spacedesigner.visualize.plan2d import render_png

# New seed. The 200-room gate keeps 20260930.
SEED = 20261001

# Synthetic rooms asked of the language model.
SYNTHETIC_ROOMS = 16

# Annotated SUN RGB-D test rooms.
SUN_ROOMS = 8

# Plans the advisory critic reads.
CRITIC_PLANS = 4

# Pairs on the blank preference sheet.
PAIR_LIMIT = 6

# What-if rooms on this sample. Phase 8's eight-room table is cited, not replaced.
COUNTERFACTUAL_LIMIT = 8

# Repository root.
ROOT = Path(__file__).resolve().parents[1]

# Report paths. They are tracked. Dataset images are not written here as raw photos.
REPORT_DIR = ROOT / "docs" / "reports"

# Machine-readable summary plus per-room rows.
METRICS_PATH = REPORT_DIR / "ablation_metrics.json"

# Markdown report.
REPORT_PATH = REPORT_DIR / "evaluation_ablation.md"

# Bar chart.
SVG_PATH = REPORT_DIR / "ablation_violation_rates.svg"

# Preference folder.
PREFERENCE_DIR = REPORT_DIR / "preference"

# Plan images named for the rater.
PAIR_DIR = PREFERENCE_DIR / "pairs"


# True when the local daemon answers.
def ollama_up() -> bool:
    """Return False when Ollama is down. This does not pull a model."""
    # Short timeout.
    try:
        # Tags only.
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2):
            # The daemon answered.
            return True
    # Down or slow.
    except (urllib.error.URLError, TimeoutError):
        # Skip the language-model rungs.
        return False


# Drop long violation lists before writing JSON.
def slim(row: dict) -> dict:
    """Copy a row with at most twelve violation strings."""
    # Shallow copy.
    copied = dict(row)
    # Full list.
    violations = copied.get("violations")
    # Only trim a list.
    if isinstance(violations, list) and len(violations) > 12:
        # Keep the count exact and the first twelve strings.
        copied["violations"] = violations[:12]
        # How many were omitted.
        copied["violations_omitted"] = len(violations) - 12
    # Slim row.
    return copied


# Stage 1 on each pair.
def run_stage1(pairs: list[tuple[SceneGraph, Requirement]]) -> tuple[list[dict], dict]:
    """Return scored rows and the feasible results keyed by scene id."""
    # Rows.
    rows: list[dict] = []
    # Feasible solves for rendering and what-if.
    saved: dict = {}
    # Each room.
    for scene, requirement in pairs:
        # Existing solver.
        result = optimize(scene, requirement)
        # No design.
        if not result.feasible:
            # Count it separately from a violation.
            row = no_design_row(result.reason)
            # Scene id.
            row["scene_id"] = scene.scene_id
            # Keep the row.
            rows.append(row)
            # Next room.
            continue
        # Score the returned design.
        row = score_design(scene, requirement, result.design, result.bom)
        # Scene id.
        row["scene_id"] = scene.scene_id
        # Keep the row.
        rows.append(row)
        # Keep the objects needed later.
        saved[scene.scene_id] = (scene, requirement, result)
        # Progress.
        print(f"cp-sat {scene.scene_id} violations {row['violation_count']}", flush=True)
    # Rows and solves.
    return rows, saved


# One coordinate guess per room, two JSON attempts.
def run_llm(
    pairs: list[tuple[SceneGraph, Requirement]],
    client: OllamaChatClient,
) -> tuple[list[dict], dict]:
    """Return scored guesses. A bad JSON reply is no design, not a violation."""
    # Catalog for the shortlist. Stage 1 loads the same file inside optimize.
    catalog = load_catalog()
    # Rows.
    rows: list[dict] = []
    # Designs for the sheet.
    saved: dict = {}
    # A dead daemon should not be retried for every remaining room.
    transport_failure: str | None = None
    # Each room.
    for scene, requirement in pairs:
        # Reuse the transport error without another call.
        if transport_failure is not None:
            # No design.
            row = no_design_row(transport_failure)
            # Scene id.
            row["scene_id"] = scene.scene_id
            # Keep it.
            rows.append(row)
            # Next room.
            continue
        # Categories that still need a purchase.
        categories = missing_categories(scene, requirement)
        # Three cheapest rows per category.
        shortlist = shortlist_items(catalog, categories)
        # Prompt. Retrieved numbers are not added.
        messages = layout_messages(scene, requirement, shortlist)
        # Parsed object, if any.
        payload = None
        # Last error.
        error = "no model output"
        # Two attempts.
        for _attempt in range(2):
            # The daemon.
            try:
                # Greedy JSON. Token cap covers a handful of objects.
                raw = client.complete(messages, LAYOUT_SCHEMA, num_predict=900)
            # Down, missing model, or timeout.
            except ParserFailure as exc:
                # Stop retrying this room.
                error = str(exc)
                # A down daemon will fail every later room the same way.
                if "did not answer" in error or "non-JSON envelope" in error:
                    # Remember it.
                    transport_failure = error
                # Leave payload empty.
                break
            # Decode.
            try:
                # Object with an objects list.
                payload = parse_layout_payload(raw)
                # Success.
                break
            # Bad JSON.
            except ValueError as exc:
                # Remember it.
                error = str(exc)
                # Show the model the failure.
                messages = [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            f"That JSON failed: {error} Reply with corrected JSON only."
                        ),
                    },
                ]
        # No usable object.
        if payload is None:
            # No design.
            row = no_design_row(error)
            # Scene id.
            row["scene_id"] = scene.scene_id
            # Keep it.
            rows.append(row)
            # Progress.
            print(f"llm {scene.scene_id} no design", flush=True)
            # Next room.
            continue
        # Build a design. Unknown ids are skipped.
        design, selected, notes = design_from_guess(payload, scene, requirement, shortlist)
        # Bill for the accepted purchases.
        bom = build_bom(selected)
        # Checker.
        row = score_design(scene, requirement, design, bom)
        # Scene id.
        row["scene_id"] = scene.scene_id
        # Skip notes, trimmed.
        row["notes"] = notes[:8]
        # Keep the row.
        rows.append(row)
        # Plan source.
        saved[scene.scene_id] = (scene, design)
        # Progress.
        print(f"llm {scene.scene_id} violations {row['violation_count']}", flush=True)
    # Rows and designs.
    return rows, saved


# Parse the gold sentences. This does not retune the parser.
def run_parser(pairs: list[tuple[SceneGraph, Requirement]], client: OllamaChatClient) -> dict:
    """Return schema-valid and field accuracy on this sample only."""
    # Field rows.
    matches: list[dict[str, bool]] = []
    # Schema-valid count.
    valid = 0
    # Each gold pair.
    for scene, requirement in pairs:
        # Object ids the parser may copy.
        objects = [(obj.id, obj.type) for obj in scene.objects]
        # Product parser.
        try:
            # One sentence.
            parsed, _attempts = parse_requirement(
                requirement.raw_text,
                scene.scene_id,
                requirement.requirement_id,
                objects,
                client,
            )
        # Invalid after the retry budget, or a down model.
        except ParserFailure as exc:
            # Progress.
            print(f"parse {scene.scene_id} failed {exc}", flush=True)
            # Next sentence.
            continue
        # Schema-valid.
        valid += 1
        # Compare with gold. Identity fields are not in the metric.
        matches.append(field_matches(requirement.model_dump(), parsed.model_dump()))
        # Progress.
        print(f"parse {scene.scene_id} ok", flush=True)
    # Rooms asked.
    rooms = len(pairs)
    # Summary.
    return {
        "rooms": rooms,
        "schema_valid": valid,
        "schema_valid_rate": (valid / rooms) if rooms else None,
        "field_accuracy": micro_accuracy(matches) if matches else None,
        "text_grounded_accuracy": (
            micro_accuracy(matches, TEXT_GROUNDED_FIELDS) if matches else None
        ),
        "model": "qwen2.5:7b",
    }


# Record retrieved numbers. Do not pass them to optimize.
def run_rag(pairs: list[tuple[SceneGraph, Requirement]]) -> dict:
    """Return gap counts. applied_to_solver stays false."""
    # One retriever. Models load on the first search.
    retriever = HybridRetriever()
    # Per-room gap lists.
    per_room: list[list[dict]] = []
    # Each sentence.
    for scene, requirement in pairs:
        # Existing helper.
        numbers, note = retrieve_numbers(requirement.raw_text, retriever)
        # A dead index on the first room stops the rest.
        if not numbers and note not in {"ok", "ok; no clearance numbers in the top chunks"}:
            # Not run.
            return {"status": "not_run", "reason": note}
        # Compare with named constants.
        per_room.append(clearance_gaps([(item.name, item.value_m) for item in numbers]))
        # Progress.
        print(f"rag {scene.scene_id} numbers {len(numbers)}", flush=True)
    # Counts.
    return summarize_gaps(per_room)


# Stage 2 on each pair.
def run_pareto(pairs: list[tuple[SceneGraph, Requirement]], scorer: object) -> dict:
    """Return Pareto counts for this sample. The 200-room gate is separate."""
    # Histogram.
    sizes: dict[str, int] = {}
    # Violations.
    violations = 0
    # Budget.
    breaches = 0
    # Dominated pairs.
    dominated_pairs = 0
    # Feasible sets.
    feasible = 0
    # Times.
    times: list[float] = []
    # Backend label.
    backend = "n/a"
    # Each room.
    for scene, requirement in pairs:
        # Existing Stage 2.
        result = optimize_pareto(scene, requirement, scorer=scorer)
        # Sweep time.
        times.append(result.solve_time_ms)
        # No set.
        if not result.feasible:
            # Next room.
            continue
        # One set.
        feasible += 1
        # Backend from the result.
        backend = result.style_backend
        # Size key.
        key = str(len(result.points))
        # Histogram.
        sizes[key] = sizes.get(key, 0) + 1
        # Each point.
        for point in result.points:
            # Checker.
            violations += len(audit_design(scene, requirement, point.design, point.bom))
            # Budget.
            breaches += int(point.design.cost > requirement.budget_inr + 1e-6)
        # Terms.
        terms = [point.trace.objective_terms.model_dump() for point in result.points]
        # Pairs inside the set.
        dominated_pairs += sum(
            dominates(left, right)
            for index, left in enumerate(terms)
            for other, right in enumerate(terms)
            if index != other
        )
        # Progress.
        print(f"pareto {scene.scene_id} points {len(result.points)}", flush=True)
    # Summary.
    return {
        "rooms": len(pairs),
        "feasible": feasible,
        "infeasible": len(pairs) - feasible,
        "checker_violations": violations,
        "budget_breaches": breaches,
        "dominated_pairs": dominated_pairs,
        "points_per_set": sizes,
        "style_backend": backend,
        "median_sweep_ms": statistics.median(times) if times else None,
    }


# What-if on the first feasible Stage 1 designs.
def run_counterfactual(saved: dict, scorer: object) -> dict:
    """Time a +10 percent budget. A bad diff is recorded, not hidden."""
    # Clocks.
    cold_ms: list[float] = []
    # Warm clocks.
    warm_ms: list[float] = []
    # Correct diffs.
    diffs_ok = 0
    # Rooms used.
    used = 0
    # Feasible solves in insertion order.
    for scene, requirement, result in list(saved.values())[:COUNTERFACTUAL_LIMIT]:
        # Plus ten percent.
        request = CounterfactualRequest(budget_inr=round(requirement.budget_inr * 1.1, 2))
        # Catalog.
        catalog = load_catalog()
        # Cold.
        cold = prepare_counterfactual(
            scene, requirement, result.design, request, catalog, scorer, use_hints=False
        )
        # Warm.
        warm = prepare_counterfactual(
            scene, requirement, result.design, request, catalog, scorer, use_hints=True
        )
        # Both need a design.
        if not isinstance(cold.result, CounterfactualDesign) or not isinstance(
            warm.result, CounterfactualDesign
        ):
            # Skip this room.
            print(f"counterfactual {scene.scene_id} infeasible", flush=True)
            # Next.
            continue
        # Clocks.
        cold_ms.append(cold.result.solve_time_ms)
        # Warm clock.
        warm_ms.append(warm.result.solve_time_ms)
        # Diff.
        ok = diff_matches(result.design, warm.result.design, warm.result.diff)
        # Count.
        diffs_ok += int(ok)
        # Used.
        used += 1
        # Progress.
        print(
            f"counterfactual {scene.scene_id} cold {cold.result.solve_time_ms:.3f} "
            f"warm {warm.result.solve_time_ms:.3f}",
            flush=True,
        )
    # None completed.
    if used == 0:
        # Not a fabricated latency.
        return {"status": "not_run", "reason": "no feasible what-if on this sample"}
    # Summary.
    return {
        "rooms": used,
        "median_full_rerun_ms": statistics.median(cold_ms),
        "median_warm_start_ms": statistics.median(warm_ms),
        "diffs_ok": diffs_ok,
    }


# SUN rooms from annotated layouts.
def load_sun_pairs(limit: int) -> tuple[list[tuple[SceneGraph, Requirement]], str]:
    """Return up to limit plausible test rooms and a short note."""
    # Manifest.
    manifest_path = ROOT / "datasets" / "processed" / "sun_rgbd" / "manifest.jsonl"
    # Missing export.
    if not manifest_path.exists():
        # Empty sample.
        return [], "SUN RGB-D manifest is not on disk."
    # Rows.
    rows = []
    # Each line.
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        # Skip blanks.
        if line.strip():
            # One record.
            rows.append(json.loads(line))
    # Supported room types, test split, not an NYU twin.
    eligible = eligible_sun_rows(rows)
    # Seeded order.
    rng = random.Random(SEED)
    # Copy.
    pool = list(eligible)
    # Shuffle.
    rng.shuffle(pool)
    # Catalog for the template budget.
    catalog = load_catalog()
    # Chosen pairs.
    chosen: list[tuple[SceneGraph, Requirement]] = []
    # Skipped layouts.
    skipped = 0
    # Walk until the sample is full.
    for row in pool:
        # Layout file.
        layout_path = (
            ROOT / "datasets" / "processed" / "sun_rgbd" / "geometry" / "test" / row["id"]
            / "layout.json"
        )
        # Missing file.
        if not layout_path.exists():
            # Skip.
            skipped += 1
            # Next.
            continue
        # Annotation.
        payload = json.loads(layout_path.read_text(encoding="utf-8"))
        # Rectangle. A bad polygon is skipped, not fatal.
        try:
            # Shapely rectangle.
            rect = sun_layout_rectangle(payload)
        # Unexpected geometry.
        except (TypeError, ValueError):
            # Skip.
            skipped += 1
            # Next row.
            continue
        # Implausible.
        if rect is None:
            # Skip.
            skipped += 1
            # Next.
            continue
        # Sides.
        length, width, height = rect
        # Empty scene.
        scene = rectangle_scene(row["id"], row["room_type"], length, width, height)
        # Budget from median prices.
        budget = template_budget(catalog, REAL_MUST_HAVE[row["room_type"]])
        # Template requirement. It is not parsed.
        requirement = template_requirement(row["id"], row["room_type"], budget)
        # Keep the pair.
        chosen.append((scene, requirement))
        # Enough.
        if len(chosen) >= limit:
            # Stop.
            break
    # Note for the report.
    note = (
        f"Eligible SUN test rows before the rectangle filter: {len(eligible)}. "
        f"Skipped missing or implausible layouts while filling the sample: {skipped}. "
        f"Rooms used: {len(chosen)}."
    )
    # Pairs and note.
    return chosen, note


# Advisory critic on a few plans. Designs are compared before and after and not edited.
def run_critic(plans: list[tuple[SceneGraph, object, list[str]]]) -> dict:
    """Return disagreement counts. Raises nothing; a failure is not_run."""
    # No plans.
    if not plans:
        # Nothing to ask.
        return {"status": "not_run", "reason": "no plan was available"}
    # Model must already be pulled.
    if not vl_model_present():
        # Do not pull.
        return {"status": "not_run", "reason": "qwen2.5vl:7b is not listed by Ollama"}
    # Free the text model first.
    unload_llm()
    # Rows for the existing summariser.
    logged = []
    # Unchanged designs.
    unchanged = 0
    # Each plan.
    for scene, design, violations in plans:
        # Snapshot before the call.
        before = design.model_dump()
        # A small PNG under the preference folder. It is a plan, not a photo.
        path = PAIR_DIR / f"critic_{scene.scene_id}.png"
        # Render.
        render_png(scene, design, path)
        # Bytes.
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        # Short summary. The checker text is included so the log can be read later.
        summary = (
            f"room {scene.dimensions.length:.2f} by {scene.dimensions.width:.2f}. "
            f"cost {design.cost:.0f}. violations {len(violations)}."
        )
        # The vision model.
        try:
            # One advisory reply.
            advice = advise(encoded, summary)
        # Daemon or JSON failure.
        except RuntimeError as exc:
            # Stop. Do not pull.
            return {"status": "not_run", "reason": str(exc)}
        # Snapshot after. advise does not receive the design.
        after = design.model_dump()
        # Unchanged.
        unchanged += int(before == after)
        # Lines.
        lines = disagreement_lines(violations, advice["flags"])
        # One log row.
        logged.append({"scene_id": scene.scene_id, "disagreements": lines})
        # Progress.
        print(f"critic {scene.scene_id} lines {len(lines)}", flush=True)
    # Counts.
    counts = summarize_disagreements(logged)
    # Report block.
    return {
        "images": len(plans),
        "rows_with_disagreement": counts.get("rows_with_disagreement", 0),
        "lines": sum(len(row["disagreements"]) for row in logged),
        "designs_unchanged": unchanged,
        "log": logged,
    }


# Write blinded plan pairs.
def write_pairs(assignment: list[dict], cpsat: dict, guessed: dict) -> None:
    """Write image A and image B for each pair. The filename does not say which method."""
    # Folder.
    PAIR_DIR.mkdir(parents=True, exist_ok=True)
    # Each pair.
    for row in assignment:
        # Scene.
        scene_id = row["scene_id"]
        # Both plans exist or the caller would not have assigned the pair.
        methods = {"cp_sat": cpsat[scene_id], "llm": guessed[scene_id]}
        # Left.
        left_scene, left_design = methods[row["left"]]
        # Right. The scene is the same room.
        _right_scene, right_design = methods[row["right"]]
        # Image A.
        render_png(left_scene, left_design, PAIR_DIR / f"pair_{row['pair']:02d}_a.png")
        # Image B.
        render_png(left_scene, right_design, PAIR_DIR / f"pair_{row['pair']:02d}_b.png")


# Bars for the plot.
def plot_bars(summary: dict) -> list[tuple[str, float | None]]:
    """Return violation rates for methods that returned an aggregate."""
    # Labels and keys.
    specs = (
        ("synth CP-SAT", "synthetic_cp_sat"),
        ("synth LLM", "synthetic_llm"),
        ("SUN CP-SAT", "sun_cp_sat"),
        ("SUN LLM", "sun_llm"),
    )
    # Bars.
    bars = []
    # Each series.
    for label, key in specs:
        # Block.
        block = summary.get(key)
        # Not an aggregate.
        if not isinstance(block, dict) or block.get("status") == "not_run":
            # Omit the rate.
            bars.append((label, None))
            # Next.
            continue
        # Rate among returned designs.
        bars.append((label, block.get("violation_rate")))
    # Four labels.
    return bars


# Build the six rung paragraphs from what actually ran.
def rung_text(summary: dict) -> list[dict]:
    """Return the six ladder steps with ran or not-run prose."""
    # Parser status.
    parser = summary.get("parser") or {}
    # RAG status.
    rag = summary.get("rag") or {}
    # Critic status.
    critic = summary.get("critic") or {}
    # LLM status.
    llm = summary.get("synthetic_llm") or {}
    # Step 1.
    step1 = (
        "Parsing ran on the synthetic sentences in this sample. "
        "Diffusion-only and a commercial RoomGPT call did not run. "
        "The live generator is Stable Diffusion 1.5 inpainting with ControlNet-depth "
        "on an existing design, not an image from text alone."
        if parser.get("status") != "not_run"
        else f"Parsing did not run. {parser.get('reason', '')} "
        "Diffusion-only and RoomGPT did not run."
    )
    # Step 2.
    step2 = (
        "On synthetic rooms the scene is the generator, not a photo. "
        "On SUN RGB-D the scene is the annotated floor rectangle, not a new "
        "perception pass. NYU layout was not run. Phase 7b geometry numbers are "
        "cited as previously recorded."
    )
    # Step 3.
    step3 = (
        "Retrieval ran and the numbers were recorded beside the requirement. "
        "They were not applied inside CP-SAT, so this step does not change the "
        "layout metrics of step 4."
        if rag.get("status") != "not_run"
        else f"Retrieval did not run. {rag.get('reason', '')}"
    )
    # Step 4.
    step4 = (
        "CP-SAT and an LLM coordinate guess both ran on the same rooms and the "
        "same catalog shortlist rules. The guess is qwen2.5:7b, temperature 0."
        if llm.get("status") != "not_run"
        else f"CP-SAT ran. The coordinate guess did not. {llm.get('reason', '')}"
    )
    # Step 5.
    step5 = (
        "The advisory critic ran on plan images. Disagreements were logged. "
        "Designs were left unchanged. A loop that rejects or rewrites a design "
        "did not run."
        if critic.get("status") != "not_run"
        else f"The advisory critic did not run. {critic.get('reason', '')} "
        "A reject loop did not run."
    )
    # Step 6.
    step6 = (
        "This sample has a Pareto set and a counterfactual where those sections "
        "below are filled. Trace-grounded explanation faithfulness is the previously "
        "recorded Phase 8 result (96 of 96 versus 8 of 16). It was not rerun."
    )
    # Six steps.
    return [
        {"step": 1, "name": "requirement parsing plus diffusion only", "text": step1},
        {"step": 2, "name": "plus the CV scene graph", "text": step2},
        {"step": 3, "name": "plus RAG numbers recorded beside the parse", "text": step3},
        {"step": 4, "name": "plus CP-SAT instead of an LLM coordinate guess", "text": step4},
        {"step": 5, "name": "plus the advisory critic", "text": step5},
        {
            "step": 6,
            "name": "full system (explanation, Pareto, counterfactual)",
            "text": step6,
        },
    ]


# Reasons that stay not-run even when other steps succeed.
def not_run_reasons(nyu_count: int) -> list[str]:
    """Return the standing not-run list."""
    # Fixed reasons plus the NYU count from disk.
    return [
        "Commercial RoomGPT, Interior AI, and Spacely AI were not called.",
        "Diffusion-only, with no scene graph, was not run. The live path is "
        "Stable Diffusion 1.5 inpainting plus ControlNet-depth on a design.",
        "A second ControlNet and SDXL were not added. Phase 9's consistency rate "
        "is one image and was not rerun as a large set.",
        "Retrieved clearance numbers were not inserted into CP-SAT.",
        "The critic was not allowed to drop or rewrite a design.",
        (
            f"NYU layout was not run. {nyu_count} NYU test frames are on disk as "
            "images, depth, and labels. They do not include a room rectangle, and "
            "the photo pipeline was not re-run."
        ),
        "Structured3D perspective images were not downloaded.",
        "Phase 12 (CubiCasa5K floor-plan parser, COLMAP, GraphRAG) was not started.",
        "No model was retrained. No catalog, RAG chunk, or embedding was overwritten.",
    ]


# Write every report file and return the summary.
def write_outputs(summary: dict, assignment: list[dict]) -> None:
    """Write the markdown, JSON, SVG, sheet, and answer key."""
    # Folder.
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # Preference folder.
    PREFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    # JSON.
    METRICS_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # Markdown.
    REPORT_PATH.write_text(render_report(summary), encoding="utf-8")
    # Plot.
    SVG_PATH.write_text(violation_svg(plot_bars(summary)), encoding="utf-8")
    # Rater sheet. Scores stay blank.
    (PREFERENCE_DIR / "rater_sheet.md").write_text(rater_sheet(assignment), encoding="utf-8")
    # Key.
    (PREFERENCE_DIR / "answer_key.md").write_text(answer_key(assignment), encoding="utf-8")


# Run the ladder.
def main() -> int:
    """Measure the ladder and write docs/reports. Return 0 when the report exists."""
    # .env for retrieval. A missing file is fine; RAG then records not_run.
    load_dotenv(ROOT / ".env")
    # Catalog cache warms Stage 1 too.
    load_catalog()
    # Synthetic pairs.
    scene_rows, requirement_rows = generate(SYNTHETIC_ROOMS, seed=SEED)
    # Validated pairs.
    synthetic = [
        (SceneGraph.model_validate(scene), Requirement.model_validate(requirement))
        for scene, requirement in zip(scene_rows, requirement_rows, strict=True)
    ]
    # SUN pairs.
    sun_pairs, sun_note = load_sun_pairs(SUN_ROOMS)
    # Progress.
    print(f"synthetic {len(synthetic)} sun {len(sun_pairs)}", flush=True)
    # Stage 1.
    synthetic_rows, synthetic_saved = run_stage1(synthetic)
    # SUN Stage 1.
    sun_rows, sun_saved = run_stage1(sun_pairs)
    # Scorer from the cache only.
    scorer = load_style_scorer(load_catalog(), save=False)
    # Pareto.
    pareto_synthetic = run_pareto(synthetic, scorer)
    # SUN Pareto.
    pareto_sun = run_pareto(sun_pairs, scorer) if sun_pairs else {
        "status": "not_run",
        "reason": "no SUN room was loaded",
    }
    # What-if on synthetic Stage 1 designs.
    counterfactual = run_counterfactual(synthetic_saved, scorer)
    # Language-model blocks default to not_run.
    parser = {"status": "not_run", "reason": "Ollama is down"}
    # LLM synthetic.
    synthetic_llm_rows: list[dict] = []
    # LLM designs.
    llm_saved: dict = {}
    # SUN LLM rows.
    sun_llm_rows: list[dict] = []
    # Daemon.
    if ollama_up():
        # Client. The model is already pulled. This does not call ollama pull.
        client = OllamaChatClient()
        # Parser on synthetic gold text only.
        parser = run_parser(synthetic, client)
        # Coordinate guesses.
        synthetic_llm_rows, llm_saved = run_llm(synthetic, client)
        # SUN guesses, only when a room was loaded.
        if sun_pairs:
            # Same client. The text model stays loaded for this batch.
            sun_llm_rows, _sun_saved = run_llm(sun_pairs, client)
    # RAG. CPU models. Failure becomes not_run.
    try:
        # Retrieve.
        rag = run_rag(synthetic)
    # A URL or driver error before the helper's own catch.
    except Exception as exc:
        # Do not include a connection string.
        rag = {"status": "not_run", "reason": "retrieval failed before numbers were recorded"}
        # Progress. The exception type is enough.
        print(f"rag not_run {type(exc).__name__}", flush=True)
    # Critic plans: two CP-SAT and two guesses when both exist.
    plans = []
    # CP-SAT plans first.
    for scene_id, (scene, _requirement, result) in synthetic_saved.items():
        # Cap.
        if sum(1 for _item in plans) >= 2:
            # Enough CP-SAT plans.
            break
        # Violations from the scored row.
        matched = next(row for row in synthetic_rows if row["scene_id"] == scene_id)
        # One plan.
        plans.append((scene, result.design, matched.get("violations", [])))
    # LLM plans.
    for scene_id, (scene, design) in llm_saved.items():
        # Cap at four.
        if len(plans) >= CRITIC_PLANS:
            # Enough.
            break
        # Matching row.
        matched = next(row for row in synthetic_llm_rows if row["scene_id"] == scene_id)
        # One plan.
        plans.append((scene, design, matched.get("violations", [])))
    # Critic. Unloads the text model first when it runs.
    critic = run_critic(plans)
    # Preference scenes: synthetic rooms with both plans.
    both = [scene_id for scene_id in llm_saved if scene_id in synthetic_saved]
    # Assignment. Empty when the guess did not run.
    assignment = blind_assignment(SEED, both[:PAIR_LIMIT])
    # Images.
    if assignment:
        # CP-SAT plans stored as (scene, requirement, result).
        cpsat_plans = {
            scene_id: (scene, result.design)
            for scene_id, (scene, _requirement, result) in synthetic_saved.items()
        }
        # Write A/B images.
        write_pairs(assignment, cpsat_plans, llm_saved)
    # NYU frame count, images only.
    nyu_dir = ROOT / "datasets" / "processed" / "nyu_depth_v2" / "test" / "rgb"
    # Count.
    nyu_count = len(list(nyu_dir.glob("*"))) if nyu_dir.exists() else 0
    # LLM aggregates.
    synthetic_llm = (
        aggregate_layouts(synthetic_llm_rows)
        if synthetic_llm_rows
        else {"status": "not_run", "reason": "Ollama is down or returned nothing"}
    )
    # SUN LLM.
    sun_llm = (
        aggregate_layouts(sun_llm_rows)
        if sun_llm_rows
        else {"status": "not_run", "reason": "Ollama is down or no SUN room was guessed"}
    )
    # Summary. Per-room rows are slim.
    summary = {
        "seed": SEED,
        "command": "uv run python scripts/eval_ablation.py",
        "synthetic_rooms": len(synthetic),
        "sun_rooms": len(sun_pairs),
        "sample_note": (
            "Synthetic rooms are a new draw from the existing generator, seed "
            f"{SEED}, count {len(synthetic)}. They are not the Phase 3 gate's 200 rooms. "
            f"{sun_note}"
        ),
        "sun_note": sun_note,
        "synthetic_cp_sat": aggregate_layouts(synthetic_rows),
        "synthetic_llm": synthetic_llm,
        "sun_cp_sat": aggregate_layouts(sun_rows) if sun_rows else {
            "status": "not_run",
            "reason": sun_note,
        },
        "sun_llm": sun_llm,
        "nyu": {
            "status": "not_run",
            "reason": (
                f"{nyu_count} NYU test frames are on disk. The layout ladder was not "
                "run on them because the cleaned export has no room rectangle and the "
                "photo pipeline was not re-run."
            ),
        },
        "parser": parser,
        "rag": rag,
        "pareto_synthetic": pareto_synthetic,
        "pareto_sun": pareto_sun,
        "counterfactual": counterfactual,
        "critic": critic,
        "preference": {"pairs": len(assignment), "collected": False},
        "synthetic_rooms_detail": [slim(row) for row in synthetic_rows],
        "synthetic_llm_detail": [slim(row) for row in synthetic_llm_rows],
        "sun_rooms_detail": [slim(row) for row in sun_rows],
        "sun_llm_detail": [slim(row) for row in sun_llm_rows],
    }
    # Rungs after the blocks exist.
    summary["rungs"] = rung_text(summary)
    # Standing not-run list.
    summary["not_run"] = not_run_reasons(nyu_count)
    # Files.
    write_outputs(summary, assignment)
    # Console.
    print(
        json.dumps(
            {
                "synthetic_cp_sat_clean_rate": summary["synthetic_cp_sat"].get("clean_rate"),
                "synthetic_llm_status": summary["synthetic_llm"].get("status", "ran"),
                "sun_rooms": len(sun_pairs),
                "report": str(REPORT_PATH),
            }
        ),
        flush=True,
    )
    # The report is the deliverable. A measured violation is not a script failure.
    return 0


# Script entry.
if __name__ == "__main__":
    # Status.
    raise SystemExit(main())
