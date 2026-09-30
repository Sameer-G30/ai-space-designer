# Phase 6 requirement parser and RAG

## Result

`POST /requirements` sends a sentence to local Ollama `qwen2.5:7b` over HTTP. The model is not loaded inside the API process. The reply is JSON for the locked `Requirement` fields. `scene_id` and `raw_text` are copied from the request. The reply is checked against the 23 catalog classes, the nine generator style words, and the Pydantic schema. One retry is allowed. A failure is HTTP 422 with a readable detail and no requirement.

The same response retrieves standards. The existing 876 `rag_chunks` rows were embedded with `bge-small-en-v1.5` (384 dimensions, CPU) into `rag_chunks.embedding`. `furniture_catalog.embedding` was left as the 382 CLIP vectors of 512 dimensions. Retrieval is pgvector cosine distance plus Postgres full-text search, fused by reciprocal rank, then reranked with `bge-reranker-base` on CPU over the top 20. The response returns up to 12 numbers with name, metres, source, page, and topic. Chunk prose is not returned. The named solver constants are copied beside the parse and were not edited: grid 0.05 m, low-confidence margin 0.10 m, circulation 0.915 m, door clear width 0.815 m, turning space 1.525 m.

No schema change, no migration, no explanations rows, and no design-version rows.

## Parser accuracy

`uv run python scripts/eval_requirement_parser.py` on the first 100 records from `generate(100, seed=20260930)`. The gold text and the schema were not changed. Identity fields (`requirement_id`, `scene_id`, `raw_text`) are copied, not scored. The 12 scored fields are budget, must-have, must-keep ids, occupants, style, accessibility, and each of the six weights.

- Schema-valid rate after the retry budget: 1.000 (100 of 100). Schema-invalid: 0.
- Field-level accuracy: 0.470833 (565 of 1200 field comparisons).
- The generator does not put objective weights in the sentence. The parser sets each weight to 1 when the sentence is silent. Gold weights are random, so those six fields are almost all misses: layout 0.01, circulation 0.02, and the other four 0.00.
- On the six fields the sentence does state, the rate is 0.936667. Budget 1.00, must-have 0.97, must-keep ids 0.65, occupants 1.00, style 1.00, accessibility 1.00.
- Must-keep is lower because the sentence names object types, and the gold ids are the objects flagged keep. Two objects of one type are ambiguous.

The run took about 261 seconds with `qwen2.5:7b` already loaded.

## Recall@5

Thirty original questions are in `datasets/metadata/rag/retrieval_questions.json`. They name chunk ids. They do not store passages. A question hits when any labelled chunk is in the top 5 after the rerank.

- Recall@5: 0.966667 (29 of 30).
- The miss is q04, the clear-floor-space question. Neither labelled chunk was in the top 5.
- Of the 26 questions that also label a PDF chunk, 24 had that PDF chunk in the top 5 (0.923077). q24 hit through the project summary and missed its labelled MoHUA chunk.

## Walkthrough

Servers: this project's Postgres, `uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` with `DATABASE_URL` exported from `.env`, and `npm run dev` in `frontend/`. Opened http://localhost:3000. The browser called Next.js only.

- Health line: `API status: ok (HTTP 200)`.
- Before `qwen2.5:7b` was installed, parsing a sentence showed `Ollama did not answer for qwen2.5:7b: Not Found`. Budget stayed 10000 and style stayed rustic. No "Parsed" line.
- After the model was installed: the form was set to budget 15000, occupants 4, style rustic, and desk unchecked. The sentence was "I want to redo my home office in a scandinavian style. I need a desk and a chair. The budget is 80000 rupees for 1 person." Parse filled budget 80000, occupants 1, style scandinavian, and checked desk and chair. The page said the fields came from the sentence. Retrieved numbers listed metres with source, page, and topic, including the ADA summary and a MoHUA page number. No passage was shown. The solver-constants line still showed 0.915 m, 0.815 m, and 1.525 m.
- Occupants were then edited to 2 and the room was solved. Result: 4 points, `style_backend` `openai/clip-vit-base-patch32`, 0 dominated removed. A plan was drawn.
- On the default home office, a feasible solve returned 5 points. Clicking `premium, best_space` changed the selected design. Budget 100 returned `No design` and `minimum selected catalog cost INR 7200.00 exceeds budget INR 100.00`, with no plan. Door width 0.5 m returned `No design` and `door openings below 0.815 m: [0]`, with no plan.
- At 390 px wide the page did not overflow horizontally. The sentence field was 358 px wide inside the 390 px viewport.

The duplicate-object HTTP 422 path was not repeated this phase.

## Checks

- `uv run ruff check .`
- `uv run pytest`: 89 passed, one known StarletteDeprecationWarning
- `uv run python scripts/verify_datasets.py`: `phase1_complete`
- `uv run python scripts/check_optimizer_200.py`: 109 feasible, 91 infeasible, 0 checker violations, 0 budget breaches. Median on this machine was 3.601 ms. The gate was not retuned.
- `uv run python scripts/check_pareto_200.py`: the same 109 and 91, 0 dominated pairs
- `uv run python scripts/embed_rag_chunks.py`: 876 chunk vectors, dimension 384. Catalog stayed 382 vectors, dimension 512.
- `uv run python scripts/eval_requirement_parser.py` and `uv run python scripts/eval_rag_recall.py`: the rates above
- From `frontend/`: `npm run lint` and `npm run build`

## Not done

Retrieved numbers do not replace the solver constants. Phase 7 training was not started. The catalog was not rebuilt, CLIP was not downloaded, and the PDFs were not re-chunked. 3D-FRONT and 3D-FUTURE were not used.
