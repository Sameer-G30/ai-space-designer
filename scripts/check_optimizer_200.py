"""Run the fixed-seed Phase 3 gate on 200 generated rooms."""

# json prints a machine-readable gate summary.
import json

# statistics computes the requested median duration.
import statistics

# Independent audit is the source of violation counts.
from spacedesigner.critic import audit_design

# The existing generator avoids dependency on gitignored synthetic files.
from spacedesigner.data.synthetic import generate

# Solver constants are included in the gate report.
from spacedesigner.optimizer.constants import (
    GRID_SIZE_M,
    LOW_CONFIDENCE_MARGIN_M,
    MIN_CIRCULATION_WIDTH_M,
    MIN_DOOR_CLEAR_WIDTH_M,
    TURNING_SPACE_DIAMETER_M,
)

# The real Stage 1 entry point is benchmarked.
from spacedesigner.optimizer.stage1_cpsat import optimize

# Locked inputs validate generated dictionaries again at the gate.
from spacedesigner.schemas import Requirement, SceneGraph

# Both renderers create one local gitignored example.
from spacedesigner.visualize import render_png, render_svg

# Fixed seed makes every gate repeatable.
BENCHMARK_SEED = 20260930

# Gate room count comes directly from the Phase 3 plan.
ROOM_COUNT = 200


# Execute and print all required Phase 3 counts.
def main() -> int:
    """Run the reproducible benchmark and return a process exit code."""
    # Generate in memory from tracked priors and catalog metadata.
    scene_rows, requirement_rows = generate(ROOM_COUNT, seed=BENCHMARK_SEED)
    # Count successful designs.
    feasible_count = 0
    # Count readable no-design outcomes.
    infeasible_count = 0
    # Accumulate independent checker findings.
    checker_violations = 0
    # Accumulate returned designs over budget.
    budget_breaches = 0
    # Count failed outputs with missing reasons.
    unreadable_reasons = 0
    # Collect durations for every solve attempt.
    solve_times_ms: list[float] = []
    # Keep one feasible tuple for local visual examples.
    example: tuple[SceneGraph, object] | None = None
    # Process paired generated rows in stable order.
    for scene_data, requirement_data in zip(
        scene_rows,
        requirement_rows,
        strict=True,
    ):
        # Validate the generated scene against the locked schema.
        scene = SceneGraph.model_validate(scene_data)
        # Validate the generated requirement against the locked schema.
        requirement = Requirement.model_validate(requirement_data)
        # Solve with the real CP-SAT model and tracked JSONL catalog.
        result = optimize(scene, requirement)
        # Record measured wall-clock duration.
        solve_times_ms.append(result.solve_time_ms)
        # Handle one successful design.
        if result.feasible:
            # Increment successful count.
            feasible_count += 1
            # Run the independent Shapely checker.
            violations = audit_design(scene, requirement, result.design, result.bom)
            # Count every reported hard failure.
            checker_violations += len(violations)
            # Count any returned design beyond budget.
            budget_breaches += int(result.design.cost > requirement.budget_inr + 1e-6)
            # Preserve the first successful result for rendering.
            if example is None:
                # Store exact scene and feasible result.
                example = (scene, result)
        # Handle one no-design outcome.
        else:
            # Increment failure count separately.
            infeasible_count += 1
            # A useful reason contains non-whitespace text.
            unreadable_reasons += int(not result.reason.strip())
    # Render examples only under the already gitignored processed tree.
    if example is not None:
        # Recover the typed scene.
        example_scene = example[0]
        # Recover the feasible result object.
        example_result = example[1]
        # Write the PNG preview.
        render_png(
            example_scene,
            example_result.design,
            "datasets/processed/phase3/example_plan.png",
        )
        # Write the SVG preview.
        render_svg(
            example_scene,
            example_result.design,
            "datasets/processed/phase3/example_plan.svg",
        )
    # Build a stable machine-readable summary.
    summary = {
        "rooms": ROOM_COUNT,
        "seed": BENCHMARK_SEED,
        "feasible": feasible_count,
        "infeasible": infeasible_count,
        "checker_violations": checker_violations,
        "budget_breaches": budget_breaches,
        "unreadable_infeasible_reasons": unreadable_reasons,
        "median_solve_time_ms": round(statistics.median(solve_times_ms), 3),
        "grid_size_m": GRID_SIZE_M,
        "low_confidence_margin_m": LOW_CONFIDENCE_MARGIN_M,
        "minimum_circulation_width_m": MIN_CIRCULATION_WIDTH_M,
        "minimum_door_clear_width_m": MIN_DOOR_CLEAR_WIDTH_M,
        "turning_space_diameter_m": TURNING_SPACE_DIAMETER_M,
    }
    # Print indented JSON for reports and humans.
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Fail the command if any Phase 3 gate invariant is broken.
    return int(
        checker_violations > 0
        or budget_breaches > 0
        or unreadable_reasons > 0
        or feasible_count + infeasible_count != ROOM_COUNT
    )


# Run only when invoked as a script.
if __name__ == "__main__":
    # Exit with the gate result.
    raise SystemExit(main())
