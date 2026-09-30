# PhotoSpace

PhotoSpace is a photo-grounded interior redesign project. Phase 0 is the shared schemas, Postgres tables, FastAPI health check, and the Next.js page that displays that check. Phase 1 acquires the public datasets used later for cleaning, training, and geometry checks. Phase 2a cleans the computer-vision datasets and writes a data quality report. Phase 2b mines layout priors, builds the furniture catalog, cleans the Objaverse meshes, chunks the RAG corpus, and adds a synthetic room generator. Phase 3 adds the hard-constrained Stage 1 layout optimizer, independent checker, plan rendering, BOM, trace, and manual-scene optimization API. Phase 4 scores catalog rows and returns one Pareto set. Phase 5 is the Next.js page for that set. Phase 6 parses a sentence into a requirement and retrieves standards with hybrid search. Phase 7a trains the room classifier and detector. Phase 7b turns a photo into a scene graph. Phase 8 explains a design from the optimizer trace, re-solves a what-if from the previous placement, and stores version diffs.

This README is updated at the end of every phase with what changed and how to check it. See the "Phase log" section at the bottom.

Dataset bytes stay on disk under `datasets/raw/` and are not committed. The file list, licenses, and checksums are in `docs/DATASETS.md`, `docs/LICENSES.md`, and `datasets/metadata/`.

## Setup

Python 3.11.9, uv, Docker, and Node.js are required.

```bash
cp .env.example .env
uv sync --all-groups
docker compose up -d
uv run alembic upgrade head
```

## Run

API, on port 8001:

```bash
uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001
```

Frontend, from `frontend/`:

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The page reads `API_URL` on the server and shows the `/health` response. The room form posts to Next.js route handlers, which call the API. The browser does not call port 8001.

## Tests

```bash
uv run pytest
uv run ruff check .
uv run python scripts/verify_datasets.py
```

## Phase 1 datasets

These archives are on disk and recorded in `datasets/metadata/acquisition_log.json`:

- NYU Depth V2 labeled set and the official `splits.mat`. The raw 428 GB capture was not taken.
- SUN RGB-D images, toolbox, and updated 2D boxes. The separate updated 3D-box file was not taken.
- Places365-Standard 256×256 validation set only.
- CubiCasa5K, the full Zenodo zip. Zenodo lists CC BY-NC-SA 4.0, which adds ShareAlike to the CC BY-NC 4.0 name in the blueprint.
- Objaverse, 160 furniture GLBs, with each asset license in `datasets/metadata/objaverse_asset_licenses.jsonl`.
- Structured3D structure annotations and 3D bounding boxes.
- 2010 ADA Standards and the MoHUA Harmonised Guidelines 2021, plus short cited summaries in `datasets/metadata/rag/`.

Not taken:

- Places365 256×256 train archive (about 24 GB). The MIT host was too slow, and the terms forbid redistributing the images, so there is no torrent. The official file remains `train_256_places365standard.tar`.
- Structured3D perspective parts `00` and `01` (about 12 GB and 13 GB). The terms forbid reuploading, so the Azure links in `docs/DATASETS.md` are the allowed source. Panorama zips, empty-room zips, and parts `02`–`17` were never part of this phase.
- 3D-FRONT and 3D-FUTURE. Deferred. The optimizer does not need them. Layout priors and the furniture catalog will use the data that is already on disk.
- FurniScene. Skipped. The paper still says the dataset will be public soon, and no download was found.
- NYU raw video, Places365 high-resolution and challenge sets, and the rest of Objaverse. Those were out of scope for this phase.

## Phase log

Each entry says what the phase changed and how to check it.

### Phase 0: foundation

- Changed: Pydantic schemas, Alembic tables, FastAPI `/health`, Next.js status page.
- Check: `uv run pytest`, then the API and frontend steps under "Run".

### Phase 1: dataset acquisition

- Changed: download scripts, `docs/DATASETS.md`, `docs/LICENSES.md`, checksums and license logs in `datasets/metadata/`.
- Check: `uv run python scripts/verify_datasets.py` prints `phase1_complete` and exits 0.

