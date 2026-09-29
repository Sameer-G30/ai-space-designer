# PhotoSpace

PhotoSpace is a photo-grounded interior redesign project. Phase 0 is the shared schemas, Postgres tables, FastAPI health check, and the Next.js page that displays that check. Phase 1 acquires the public datasets used later for cleaning, training, and geometry checks. Phase 2a cleans the computer-vision datasets and writes a data quality report. Phase 2b mines layout priors, builds the furniture catalog, cleans the Objaverse meshes, chunks the RAG corpus, and adds a synthetic room generator.

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

Open http://localhost:3000. The page reads `API_URL` and shows the `/health` response.

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
