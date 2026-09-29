# PhotoSpace

PhotoSpace is a photo-grounded interior redesign project. Phase 0 is the shared schemas, Postgres tables, FastAPI health check, and the Next.js page that displays that check. Phase 1 acquires the public datasets used later for cleaning, training, and geometry checks. Phase 2a cleans the computer-vision datasets and writes a data quality report. Phase 2b mines layout priors, builds the furniture catalog, cleans the Objaverse meshes, chunks the RAG corpus, and adds a synthetic room generator. Phase 3 adds the hard-constrained Stage 1 layout optimizer, independent checker, plan rendering, BOM, trace, and manual-scene optimization API. Phase 4 scores catalog rows and returns one Pareto set. Phase 5 is the Next.js page for that set.

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
