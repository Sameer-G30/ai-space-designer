# Phase 4 recommendation scoring and Stage 2 Pareto report

## Result

Phase 4 adds a deterministic item score and a Stage 2 that turns weight vectors into
different catalog selections, places each selection with the existing Stage 1 CP-SAT model,
and returns one labelled Pareto set per solve. Hard constraints stay inside CP-SAT and are
re-checked by the independent Shapely checker; no design that fails the checker or exceeds
the budget is returned. Infeasible rooms keep the Stage 1 reason and carry no design.

## Item score (`src/spacedesigner/recommend/scoring.py`)

For a catalog row in a missing `must_have` category, all parts are in [0, 1]:

- style: CLIP text similarity between the requested style and the row, min-max normalised
  over the whole catalog;
- budget fit: `1 - price / (budget / number of missing categories)`, zero if above that share;
- space fit: zero if the item cannot fit the room in either orientation, otherwise
  `1 - footprint / (0.30 * floor area)` (0.30 is a project heuristic, `SPACE_SHARE_CAP`);
- function match: 1 for the requested category, 0 otherwise. It is a gate, not a weight;
- sustainability: the existing fixed material lookup (`MATERIAL_SCORES`).

The score is the weighted mean of style, budget fit, space fit and sustainability, using the
objective weights (aesthetics, budget, mean of layout and circulation, sustainability),
multiplied by the gates. Ergonomics is constant per row, so it does not change item ranking.

**Omitted term:** the blueprint names a rating term. The catalog has no ratings and none were
scraped or invented, so the term is omitted.

**Sustainability** is a deterministic material lookup. The catalog has no certification data
and none was invented. Five materials (leather, rattan, and the linen, polyester and cotton
fabrics) are not in the lookup and take Stage 1's neutral default of 0.5.

## CLIP

- Checkpoint: `openai/clip-vit-base-patch32` (pretrained, no fine-tuning), text tower only,
  CPU, 512 dimensions, loaded lazily in a script, never at import time or in a request.
- There are no catalog product photos, so items are embedded from text built from category,
  style tags and material (for example "a bohemian and rustic style armchair made of rattan").
  The query is "a <style> style furniture piece".
- New dependencies (approved): `torch` (CPU wheel from the PyTorch CPU index) and
  `transformers`.
- Vectors for the 382 catalog rows are in the gitignored cache
  `datasets/processed/phase4/clip_text.npz` (so metrics and the API run without Postgres) and
  in the existing `furniture_catalog.embedding` column (382 of 382 rows, 512 dims).
- **RAG embeddings were not written**: `rag_chunks.embedding` is still null (Phase 6).
- If the cache lacks a style, the API falls back to tag overlap and reports
  `style_backend = "tag_overlap_fallback"` instead of claiming CLIP.

## Precision@K and NDCG

Command: `uv run python scripts/eval_recommender.py` (seed 20260929, 200 queries from
`generate()`, whole 382-item catalog ranked per query; 197 queries scored, 3 had no
acceptable item).

Ground truth is derived only from generator fields. Graded relevance of an item:
0 if its category is not in `must_have`; otherwise 1, plus 1 if
`price <= budget / number of must_have categories`, plus 1 if the requested style equals one
of its style tags. An item is *acceptable* at grade 3. NDCG uses gain `2^grade - 1`.
Caveat: the ground truth uses catalog style tags, which are project labels.

| method | P@5 | P@10 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- |
| CLIP item score (K = 5 and 10) | 0.459 | 0.361 | 0.748 | 0.766 |
| same, aesthetics weight zero | 0.236 | 0.235 | 0.590 | 0.650 |
| random order | 0.018 | 0.017 | 0.054 | 0.058 |
| oracle ceiling | 0.901 | 0.712 | 1.000 | 1.000 |

The ceiling is below 1 because many queries have fewer than K acceptable items.

## Weight sweep

27 vectors: the requirement's own weights plus every combination of budget, aesthetics and
sustainability in {0, 0.5, 1} (all-zero excluded) with layout, circulation and ergonomics
fixed at 0.5. Each vector re-scores the catalog, picks the top row per missing category,
repairs over-budget picks by swapping to cheaper rows, and places the result with Stage 1.
The cheapest Stage 1 selection is always a candidate. Identical selections are placed once.
Dominance is judged on the six objective terms (maximise all; the budget term already encodes
cost). The aesthetics term is now the mean normalised CLIP score of the purchased rows.

Labels: cheapest, balanced (best equal-weight mean of the six terms), premium (highest cost
in the front, always within budget), most_sustainable, best_style, best_space,
user_weighted, and `alternative` to top the set up to four points when fewer are labelled.
One point can carry several labels. "Premium" is the costliest non-dominated point that was
found, not the largest possible spend.

## Checks

`uv run python scripts/check_pareto_200.py` (seed 20260930, the Phase 3 rooms):

- 109 feasible, 91 readable infeasible (same split as Phase 3);
- checker violations 0, budget breaches 0, dominated pairs inside returned sets 0;
- points per set: 2 (2 rooms), 3 (5), 4 (55), 5 (36), 6 (10), 7 (1), so 4 to 8 points was
  reached in 102 of 109 sets. In 7 sets fewer than four distinct non-dominated designs
  exist and all of them are returned;
- median sweep time 24 ms, maximum 314 ms.

The Phase 3 gate `scripts/check_optimizer_200.py` is unchanged (0 violations, 0 breaches).

## API and scope

`POST /designs/optimize` now returns `{feasible, points[{labels, design, trace, bom,
solve_time_ms}], candidates_evaluated, dominated_removed, style_backend, solve_time_ms}` or
the infeasible reason. Each point is persisted with the existing tables. `GET /health` and
`POST /scenes` are unchanged. Stage 1 `optimize()` gained optional `selection`, `variant` and
`term_overrides` arguments; its default behaviour is unchanged.

Not done: 3D-FRONT and 3D-FUTURE were not used; no rating term; no image embeddings, no
CLIP fine-tuning; no NL parser, RAG retrieval, bge embeddings, frontend, CORS, migration,
explanations, or design versions.
