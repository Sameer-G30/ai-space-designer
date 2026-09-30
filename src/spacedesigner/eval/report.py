"""Markdown, SVG, and the blank preference sheet for the Phase 11 report."""

# Annotations on Python 3.11.
from __future__ import annotations

# Seeded side assignment for the blinded pairs.
import random

# Previously recorded numbers. This module does not recompute them.
PREVIOUSLY_RECORDED = (
    "These numbers were already written in docs/reports/. This phase did not rerun them.",
    "",
    "Phase 3 gate, seed 20260930, 200 rooms (optimizer_stage1.md): 109 feasible, "
    "91 infeasible, checker violations 0, budget breaches 0, median solve 4.141 ms.",
    "Phase 4 Pareto gate, same seed (optimizer_stage2.md): the same 109/91 split, "
    "violations 0, budget breaches 0, dominated pairs 0. 102 of 109 sets have 4 to 8 points. "
    "7 sets return fewer because fewer non-dominated designs exist.",
    "Phase 4 recommender, seed 20260929, 200 queries, 197 scored: Precision@5 0.459, "
    "Precision@10 0.361, NDCG@5 0.748, NDCG@10 0.766.",
    "Phase 6 parser, seed 20260930, 100 gold requirements: schema-valid rate 1.000, "
    "field-level accuracy 0.470833, text-grounded field accuracy 0.936667.",
    "Phase 6 Recall@5: 0.966667 (29 of 30).",
    "Phase 7a, seed 20260930: classifier test top-1 0.7492 (248 of 331). "
    "Detector test mAP50 0.558 and mAP50-95 0.434 against zero-shot 0.343 and 0.260.",
    "Phase 7b depth, NYU test, 654 frames: AbsRel 0.2132, RMSE 0.6199 m, delta1 0.6771, "
    "AbsRel after median scaling 0.0741.",
    "Phase 7b segmentation: mean IoU 0.3466 on 64 leak-free NYU test frames.",
    "Phase 7b SUN RGB-D layouts: 473 of 1006 scored. Metric-depth-only median error on the "
    "visible part: length 96 cm, width 105 cm, height 44 cm.",
    "Phase 8, 8 rooms, budget +10%: median full re-run 5.332 ms, median warm start 6.040 ms, "
    "diffs correct 8 of 8. Warm start was slower. Trace-grounded explanations 96 of 96 "
    "(rate 1.0). No trace access 8 of 16 (rate 0.5). qwen2.5:7b, temperature 0.",
    "Phase 9 mask-lock SSIM: 4 rooms at 128 px, mean 1.0, min 1.0, changed_pixels_min 2071. "
    "One 512 px diffusion image: locked-region SSIM 1.0, consistency 0 of 1. "
    "That consistency figure is one image, not a large set. Critic advisory, 3 disagreement "
    "lines, design unchanged. Diffusion-worker peak 3409.3 MiB. nvidia-smi peak 6647 MiB "
    "of 8188 MiB.",
    "Phase 10: Playwright 2 passed (1280x900 and 390x844). That run is the page check. "
    "This phase did not change the page.",
)


# Format a rate, or n/a when the denominator was zero.
def _rate(value: object) -> str:
    """Return a three-decimal rate, or n/a."""
    # Missing.
    if value is None:
        # No denominator.
        return "n/a"
    # Bool is not a rate.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # Show the raw value.
        return str(value)
    # Three decimals.
    return f"{float(value):.3f}"