### Phase 2a: cleaning the CV datasets

- Changed:
  - `src/spacedesigner/data/taxonomy.py`: 26 furniture classes, 15 room types, and synonym maps grounded in SUN RGB-D and NYU labels.
  - One cleaner per dataset in `src/spacedesigner/data/`, run through `scripts/clean_*.py`. They write to `datasets/processed/` (gitignored).
  - NYU Depth V2: PNG images, masked depth `.npy`, and label maps, using the official split.
  - SUN RGB-D: YOLO labels, a sensor and scene stratified split, and depth plus 3D layout for the test images.
  - Room-type set: Places365 val images plus SUN RGB-D scene labels.
  - CubiCasa5K: wall, door, window, and room polygons and masks.
  - Structured3D: room, plane, and dimension tables from the annotation and bbox zips only.
  - Two small Places365 label files were added (`scripts/download_places365_labels.py`) because `val_256.tar` has images only.
  - Summaries in `datasets/metadata/cleaning/` and the report `docs/reports/data_quality_cv.md`.
- Not cleaned, because the bytes are not on disk: the Places365 train archive (no Places train split) and the Structured3D perspective images (no photo or depth checks in Phase 7b).
- Check:
  - `uv run pytest tests/data` runs the rules and validation tests. The checks on exported data skip if `datasets/processed/` does not exist.
  - `uv run ruff check .` and `uv run python scripts/verify_datasets.py`.
  - Rebuild the exports with `uv run python scripts/clean_sun_rgbd.py`, `clean_nyu.py`, `clean_places.py` (after SUN), `clean_cubicasa.py`, `clean_structured3d.py`, then `clean_report.py`.
  - Read `docs/reports/data_quality_cv.md` for counts, class histograms, and dropped-record reasons.

### Phase 2b: layout, catalog, 3D, knowledge, and synthetic data

- Changed:
  - Layout priors from data on disk, with a minimum sample count on every prior: SUN RGB-D 3D boxes (sizes, co-occurrence, centre-to-wall distance), Structured3D room sizes, and dimensionless CubiCasa5K room shapes. Output: `datasets/metadata/cleaning/layout_priors.json`.
  - Objaverse: the 160 acquired GLBs loaded with trimesh, up axis and scale normalized, textures capped at 1024 px, mapped to the 26 taxonomy classes. Output: `datasets/processed/objaverse/` (gitignored).
  - Furniture catalog: 382 items, loaded into `furniture_catalog`, also in `datasets/metadata/cleaning/furniture_catalog.jsonl`. Dimensions are measured (SUN RGB-D and Objaverse proportions). Style tags and materials are project labels. **Prices are synthetic INR, not scraped.** `embedding` is null.
  - RAG corpus: the ADA and MoHUA PDFs plus the cited summaries, chunked by section with source, page, and topic, 876 rows in `rag_chunks`. `embedding` is null. The MoHUA text is stored for retrieval only.
  - Synthetic generator v1: 2000 rooms with matching requirement text and gold JSON, under `datasets/raw/synthetic/` (gitignored), validated against the locked schemas.
  - New dependencies: `trimesh` (MIT) and `pypdf` (BSD-3-Clause).
- Not built, because the bytes are not on disk: ATISS-style 3D-FRONT house flattening and 3D-FUTURE style, material, and dimension labels. Kitchen, bathroom, and other room types have too few 3D-annotated SUN RGB-D rooms for co-occurrence priors, and Structured3D boxes carry no class labels.
- Check:
  - `uv run ruff check .`, `uv run pytest`, and `uv run python scripts/verify_datasets.py`.
  - `docker compose up -d && uv run alembic upgrade head`, then `uv run python scripts/load_layout_db.py --counts` prints 382 catalog rows and 876 chunk rows, with the same number of null embeddings.
  - Rebuild in order: `scripts/mine_layout_priors.py`, `clean_objaverse.py`, `build_catalog.py`, `chunk_rag.py`, `generate_synthetic.py`, `load_layout_db.py`, `layout_report.py`.
  - Read `docs/reports/data_quality_layout.md` for counts, drop reasons, omitted priors, and what 3D-FRONT and 3D-FUTURE would have provided.

