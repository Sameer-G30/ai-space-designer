"""Precision@K and NDCG@K for the item score on a fixed-seed synthetic sample."""

# json prints a machine-readable summary.
import json

# random supplies the seeded random-order baseline.
import random

# statistics averages per-query metrics.
import statistics

# The generator supplies must_have, style, and budget ground truth (no gitignored 2000-set).
from spacedesigner.data.synthetic import generate

# Tracked JSONL catalog, no Postgres.
from spacedesigner.optimizer.catalog import load_catalog

# Ranking metrics and the relevance definition.
from spacedesigner.recommend.metrics import ACCEPTABLE_GRADE, ndcg_at_k, precision_at_k, relevance

# Cached CLIP vectors; the model only loads if the cache is missing.
from spacedesigner.recommend.scoring import load_style_scorer, score_item

# Locked input types.
from spacedesigner.schemas import Requirement, SceneGraph

# Fixed seed and sample size for a repeatable check.
SEED = 20260929
# Number of synthetic requirements ranked against the whole catalog.
QUERIES = 200
# Cutoffs reported.
KS = (5, 10)


# Rank the whole catalog for a requirement and return grades in ranked order.
def ranked_grades(catalog, requirement, scene, scorer, weights, order):
    """Return graded relevance in the order given by the scoring function."""
    # Style similarity for this requirement.
    style = scorer.style_scores(requirement.style)
    # Budget is shared across required categories.
    share = requirement.budget_inr / max(1, len(set(requirement.must_have)))
    # Score every row (other categories score zero through the category gate).
    scored = []
    # Loop over catalog rows.
    for item in catalog:
        # Best score over the categories the item could serve.
        total = max(
            score_item(item, c, style[item.item_id], weights, scene.dimensions.length,
                       scene.dimensions.width, share).total
            for c in set(requirement.must_have)
        )
        # Keep the row with a deterministic tie-break.
        scored.append((total, item))
    # Choose ordering: model score, seeded shuffle, or the oracle ceiling.
    if order == "oracle":
        # Best achievable ranking: highest graded relevance first.
        scored.sort(key=lambda p: (-relevance(p[1], requirement), p[1].item_id))
    elif order is None:
        # Descending score, then price and id for determinism.
        scored.sort(key=lambda p: (-p[0], p[1].price, p[1].item_id))
    else:
        # Random baseline.
        order.shuffle(scored)
    # Graded relevance in ranked order.
    return [relevance(item, requirement) for _, item in scored]


# Run the check and print the summary.
def main() -> int:
    """Compute metrics for CLIP scoring, a no-style ablation, and a random baseline."""
    # Generate scenes and gold requirements in memory.
    scenes, requirements = generate(QUERIES, seed=SEED)
    # Validated catalog.
    catalog = load_catalog()
    # Cache-backed scorer.
    scorer = load_style_scorer(catalog, embedder=None)
    # Fall back to loading CLIP only when the cache is absent.
    if scorer.backend.startswith("tag"):
        # Import lazily so the normal path never touches torch.
        from spacedesigner.recommend.embedder import ClipTextEmbedder

        # Build and cache vectors once.
        scorer = load_style_scorer(catalog, embedder=ClipTextEmbedder())
    # Random generator for the baseline.
    rng = random.Random(SEED)
    # Metric accumulators by method name.
    results = {name: {f"{m}@{k}": [] for m in ("precision", "ndcg") for k in KS}
               for name in ("clip_score", "no_style_ablation", "random", "oracle_ceiling")}
    # Evaluate each query.
    for scene_data, req_data in zip(scenes, requirements, strict=True):
        # Validate inputs against the locked schemas.
        scene, req = SceneGraph.model_validate(scene_data), Requirement.model_validate(req_data)
        # The requirement's own weights drive the CLIP score.
        own = req.objective_weights.model_dump()
        # Ablation removes the aesthetics weight.
        no_style = {**own, "aesthetics": 0.0}
        # Ideal grades for NDCG.
        all_grades = [relevance(i, req) for i in catalog]
        # Skip queries with no acceptable item (metrics undefined).
        if max(all_grades) < ACCEPTABLE_GRADE:
            # Next query.
            continue
        # Grades per method.
        for name, weights, order in (
            ("clip_score", own, None),
            ("no_style_ablation", no_style, None),
            ("random", own, rng),
            ("oracle_ceiling", own, "oracle"),
        ):
            # Ranked grade list.
            grades = ranked_grades(catalog, req, scene, scorer, weights, order)
            # Record every cutoff.
            for k in KS:
                # Precision@K.
                results[name][f"precision@{k}"].append(precision_at_k(grades, k))
                # NDCG@K.
                results[name][f"ndcg@{k}"].append(ndcg_at_k(grades, all_grades, k))
    # Average across queries.
    summary = {
        "seed": SEED,
        "queries": QUERIES,
        "catalog_items": len(catalog),
        "style_backend": scorer.backend,
        "acceptable_grade": ACCEPTABLE_GRADE,
        "metrics": {n: {m: round(statistics.mean(v), 4) for m, v in r.items()}
                    for n, r in results.items()},
        "queries_scored": len(results["clip_score"]["precision@5"]),
    }
    # Print the summary.
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Gate: CLIP scoring must beat the random baseline at both cutoffs.
    ok = all(
        summary["metrics"]["clip_score"][m] > summary["metrics"]["random"][m]
        for m in summary["metrics"]["clip_score"]
    )
    # Exit non-zero if it does not.
    return 0 if ok else 1


# Run only when invoked as a script.
if __name__ == "__main__":
    # Exit with the gate result.
    raise SystemExit(main())