# One aggregate as markdown lines.
def _aggregate_lines(title: str, summary: object) -> list[str]:
    """Render one method block. A not-run dict stays a reason, not a zero."""
    # Heading.
    lines = [f"### {title}", ""]
    # Missing block.
    if not isinstance(summary, dict):
        # Say so.
        lines.append("Not in this run.")
        # Blank line.
        lines.append("")
        # Done.
        return lines
    # Explicit skip.
    if summary.get("status") == "not_run":
        # Reason.
        lines.append(f"Not run. {summary.get('reason', '')}")
        # Blank line.
        lines.append("")
        # Done.
        return lines
    # Zero rooms.
    if summary.get("rooms", 0) == 0:
        # No invented rate.
        lines.append("No rooms in this split.")
        # Blank line.
        lines.append("")
        # Done.
        return lines
    # Counts.
    rooms = int(summary["rooms"])
    # Returned.
    returned = int(summary["returned"])
    # Table.
    lines.extend(
        [
            "| metric | value |",
            "| --- | ---: |",
            f"| rooms | {rooms} |",
            f"| designs returned | {returned} |",
            f"| no design | {summary['no_design']} |",
            (
                f"| designs with at least one checker violation | "
                f"{summary['with_violation']} of {returned} |"
            ),
            f"| violation rate among returned designs | {_rate(summary.get('violation_rate'))} |",
            f"| mean violations among returned designs | {_rate(summary.get('mean_violations'))} |",
            (
                f"| budget compliant among returned designs | "
                f"{summary['budget_ok']} of {returned} |"
            ),
            (
                f"| clean rooms (returned, no violation, budget, must-have, must-keep) | "
                f"{summary['clean']} of {rooms} |"
            ),
            f"| clean rate over all rooms | {_rate(summary.get('clean_rate'))} |",
            (
                f"| mean must-have rate among returned designs | "
                f"{_rate(summary.get('must_have_mean'))} |"
            ),
            (
                f"| mean must-keep rate where a keep was required | "
                f"{_rate(summary.get('must_keep_mean'))} "
                f"({summary.get('must_keep_rooms', 0)} rooms) |"
            ),
            (
                f"| median footprint-sum / floor area | "
                f"{_rate(summary.get('utilization_median'))} |"
            ),
            f"| median free-floor ratio | {_rate(summary.get('free_floor_median'))} |",
            (
                f"| clearance-clean among returned designs | "
                f"{summary.get('clearance_clean', 0)} of {returned} |"
            ),
            "",
        ]
    )
    # Kind counts.
    kinds = summary.get("kinds") or {}
    # Only when the aggregate recorded them.
    if kinds:
        # Heading.
        lines.append("Hard kinds among returned designs (a design can raise more than one):")
        # Blank.
        lines.append("")
        # Each kind.
        for name, count in kinds.items():
            # One bullet.
            lines.append(f"- {name}: {count} of {returned}")
        # Blank.
        lines.append("")
    # The block.
    return lines