### Phase 3: Stage 1 optimizer

- Changed:
  - OR-Tools CP-SAT placement on a 0.05 m grid with 0°/90° new-item rotation, fixed must-keep poses, no overlap, opening approach and circulation clearance, budget, required categories, low-confidence inset, and accessible turning-space constraints.
  - Independent Shapely auditing, deterministic BOM aggregation, complete `OptimizerTrace`, and exact-coordinate PNG/SVG plan rendering.
  - `POST /scenes` for validated manual scene graphs and `POST /designs/optimize` for a scene id plus gold `Requirement`; `GET /health` is unchanged.
  - The tracked JSONL remains the solver source of truth. The 200-room check is database-independent; API persistence uses the existing tables without a migration.
  - Fixed-seed gate: 109 feasible and 91 readable infeasible outcomes, 0 checker violations, 0 budget breaches, and 4.141 ms median solve time.
  - New dependencies: `ortools` (Apache-2.0) and `shapely` (BSD-3-Clause).
- Not built: Phase 4 recommendation scoring, embeddings, CLIP, Pareto/NSGA-II, natural-language parsing, RAG retrieval, frontend pages, 3D views, explanations, or version writes. 3D-FRONT and 3D-FUTURE were not used.
- Check:
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `uv run pytest tests/api/test_phase3_routes.py` exercises both new routes with `TestClient`.
  - Read `docs/reports/optimizer_stage1.md` for gate counts, constants, infeasibility handling, and scope limitations.

### Phase 4: recommendation scoring and Stage 2 Pareto set

- Changed:
  - `src/spacedesigner/recommend/`: CLIP (`openai/clip-vit-base-patch32`, text tower, CPU, lazy) style similarity plus budget fit, space fit, category gate and the fixed material sustainability lookup. No rating term (the catalog has no ratings).
  - `src/spacedesigner/optimizer/stage2_pareto.py`: a 27-vector weight sweep selects catalog items, Stage 1 CP-SAT places them, dominated designs are dropped, and 4–8 points are labelled (cheapest, balanced, premium, most_sustainable and others).
  - `POST /designs/optimize` now returns that Pareto set (design, trace, and BOM per point) or a readable infeasible reason.
  - Catalog vectors: gitignored cache `datasets/processed/phase4/clip_text.npz` and `furniture_catalog.embedding` (382 rows). `rag_chunks.embedding` stays null.
  - New dependencies: `torch` (CPU wheel) and `transformers`. The CLIP weights were downloaded once with approval.
- Not built: Phase 5 frontend, NL parser, RAG retrieval, migrations. 3D-FRONT and 3D-FUTURE were not used.
- Check:
  - `uv run ruff check .` and `uv run pytest` (76 passed, one known Starlette warning).
  - `uv run python scripts/verify_datasets.py` and `uv run python scripts/check_optimizer_200.py` (unchanged).
  - `uv run python scripts/check_pareto_200.py`: 109 feasible, 91 infeasible, 0 violations, 0 breaches, 0 dominated pairs.
  - `uv run python scripts/eval_recommender.py`: Precision@5/10 and NDCG@5/10 against the synthetic ground truth.
  - `uv run pytest tests/optimizer/test_stage2.py tests/api/test_phase3_routes.py` covers non-dominance and the route via `TestClient`.
  - Rebuild vectors with `uv run python scripts/build_catalog_embeddings.py` (add `--write-db` with the database up and `DATABASE_URL` exported).
  - Read `docs/reports/optimizer_stage2.md`.

### Phase 5: Next.js v1

