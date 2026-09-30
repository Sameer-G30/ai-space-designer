# Phase 8: explanations, counterfactuals, and versions

Numbers below are from one run of `uv run python scripts/eval_explanations.py` on this machine. The script does not download weights and does not pull a model. Faithfulness uses the local `qwen2.5:7b` already served by Ollama. If that daemon is down, the script still prints the latency and diff lines and then `faithfulness not_run ollama_down`.

## What the routes do

`GET /designs/{id}/explanation` rebuilds the optimizer trace by replaying Stage 1 on the stored design (same catalog rows, same weights, same aesthetics override Stage 2 wrote). The trace is not a database column, and no migration was added. A template turns that trace into sentences: cost, score, each binding constraint, each objective term, and the rejected-item count. A what-if design also gets one sentence for score change per rupee when that number was stored on its version diff.

`qwen2.5:7b` is asked only to rephrase those sentences, one per fact, copying every number. The prompt does not include the raw trace. If Ollama does not answer, or the reply is not a `sentences` array, the template itself is stored. Each sentence is checked and the boolean is written to `explanations.verified`.

The checker accepts a sentence only when every number in it matches a number in the templated facts (tolerance `1e-6` times `max(1, |fact number|)`) and every domain word it uses already appears in those facts. The domain words are budget, clearance, circulation, ergonomics, accessibility, turning, margin, sustainability, aesthetics, layout, rejected, cost, score, occupant, door, window, and catalog. A sentence with neither a number nor one of those words is not verified.

`POST /designs/{id}/counterfactual` accepts `budget_inr`, `length_m`, `width_m`, `height_m`, and `occupant_count`. At least one is required. The current catalog rows are kept when they still fit the budget; otherwise cheaper rows of the same categories are substituted. CP-SAT receives `add_hint` for each purchased item that is still selected (start cell, start cell, rotation bit, and both sizes). `repair_hint` is set only on that path. The no-hint solve used by `POST /designs/optimize` is unchanged. Sensitivity is `(new score − old score) / (new budget − old budget)` when the budget changes, and null otherwise. Occupant count is stored on the new requirement. Stage 1 does not constrain it, so an occupant-only what-if does not move furniture. A room-size change is saved as a new scene id so the parent design's scene is not overwritten.

`GET /designs/{id}/versions` reads `design_versions`. The first read of a design inserts version 1, a snapshot whose diff lists every object as added and whose cost and score changes are 0. A what-if appends the next version on the parent design and version 1 on the new design. Both diffs have `items_added`, `items_removed`, `items_moved`, `cost_change`, and `score_change`. Rows are not updated.

`POST /requirements`, `POST /designs/optimize`, `POST /scenes`, and `POST /scenes/photo` were not changed. Named clearance constants, the taxonomy, and the locked Pydantic schemas were not changed. Alembic head is still `c550d1f16744`.

## Counterfactual latency and version diffs

Eight fixed rooms, real catalog, Stage 1 only (no Pareto sweep and no CLIP). Each room asks for a desk, a chair, and a shelf. The what-if raises the budget by 10 percent. Cold is the same model with no hints. Warm passes the three previous poses. `diffs_ok` checks that added and removed ids match the set difference, that moved ids exist on both sides, and that the cost and score deltas match the two designs.

| | value |
| --- | ---: |
| rooms | 8 |
| median full re-run (`solve_time_ms`) | 5.332 |
| median warm start (`solve_time_ms`) | 6.040 |
| hints on each warm start | 3 |
| diffs correct | 8 of 8 |

Warm start was slower on this fixture. These placements already finish in about 5 ms, and attaching hints adds overhead. The check is a latency measurement, not a claim that hints are faster here.

Per room, cold then warm, in milliseconds: 4.800 / 5.628, 5.130 / 5.755, 5.714 / 5.856, 4.810 / 5.839, 5.963 / 6.296, 5.426 / 6.223, 5.630 / 6.778, 5.237 / 6.588.

## Faithfulness

Same eight Stage 1 designs. Temperature 0. Grounded: the product prompt, facts only. Ungrounded: room type and the three category names, no fact list and no optimizer numbers, asking for budget, clearances, and costs. Both replies are sentence lists checked against the same facts.

| prompt | designs with model sentences | claims | verified rate |
| --- | ---: | ---: | ---: |
| trace-grounded | 8 | 96 | 1.0 |
| no trace access | 8 | 16 | 0.5 |

96 grounded claims is 12 sentences on each design (cost, score, three binding constraints, six objective terms, rejected-item count), and every one verified. The ungrounded side returned 16 sentences, 8 of which verified. A number-free sentence that only uses domain words already present in the facts can verify, so the ungrounded rate is not zero. Sentences that introduce a number the facts do not contain do not verify.

## Other checks

- `uv run ruff check .` clean.
- `uv run pytest`: 130 passed, 1 skipped, plus the known Starlette `httpx` versus `httpx2` warning. The skipped test is the existing face-blur test that needs OpenCV in `.venv-train`.
- `uv run python scripts/verify_datasets.py` exited 0 with `phase1_complete`.
- `uv run python scripts/check_optimizer_200.py` exited 0: seed 20260930, 109 feasible, 91 infeasible, 0 checker violations, 0 budget breaches.

## Repeat

```bash
uv run ruff check .
uv run pytest
uv run python scripts/verify_datasets.py
uv run python scripts/check_optimizer_200.py
uv run python scripts/eval_explanations.py
```

From `frontend/`: `npm run lint` and `npm run build`.

The page: start Postgres, then `uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`, and `npm run dev` in `frontend/`. Open http://localhost:3000, solve, choose Explain this design, run one what-if, and choose Compare versions. The default what-if budget is 10 percent above the solved budget.

## Page walkthrough

On the default room (6 m by 6 m home office, desk and chair, budget INR 80000) the solve returned 5 Pareto points. Explain this design showed the sources, including `design.cost` INR 7200.00, and rephrased claims with verified rate 1.000. The what-if budget was the prefilled 88000. It warm-started with 2 hints, changed the score by 0.001364, changed the cost by 0, and reported score change per rupee `1.705e-7`. Added, removed, and moved were all none. Compare versions showed version 1 (the two catalog objects added, zero deltas) and version 2 (no object changes, score change 0.001364). The page did not overflow at 905 px or at 390 px. The wide bill and version tables scroll inside their own boxes.