# The full results report.
def render_report(summary: dict) -> str:
    """Return the markdown report. Preference scores are never filled in here."""
    # Lines.
    lines: list[str] = [
        "# Phase 11: evaluation and ablation",
        "",
        "This report measures the system that Phases 0-10 already built.",
        "It does not replace the page, retrain a model, or change the solver.",
        "",
        "## Limitation",
        "",
        "Geometry accuracy is measured on public NYU Depth V2 and SUN RGB-D data,",
        "not on a custom tape-measured photo set. There is no personal tape-measure set",
        "on disk. Structured3D perspective RGB and depth are not on disk and were not",
        "downloaded.",
        "",
        "## What this run is",
        "",
        f"- Command: `{summary.get('command', 'uv run python scripts/eval_ablation.py')}`",
        f"- Seed: {summary.get('seed', 'n/a')}",
        f"- Synthetic rooms: {summary.get('synthetic_rooms', 'n/a')}",
        f"- SUN RGB-D layout rooms: {summary.get('sun_rooms', 'n/a')}",
        "",
        summary.get(
            "sample_note",
            "Synthetic rooms come from the existing generator. SUN rooms use annotated "
            "floor rectangles, not a new photo-pipeline pass.",
        ),
        "",
        "## Previously recorded",
        "",
    ]
    # Static citations.
    lines.extend(PREVIOUSLY_RECORDED)
    # Blank.
    lines.append("")
    # Ladder.
    lines.extend(["## Ladder", ""])
    # Each rung the script recorded.
    for rung in summary.get("rungs", []):
        # Title.
        lines.append(f"### Step {rung.get('step')}: {rung.get('name')}")
        # Blank.
        lines.append("")
        # Status.
        lines.append(str(rung.get("text", "")))
        # Blank.
        lines.append("")
    # Synthetic layouts.
    lines.extend(["## Synthetic layouts", ""])
    # Note.
    lines.append(
        "Violation rate is the fraction of returned designs with at least one "
        "Shapely hard-constraint finding. Clean rate counts a room only when a design "
        "came back with no finding, a legal budget, every must-have category, and every "
        "must-keep pose. A room with no design is not clean. CP-SAT coordinates sit on "
        "the 0.05 m grid. The language-model coordinates are not snapped to that grid. "
        "Its cost is the sum of catalog rows it named from a three-item shortlist. "
        "It does not invent a price."
    )
    # Blank.
    lines.append("")
    # Two methods.
    lines.extend(_aggregate_lines("CP-SAT (Stage 1)", summary.get("synthetic_cp_sat")))
    # LLM.
    lines.extend(_aggregate_lines("LLM coordinate guess", summary.get("synthetic_llm")))
    # Real SUN.
    lines.extend(["## SUN RGB-D test layouts", ""])
    # Geometry note.
    lines.append(str(summary.get("sun_note", "")))
    # Blank.
    lines.append("")
    # Fixed caveat. The sample note above is only the filter count.
    lines.append(
        "These rooms are annotated floor rectangles from the SUN RGB-D test split. "
        "The photo pipeline was not re-run, so perception error is not folded into "
        "these sizes. Openings are absent, so a door-clearance miss cannot occur here. "
        "Confidence is high because the rectangle is the annotation, not a depth estimate. "
        "The rectangle is Shapely's minimum rotated rectangle. Phase 7b's published "
        "centimetre errors used OpenCV's min-area rectangle and were not recomputed."
    )
    # Blank.
    lines.append("")
    # Methods.
    lines.extend(_aggregate_lines("CP-SAT (Stage 1)", summary.get("sun_cp_sat")))
    # LLM.
    lines.extend(_aggregate_lines("LLM coordinate guess", summary.get("sun_llm")))
    # NYU.
    lines.extend(["## NYU Depth V2 test split", ""])
    # NYU block.
    nyu = summary.get("nyu", {"status": "not_run", "reason": "not recorded"})
    # Status.
    if isinstance(nyu, dict) and nyu.get("status") == "not_run":
        # Reason.
        lines.append(f"Layout ladder not run. {nyu.get('reason', '')}")
    # Otherwise.
    else:
        # Whatever the script stored.
        lines.append(str(nyu))
    # Blank.
    lines.append("")
    # Depth citation reminder.
    lines.append(
        "Depth and segmentation for this split are the previously recorded Phase 7b "
        "numbers above. They were not rerun to raise them."
    )
    # Blank.
    lines.append("")
    # Parser.
    lines.extend(["## Requirement parsing on this sample", ""])
    # Block.
    lines.extend(_parser_lines(summary.get("parser")))
    # RAG.
    lines.extend(["## RAG numbers recorded beside the parse", ""])
    # Block.
    lines.extend(_rag_lines(summary.get("rag")))
    # Pareto and counterfactual.
    lines.extend(["## Pareto sets and counterfactuals on this sample", ""])
    # Pareto.
    lines.extend(_pareto_lines("Synthetic", summary.get("pareto_synthetic")))
    # SUN.
    lines.extend(_pareto_lines("SUN RGB-D", summary.get("pareto_sun")))
    # What-if.
    lines.extend(_counterfactual_lines(summary.get("counterfactual")))
    # Critic.
    lines.extend(["## Advisory critic", ""])
    # Block.
    lines.extend(_critic_lines(summary.get("critic")))
    # Preference.
    lines.extend(["## Human preference", ""])
    # Not collected.
    lines.append(
        "A pairwise sheet for friends and faculty is in docs/reports/preference/. "
        "Ratings were not collected. No model score was written into that table."
    )
    # Blank.
    lines.append("")
    # Pair count.
    preference = summary.get("preference") or {}
    # Count.
    lines.append(f"Image pairs prepared: {preference.get('pairs', 0)}.")
    # Blank.
    lines.append("")
    # Collected flag.
    collected = bool(preference.get("collected", False))
    # Words, not a Python bool.
    lines.append(f"Scores collected: {'yes' if collected else 'no'}.")
    # Blank.
    lines.append("")
    # Not run list.
    lines.extend(["## Not run, and why", ""])
    # Each reason.
    for reason in summary.get("not_run", []):
        # Bullet.
        lines.append(f"- {reason}")
    # Blank.
    lines.append("")
    # Plot.
    lines.extend(
        [
            "## Plot",
            "",
            "Violation rate among returned designs, from this run only:",
            "",
            "![violation rates](ablation_violation_rates.svg)",
            "",
            "## Repeat",
            "",
            "```",
            "uv run ruff check .",
            "uv run pytest",
            "uv run python scripts/verify_datasets.py",
            "uv run python scripts/check_optimizer_200.py",
            "uv run python scripts/check_pareto_200.py",
            "uv run python scripts/eval_ablation.py",
            "```",
            "",
            "The Next.js page was not part of this phase. The Phase 10 Playwright run",
            "is `npm run test:e2e` from `frontend/` (2 passed). It was not repeated here.",
            "",
        ]
    )
    # Join.
    return "\n".join(lines)