- Changed:
  - Room form: scene id, one of the 15 room types, length, width, height, confidence, optional doors and windows, optional kept objects. Posts a `SceneGraph` to `/scenes`.
  - Structured requirement form: budget in INR, one or more of the 23 catalog classes, must-keep ids from the objects marked keep, occupant count, one of the nine generator styles, accessibility, and all six weights. `raw_text` stays empty. There is no sentence box.
  - Pareto scatter of cost and score. Clicking a point selects that design for the 2D plan, the BOM, and the React Three Fiber box view. One to eight points are drawn. An infeasible reason is shown with no design. HTTP 404 and 422 show the status and detail.
  - The browser stays on port 3000. Next.js route handlers call FastAPI with `API_URL`. No CORS and no new FastAPI route.
  - Prices are labelled synthetic INR. `style_backend` is shown as returned. Sustainability is labelled as a material lookup, including the five materials that score 0.5.
  - New npm packages: `three`, `@react-three/fiber`, and `@types/three` (three 0.186 publishes no TypeScript declarations).
  - Report: `docs/reports/frontend_v1.md`.
- Not built: natural-language parsing, Ollama, RAG embeddings, migrations, explanations, design versions, GLB furniture, a chart library. 3D-FRONT and 3D-FUTURE were not used.
- Check:
  - `uv run ruff check .`
  - `uv run pytest`
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - From `frontend/`: `npm install`, `npm run lint`, `npm run build`.
  - Start the API with `uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`, and start the page with `npm run dev` in `frontend/`.
  - Open http://localhost:3000. Confirm `API status: ok (HTTP 200)`.
  - Leave the default home office (6 m by 6 m, south door width 0.9 m, budget 80000, desk and chair) and choose Save room and solve. Confirm a Pareto set, then click another point and confirm the plan, the BOM total, and the box view follow it.
  - Set the budget to 100 and solve again. Confirm the cost reason and that no plan is drawn.
  - Set the door width to 0.5 m, restore the budget, and solve. Confirm the narrow-door reason and that no plan is drawn.
  - Add two kept objects with the same id and solve. Confirm HTTP 422 and that no plan is drawn.
  - Read `docs/reports/frontend_v1.md`.

### Phase 6: requirement parser and RAG

- Changed:
  - `POST /requirements` calls local Ollama `qwen2.5:7b` over HTTP, validates the locked `Requirement` shape, and retries once. `scene_id` is the scene being edited. `raw_text` is the sentence. `must_have` is limited to the 23 catalog classes. `style` is limited to the nine generator words. All six weights are required. A failed parse is HTTP 422 and does not invent a requirement.
  - The 876 existing `rag_chunks` rows now have `bge-small-en-v1.5` vectors (384 dimensions) in `rag_chunks.embedding`. Hybrid retrieval is pgvector cosine distance plus Postgres full-text search, then `bge-reranker-base` on the top 20. Both models run on CPU. `furniture_catalog.embedding` is still the 382 CLIP vectors of 512 dimensions.
  - The parse response includes retrieved numbers with source, page, and topic, and a copy of the named solver constants. Those constants were not changed. Chunk prose is not returned. MoHUA text is not quoted in the UI or the report.
  - The Next.js page has a sentence box. It posts to `/api/requirements`, which calls FastAPI with `API_URL`. A successful parse fills the structured fields. Those fields stay editable. A failed parse shows the error and leaves the fields alone. The browser still does not call port 8001. No CORS.
  - Report: `docs/reports/requirements_rag.md`.
