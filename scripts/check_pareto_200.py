"""Run Stage 2 on the fixed-seed 200 rooms and audit every returned Pareto design."""

# json prints a machine-readable summary.
import json

# statistics reports the median sweep time.
import statistics

# Independent audit is the source of violation counts.
from spacedesigner.critic import audit_design

# Same generator and seed as the Phase 3 gate.
from spacedesigner.data.synthetic import generate

# Stage 2 entry point and dominance test.
from spacedesigner.optimizer.stage2_pareto import dominates, optimize_pareto

# Locked inputs.
from spacedesigner.schemas import Requirement, SceneGraph

# Seed shared with scripts/check_optimizer_200.py.
SEED = 20260930
# Room count shared with the Phase 3 gate.
ROOMS = 200


# Execute the gate and print the summary.
def main() -> int:
    """Return zero only when every invariant holds."""
    # Generate rooms in memory.
    scenes, requirements = generate(ROOMS, seed=SEED)
    # Counters.
    feasible = infeasible = violations = breaches = dominated_pairs = unreadable = 0
    # Point-count histogram and time list.
    sizes: dict[int, int] = {}
    times: list[float] = []
    backends: set[str] = set()
    label_counts: dict[str, int] = {}
    # Process each room.
    for scene_data, req_data in zip(scenes, requirements, strict=True):
        # Validate inputs.
        scene, req = SceneGraph.model_validate(scene_data), Requirement.model_validate(req_data)
        # Run the sweep.
        result = optimize_pareto(scene, req)
        # Track time.
        times.append(result.solve_time_ms)
        # No-design outcome.
        if not result.feasible:
            # Count separately.
            infeasible += 1
            # A reason must be readable.
            unreadable += int(not result.reason.strip())
            # Next room.
            continue
        # Feasible set.
        feasible += 1
        # Record set size and backend.
        sizes[len(result.points)] = sizes.get(len(result.points), 0) + 1
        backends.add(result.style_backend)
        # Audit every point independently.
        for point in result.points:
            # Count labels.
            for label in point.labels:
                # Tally.
                label_counts[label] = label_counts.get(label, 0) + 1
            # Checker findings.
            violations += len(audit_design(scene, req, point.design, point.bom))
            # Budget breaches.
            breaches += int(point.design.cost > req.budget_inr + 1e-6)
        # Pairwise dominance inside the returned set.
        terms = [p.trace.objective_terms.model_dump() for p in result.points]
        # Count dominated pairs (must be zero).
        dominated_pairs += sum(
            dominates(a, b) for i, a in enumerate(terms) for j, b in enumerate(terms) if i != j
        )
    # Summary.
    summary = {
        "rooms": ROOMS, "seed": SEED, "feasible": feasible, "infeasible": infeasible,
        "checker_violations": violations, "budget_breaches": breaches,
        "dominated_pairs": dominated_pairs, "unreadable_infeasible_reasons": unreadable,
        "points_per_set": dict(sorted(sizes.items())), "labels": dict(sorted(label_counts.items())),
        "style_backends": sorted(backends),
        "median_sweep_time_ms": round(statistics.median(times), 3),
        "max_sweep_time_ms": round(max(times), 3),
    }
    # Print.
    print(json.dumps(summary, indent=2))
    # Gate.
    failed = violations or breaches or dominated_pairs or unreadable
    # Also require that every room was accounted for.
    return int(bool(failed) or feasible + infeasible != ROOMS)


# Run only when invoked as a script.
if __name__ == "__main__":
    # Exit with the gate result.
    raise SystemExit(main())