# Parser block.
def _parser_lines(parser: object) -> list[str]:
    """Render this sample's parser rates, or a not-run reason."""
    # Missing.
    if not isinstance(parser, dict):
        # Say so.
        return ["Not in this run.", ""]
    # Skip.
    if parser.get("status") == "not_run":
        # Reason.
        return [f"Not run. {parser.get('reason', '')}", ""]
    # Table.
    return [
        "This is a new sample. It does not replace the Phase 6 numbers above.",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| sentences | {parser.get('rooms', 0)} |",
        f"| schema-valid | {parser.get('schema_valid', 0)} of {parser.get('rooms', 0)} |",
        f"| schema-valid rate | {_rate(parser.get('schema_valid_rate'))} |",
        f"| field-level accuracy | {_rate(parser.get('field_accuracy'))} |",
        f"| text-grounded field accuracy | {_rate(parser.get('text_grounded_accuracy'))} |",
        f"| model | {parser.get('model', 'qwen2.5:7b')} |",
        "",
    ]


# RAG block.
def _rag_lines(rag: object) -> list[str]:
    """Render retrieval counts. Applied stays false."""
    # Missing.
    if not isinstance(rag, dict):
        # Say so.
        return ["Not in this run.", ""]
    # Skip.
    if rag.get("status") == "not_run":
        # Reason.
        return [f"Not run. {rag.get('reason', '')}", ""]
    # Table.
    return [
        "Retrieved numbers were stored beside the requirement. They were not passed",
        "into CP-SAT. Named solver constants were not edited.",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| queries | {rag.get('rooms', 0)} |",
        f"| queries with at least one number | {rag.get('rooms_with_numbers', 0)} |",
        f"| numbers recorded | {rag.get('numbers', 0)} |",
        f"| numbers mapped to a solver constant | {rag.get('mapped_to_solver_constant', 0)} |",
        (
            "| mapped numbers that differ from that constant | "
            f"{rag.get('mapped_values_that_differ', 0)} |"
        ),
        f"| applied inside CP-SAT | {rag.get('applied_to_solver', False)} |",
        "",
    ]


# Pareto block.
def _pareto_lines(title: str, pareto: object) -> list[str]:
    """Render one Pareto summary."""
    # Heading.
    lines = [f"### Pareto, {title}", ""]
    # Missing.
    if not isinstance(pareto, dict):
        # Say so.
        return [*lines, "Not in this run.", ""]
    # Skip.
    if pareto.get("status") == "not_run":
        # Reason.
        return [*lines, f"Not run. {pareto.get('reason', '')}", ""]
    # Points.
    points = pareto.get("points_per_set") or {}
    # Text of the histogram.
    histogram = ", ".join(
        f"{count} {'set' if count == 1 else 'sets'} with {size} points"
        for size, count in sorted(points.items())
    )
    # Table.
    lines.extend(
        [
            "| metric | value |",
            "| --- | ---: |",
            f"| rooms | {pareto.get('rooms', 0)} |",
            f"| feasible | {pareto.get('feasible', 0)} |",
            f"| infeasible | {pareto.get('infeasible', 0)} |",
            f"| checker violations | {pareto.get('checker_violations', 0)} |",
            f"| budget breaches | {pareto.get('budget_breaches', 0)} |",
            f"| dominated pairs inside returned sets | {pareto.get('dominated_pairs', 0)} |",
            f"| style backend | {pareto.get('style_backend', 'n/a')} |",
            f"| median sweep ms | {_rate(pareto.get('median_sweep_ms'))} |",
            "",
            f"Points per set: {histogram or 'n/a'}.",
            "",
        ]
    )
    # Done.
    return lines