- Not built: Phase 7 training, SAM2, Depth Anything, YOLO, a schema change, a migration, explanation rows, design versions, and any edit to the optimizer constants. 3D-FRONT and 3D-FUTURE were not used. Retrieved clearances are recorded beside the parse and do not replace the solver.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (89 passed, one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `uv run python scripts/check_pareto_200.py`
  - With `DATABASE_URL` exported from `.env` and Postgres up: `uv run python scripts/embed_rag_chunks.py` (876 vectors, dimension 384; catalog dimension stays 512).
  - With Ollama serving `qwen2.5:7b`: `uv run python scripts/eval_requirement_parser.py` (schema-valid rate and field-level accuracy on 100 gold requirements, seed 20260930).
  - `uv run python scripts/eval_rag_recall.py` (Recall@5 on the 30 questions in `datasets/metadata/rag/retrieval_questions.json`).
  - From `frontend/`: `npm run lint` and `npm run build`.
  - Start the API with `uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`, and start the page with `npm run dev` in `frontend/`.
  - Open http://localhost:3000. Confirm `API status: ok (HTTP 200)`.
  - Type a room sentence and choose Parse sentence. Confirm the structured fields fill, and that source, page, and topic are shown for retrieved numbers without a copied passage. Edit one field, then choose Save room and solve. Confirm a Pareto set or a readable infeasible reason.
  - Set the budget to 100 and solve. Confirm the cost reason and that no plan is drawn.
  - Set the door width to 0.5 m, restore the budget, and solve. Confirm the narrow-door reason and that no plan is drawn.
  - Click another Pareto point and confirm the plan follows it.
  - Read `docs/reports/requirements_rag.md`.

### Phase 7a: training the CV models

- Changed:
  - `src/spacedesigner/training/` holds the classifier and detector code. Scripts: `train_room_classifier.py`, `eval_room_classifier.py`, `train_detector.py`, `eval_detector.py`.
  - Room classifier: timm ConvNeXt-Tiny fine-tuned on the Phase 2a room-type export. Test top-1 is 0.749 on 331 images.
  - Detector: YOLO-World-S fine-tuned on SUN RGB-D with the 26 locked classes, 640 px, batch 8, mixed precision, 3.2 GB peak VRAM. Test mAP50 is 0.558 and mAP50-95 is 0.434, against 0.343 and 0.260 zero-shot.
  - Training runs in a separate `.venv-train` (CUDA torch, timm, ultralytics; see `requirements-train.txt`). The main `.venv` keeps CPU torch. Weights are in `models/` and are gitignored.
  - Report: `docs/reports/cv_training.md`.
- Not built: Phase 7b, YOLO-World-M, a Places365 train download, any frontend, schema, or API change.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (93 passed, one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `.venv-train/bin/python scripts/eval_room_classifier.py --split test` (top-1 and confusion matrix).
  - `.venv-train/bin/python scripts/eval_detector.py` (mAP50 and mAP50-95, zero-shot and fine-tuned, on the test split).
  - Read `docs/reports/cv_training.md`.

### Phase 7b: photo to scene graph

- Changed:
  - `src/spacedesigner/perception/` now holds the photo pipeline: privacy pass (EXIF and GPS stripped in the API, faces blurred first in the worker), room classifier, detector, SAM2.1 Hiera-Tiny masks, Depth Anything V2 Small metric-indoor depth, RANSAC floor, ceiling, and wall fits, and scene assembly. The GPU stages run in a child process in `.venv-train`, one model at a time (largest stage 517 MiB). The main `.venv` is unchanged and still has CPU torch.
  - `POST /scenes/photo?scene_id=..&known_length_m=..&known_axis=..` (raw image body) under the existing `/scenes` prefix. A typed length gives `high` confidence; otherwise the metric depth gives `low`, and the existing 0.10 m low-confidence inset applies. A confidence is returned for each dimension. The scene is saved with the existing versioning (repeat uploads add 1). `POST /scenes`, `/requirements`, and `/designs/optimize` are unchanged.
  - The Next.js page has a photo upload, an optional known length and which dimension it is, and fills the room fields so they can be corrected before solving. The corrected room is saved as the next version.
  - Approved downloads: SAM2.1 Hiera-Tiny, Depth Anything V2 Metric-Indoor-Small, and the 230 KB YuNet face model (gitignored under `models/pretrained/`). `transformers` was added to `.venv-train` only.
  - Report: `docs/reports/photo_to_scene.md`. Depth AbsRel 0.213 (0.074 after median scaling) on NYU test; segmentation mean IoU 0.347 on 64 frames; room-dimension errors on 473 SUN RGB-D layouts are in the report.
- Not built or not run: Structured3D room-dimension check (the perspective bytes are not on disk), Phase 8, a Qwen critic, inpainting, a 3D view. No schema change and no migration.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (115 passed, 1 skipped; the skipped face-blur test needs OpenCV and runs only in `.venv-train`; one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `.venv-train/bin/python scripts/eval_photo_to_scene.py depth` (NYU test AbsRel, RMSE, delta1)
  - `.venv-train/bin/python scripts/eval_photo_to_scene.py seg`
  - `.venv-train/bin/python scripts/eval_photo_to_scene.py dims` (SUN RGB-D room-dimension error in cm, with and without one measurement)
  - From `frontend/`: `npm run lint` and `npm run build`.
  - Start Postgres (`docker compose up -d`), the API (`uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`), and `npm run dev` in `frontend/`. Open http://localhost:3000, choose a photo, optionally type a known length, choose Estimate room from photo, correct a number, then Save room and solve. Try a 390 px wide window too.
  - Read `docs/reports/photo_to_scene.md`.

### Phase 8: explanations, counterfactuals, and versions

- Changed:
  - `src/spacedesigner/explain/` fills the empty package. A template is built from the optimizer trace (cost, score, binding constraints, objective terms, rejected-item count). `qwen2.5:7b` only rephrases those sentences over HTTP. Each sentence is checked against the facts and stored in `explanations.verified`. If Ollama is down, the template is stored and marked verified. The trace is replayed from the stored design. No new column and no migration. Alembic head is still `c550d1f16744`.
  - `POST /designs/{id}/counterfactual` warm-starts CP-SAT with hints from the previous placement. Sensitivity is the score change divided by the budget change when the budget changes. A room-size change is saved under a new scene id. `GET /designs/{id}/versions` reads the existing `design_versions` table: version 1 is a snapshot, and a what-if appends a diff (items added, removed, moved; cost change; score change). `GET /designs/{id}/explanation` returns the facts and the claims.
  - `POST /requirements`, `POST /designs/optimize`, `POST /scenes`, and `POST /scenes/photo` are unchanged. Named clearance constants are unchanged.
  - The Next.js page keeps the existing solve flow and adds an explanation with sources, a what-if control (the budget field starts at 10 percent above the solved budget), and a version comparison. On the default room the walkthrough solved 5 points, showed verified sources, ran the prefilled 88000 budget what-if (2 hints, score change 0.001364, no item changes), and compared versions 1 and 2. The page did not overflow at desktop width or at 390 px.
  - Report: `docs/reports/explanations.md`. On 8 fixed rooms the median full re-solve was 5.332 ms and the median warm start was 6.040 ms (hints did not speed up these ~5 ms solves). All 8 version diffs matched. Trace-grounded explanations verified 96 of 96 claims (rate 1.0). Explanations with no trace access verified 8 of 16 claims (rate 0.5). `qwen2.5:7b`, temperature 0.
- Not built: Phase 9 (3D assets, inpainting, ControlNet, a Qwen critic), a schema change, a migration, a CLIP fine-tune, and any edit to the parser, the retriever, the recommender, the photo pipeline, or the named clearance constants.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (130 passed, 1 skipped; the skipped face-blur test needs OpenCV and runs only in `.venv-train`; one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `uv run python scripts/eval_explanations.py` (latency, diff check, and faithfulness; prints `faithfulness not_run ollama_down` when Ollama is down).
  - From `frontend/`: `npm run lint` and `npm run build`.
  - Start Postgres (`docker compose up -d`), the API (`uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`), and `npm run dev` in `frontend/`. Open http://localhost:3000. Solve the default room. Choose Explain this design and read the sources. Run one what-if. Choose Compare versions. Try a narrow window too.
  - Read `docs/reports/explanations.md`.

### Phase 9: visualization and the design critic

- Changed:
  - The 3D view places a cleaned Objaverse GLB when the catalog item has one, on the same solver coordinates (floor x is world X, floor y is world Z, height is world Y). Items without a cleaned mesh stay boxes. The mesh route is `GET /api/meshes/{itemId}` and reads `datasets/processed/objaverse/`. It does not add a second 3D engine.
  - `POST /designs/{id}/visualize` renders a depth map and a segmentation map from the scene graph, builds an inpaint mask for the objects the optimizer added or moved, and pixel-locks everything else. The Stable Diffusion 1.5 plus ControlNet-depth worker is in `.venv-train` and refuses to download (`local_files_only`). The saved detector can re-check the generated image and ask for another seed. `qwen2.5vl:7b` is advisory only. Disagreements with the Shapely checker are logged and do not change the design. No new column and no migration.
  - The page keeps the sentence box, photo upload, Pareto set, plan, bill of materials, explanations, what-if, and versions. It adds the mesh-or-box caption and a Render this design control. On the default room, the cheapest point stayed boxes and the best-style point showed an Objaverse mesh for the chair and a box for the desk. Render returned the depth and segmentation maps and a note that diffusion weights are not installed. The page did not overflow at desktop width or at 390 px.
  - Report: `docs/reports/visualization_critic.md`. Mask-lock SSIM on 4 scene-graph renders (128 px) was 1.0, with at least 2071 editable pixels in each image. On one 512 px Stable Diffusion image the locked-region SSIM was 1.0, the detector consistency rate was 0 of 1 (one extra detection after 2 seeds), the critic wrote 3 disagreement lines and did not change the design, and the sampled GPU peak was 6647 MiB (worker peak 3409.3 MiB).
- Not built: a second ControlNet on the segmentation map, a schema change, a migration, a CLIP fine-tune, and any edit to the parser, the retriever, the recommender, the photo pipeline, the optimizer, the explanations, or the named clearance constants. Phase 10 was not started.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (143 passed, 1 skipped; the skipped face-blur test needs OpenCV and runs only in `.venv-train`; one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - `uv run python scripts/eval_visualization.py` (mask-lock SSIM, then one live image when the fp16 weights and `qwen2.5vl:7b` are installed).
  - From `frontend/`: `npm run lint` and `npm run build`.
  - Start Postgres (`docker compose up -d`), the API (`uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` after exporting `DATABASE_URL` from `.env`), and `npm run dev` in `frontend/`. Open http://localhost:3000. Solve the default room. Confirm a mesh where the catalog item has a cleaned GLB and a box where it does not. Choose Render this design and read the image or the reason it was not generated. Try a narrow window too.
  - Read `docs/reports/visualization_critic.md`.

### Phase 10: full page flow

- Changed:
  - The existing page is unchanged. Playwright, beside the Next.js app, drives that page through one flow: a SUN RGB-D test photo when the perception weights are on disk, a corrected room width, a parsed sentence, the Pareto set, the 2D plan, the 3D mesh-or-box view, Render this design (depth, segmentation, and either an image or the not-run note, plus the advisory critic line), the bill of materials, an explanation with sources, one what-if, and version comparison. The browser stays on port 3000. If a perception weight is missing, the photo step is skipped with that reason and the typed room continues. Nothing is downloaded.
  - `npm run test:e2e` from `frontend/` runs the flow at 1280×900 and at 390×844. This run passed both. Photo: `datasets/processed/sun_rgbd/images/test/sun_00030.jpg`, known height 2.7 m, 6 objects, 0 openings. Width 5.47 m corrected to 5.57 m. 4 Pareto points. The rendered point captioned the chair as an Objaverse mesh and the desk as a box. The image was generated. The critic line was advisory and did not change the design.
  - The IDE browser cannot set a file input, so its walkthrough used a typed room (width 6 m to 5.5 m) and the same sentence. It solved 4 points, showed Objaverse meshes on the best-style point, returned a generated image with depth and segmentation (locked-region SSIM 1.000; consistency mismatched, 0 of 2, one extra detection), an advisory critic note, a verified explanation (rate 1.000), a what-if (budget 88000, 2 hints, score change 0.002860), and versions 1 and 2. At 390 px the finished page did not overflow.
  - Report: `docs/reports/frontend_v2.md`.
- Not built: a page rewrite, a schema change, a migration, a CLIP fine-tune, SDXL, a second ControlNet, a second 3D engine, and any edit to the parser, the retriever, the recommender, the photo pipeline, the optimizer, the explanations, the named clearance constants, or the Phase 9 diffusion and critic models. Phase 11 was not started.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (145 passed, 1 skipped; the skipped face-blur test needs OpenCV and runs only in `.venv-train`; one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py`
  - From `frontend/`: `npm run lint`, `npm run build`, and `npm run test:e2e`.
  - Postgres and the API on port 8001 must already be up. `npm run test:e2e` uses http://localhost:3000 and starts `npm run dev` only when that port is free.
  - Read `docs/reports/frontend_v2.md`.

### Phase 11: evaluation and ablation

- Changed:
  - A measurement script, `scripts/eval_ablation.py`, runs the six-step ladder on code that already existed. Seed `20261001`. 16 synthetic rooms from the existing generator, and 8 SUN RGB-D test rooms whose size is the annotated floor rectangle. The photo pipeline was not re-run. NYU test frames (654 on disk) have no room rectangle, so the layout ladder was not run on them. Depth and segmentation stay the previously recorded Phase 7b numbers.
  - CP-SAT versus a `qwen2.5:7b` coordinate guess, both scored by the existing Shapely checker. Synthetic CP-SAT: 12 of 16 designs returned, 0 violations on those 12, budget compliant 12 of 12, clean 12 of 16. The guess returned 16 designs, 10 of 16 with a violation (rate 0.625), clean 6 of 16, budget compliant 16 of 16, must-keep rate 0.423 where a keep was required. SUN CP-SAT: 8 of 8 clean, 0 violations. SUN guess: 3 of 8 with a violation (rate 0.375), clean 5 of 8. Those SUN rooms have no openings, so a door-clearance miss cannot occur there.
  - Parsing on the 16 sentences: schema-valid 16 of 16, field-level accuracy 0.464, text-grounded 0.917. This does not replace the Phase 6 100-sentence numbers. Retrieval recorded 192 numbers beside the parse. 33 mapped to a named solver constant and all 33 differed. None were applied inside CP-SAT.
  - Pareto on this sample: synthetic 12 feasible, 0 checker violations, 0 budget breaches, 0 dominated pairs (one set has 2 points). SUN 8 feasible, same zeros. Counterfactual, budget plus 10 percent, 8 rooms: median full re-run 9.126 ms, median warm start 9.856 ms, diffs 8 of 8. Warm start was slower here, as in the Phase 8 table, which was not rerun. The advisory critic read 4 plan images, logged 3 disagreement lines (each "vlm flagged missing"), and left all 4 designs unchanged. It did not reject or rewrite a design.
  - Human preference: 6 blinded plan pairs and a blank sheet in `docs/reports/preference/`. Scores were not collected. No model score was written in as a preference.
  - Report: `docs/reports/evaluation_ablation.md`. Plot: `docs/reports/ablation_violation_rates.svg`. Geometry accuracy remains the public NYU and SUN RGB-D numbers, not a custom tape-measured photo set. RoomGPT, diffusion-only, and a critic reject loop were not run.
- Not built: a CubiCasa5K floor-plan parser, COLMAP, GraphRAG, a schema change, a migration, a retraining run, a page rewrite, SDXL, a second ControlNet, and any edit that puts a retrieved clearance into CP-SAT or lets the critic drop a design. Phase 12 was not started.
- Check:
  - `uv run ruff check .`
  - `uv run pytest` (162 passed, 1 skipped; the skipped face-blur test needs OpenCV and runs only in `.venv-train`; one known Starlette warning).
  - `uv run python scripts/verify_datasets.py`
  - `uv run python scripts/check_optimizer_200.py` (seed 20260930: 109 feasible, 91 infeasible, checker violations 0, budget breaches 0).
  - `uv run python scripts/check_pareto_200.py` (same seed: 109 feasible, 91 infeasible, violations 0, breaches 0, dominated pairs 0).
  - `uv run python scripts/eval_ablation.py` (seed 20261001; calls local Ollama and Postgres; does not pull a model).
  - The Next.js page was not part of this phase. The Phase 10 Playwright run remains `npm run test:e2e` from `frontend/` (2 passed).
  - Read `docs/reports/evaluation_ablation.md`. The preference sheet is `docs/reports/preference/rater_sheet.md`.