# Counterfactual block.
def _counterfactual_lines(block: object) -> list[str]:
    """Render this sample's what-if timing. Phase 8 is cited separately."""
    # Heading.
    lines = ["### Counterfactual on this sample", ""]
    # Missing.
    if not isinstance(block, dict):
        # Say so.
        return [*lines, "Not in this run.", ""]
    # Skip.
    if block.get("status") == "not_run":
        # Reason.
        return [*lines, f"Not run. {block.get('reason', '')}", ""]
    # Table.
    lines.extend(
        [
            "Budget plus 10 percent, Stage 1, same catalog. This does not replace the",
            "Phase 8 eight-room latency table.",
            "",
            "| metric | value |",
            "| --- | ---: |",
            f"| rooms | {block.get('rooms', 0)} |",
            f"| median full re-run ms | {_rate(block.get('median_full_rerun_ms'))} |",
            f"| median warm start ms | {_rate(block.get('median_warm_start_ms'))} |",
            f"| diffs correct | {block.get('diffs_ok', 0)} of {block.get('rooms', 0)} |",
            "",
        ]
    )
    # This sample's clocks, stated only when both medians exist.
    cold = block.get("median_full_rerun_ms")
    # Warm median.
    warm = block.get("median_warm_start_ms")
    # Both measured.
    if isinstance(cold, (int, float)) and isinstance(warm, (int, float)) and warm > cold:
        # Same direction as the previously recorded Phase 8 table.
        lines.append(
            "On this sample the median warm start was slower than the full re-run."
        )
        # Blank.
        lines.append("")
    # Done.
    return lines


# Critic block.
def _critic_lines(block: object) -> list[str]:
    """Render disagreement counts. The design is not a rejector outcome."""
    # Missing.
    if not isinstance(block, dict):
        # Say so.
        return ["Not in this run.", ""]
    # Skip.
    if block.get("status") == "not_run":
        # Reason.
        return [f"Not run. {block.get('reason', '')}", ""]
    # Table.
    lines = [
        "The critic read top-down plans, not diffusion images. It did not reject or",
        "rewrite a design. Phase 9's 0-of-1 consistency rate is a different measurement",
        "and is cited above as one image.",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| plans | {block.get('images', 0)} |",
        f"| plans with at least one disagreement line | {block.get('rows_with_disagreement', 0)} |",
        f"| disagreement lines | {block.get('lines', 0)} |",
        f"| designs unchanged | {block.get('designs_unchanged', 0)} of {block.get('images', 0)} |",
        "",
        "The runner sends a CP-SAT plan before a language-model plan of the same room.",
        "A repeated scene id is those two plans, not a second critic pass on one image.",
        "",
    ]
    # Optional log from the metrics file.
    log = block.get("log") or []
    # Each stored row.
    for row in log:
        # Scene.
        scene_id = row.get("scene_id", "")
        # Lines.
        disagreements = row.get("disagreements") or []
        # Empty agreement.
        if not disagreements:
            # Say they agreed.
            lines.append(f"- {scene_id}: no disagreement line")
            # Next.
            continue
        # Each line.
        for line in disagreements:
            # One bullet.
            lines.append(f"- {scene_id}: {line}")
    # Blank after the log.
    if log:
        # Separator.
        lines.append("")
    # The block, including the log when the metrics file stored one.
    return lines


# SVG bar chart of violation rates. None means the bar is omitted.
def violation_svg(bars: list[tuple[str, float | None]]) -> str:
    """Return an SVG document. Rates are clipped to the 0-1 axis for drawing."""
    # Canvas. Extra width keeps the four labels from colliding.
    width = 760
    # Height. Extra room under the axis for rotated labels.
    height = 380
    # Plot box.
    left = 80
    # Top.
    top = 48
    # Baseline.
    baseline = 250
    # Bar width.
    bar_width = 48
    # Gap between bars.
    gap = 90
    # Axis height.
    axis = baseline - top
    # Elements.
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        (
            '<text x="16" y="24" font-family="sans-serif" font-size="16">'
            "Violation rate among returned designs</text>"
        ),
        f'<line x1="{left}" y1="{baseline}" x2="{width - 20}" y2="{baseline}" stroke="#222"/>',
    ]
    # Each bar.
    for index, (label, value) in enumerate(bars):
        # X of this bar.
        x = left + 20 + index * (bar_width + gap)
        # Missing rate.
        if value is None:
            # Label only.
            parts.append(
            f'<text x="{x}" y="{baseline + 18}" font-family="sans-serif" font-size="12" '
            f'transform="rotate(35 {x} {baseline + 18})">{label}</text>'
            )
            # Next bar.
            continue
        # Clip for the picture. The table keeps the raw rate.
        clipped = min(1.0, max(0.0, float(value)))
        # Pixel height.
        bar_height = axis * clipped
        # Top of the bar.
        y = baseline - bar_height
        # Rectangle.
        parts.append(
            f'<rect x="{x}" y="{y:.1f}" width="{bar_width}" height="{bar_height:.1f}" '
            'fill="#3d5a80"/>'
        )
        # Value.
        parts.append(
            f'<text x="{x}" y="{y - 6:.1f}" font-family="sans-serif" font-size="11">'
            f"{clipped:.3f}</text>"
        )
        # Label, rotated so neighbouring names do not overlap.
        parts.append(
            f'<text x="{x}" y="{baseline + 18}" font-family="sans-serif" font-size="12" '
            f'transform="rotate(35 {x} {baseline + 18})">{label}</text>'
        )
    # Close.
    parts.append("</svg>")
    # Document.
    return "\n".join(parts)


# Which side is the system. The rater sheet does not include this.
def blind_assignment(seed: int, scene_ids: list[str]) -> list[dict]:
    """Assign each scene to left and right using the ablation seed."""
    # Seeded draw.
    rng = random.Random(seed)
    # Rows.
    rows = []
    # Each scene that has both plans.
    for index, scene_id in enumerate(scene_ids, start=1):
        # Half the time the language-model plan is on the left.
        swap = rng.random() < 0.5
        # Left method.
        left = "llm" if swap else "cp_sat"
        # The other method.
        right = "cp_sat" if swap else "llm"
        # One pair.
        rows.append({"pair": index, "scene_id": scene_id, "left": left, "right": right})
    # All pairs.
    return rows


# Instructions and an empty score table.
def rater_sheet(pairs: list[dict]) -> str:
    """Return the sheet a person would fill. Scores stay blank."""
    # Lines.
    lines = [
        "# Preference sheet",
        "",
        "This sheet is for friends and faculty. It was not filled in.",
        "Ratings were not collected. Do not substitute a model score.",
        "",
        "Each pair is two top-down plans of the same room.",
        "Image A is on the left. Image B is on the right.",
        "Write A, B, or tie if you would rather live with one of them.",
        "Ignore style of the drawing. The colours are only labels.",
        "",
        "| pair | image A | image B | choice (A, B, or tie) | rater | notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    # Each prepared pair.
    for row in pairs:
        # Number.
        number = row["pair"]
        # Empty choice cells. The images are named, not scored.
        lines.append(
            f"| {number} | pairs/pair_{number:02d}_a.png | pairs/pair_{number:02d}_b.png |  |  |  |"
        )
    # Blank line and the collected flag.
    lines.extend(["", "Scores collected: no.", ""])
    # Text.
    return "\n".join(lines)


# Key for later, not for the rater.
def answer_key(pairs: list[dict]) -> str:
    """Return which side is CP-SAT. No human score is included."""
    # Lines.
    lines = [
        "# Answer key",
        "",
        "Do not show this page to a rater before they mark the sheet.",
        "No preference scores have been entered.",
        "",
        "| pair | scene | left | right |",
        "| --- | --- | --- | --- |",
    ]
    # Each pair.
    for row in pairs:
        # One row.
        lines.append(
            f"| {row['pair']} | {row['scene_id']} | {row['left']} | {row['right']} |"
        )
    # Blank.
    lines.append("")
    # Text.
    return "\n".join(lines)
