# Phase 3 Stage 1 optimizer report

## Result

Phase 3 adds one deterministic, hard-constrained layout candidate per solve. OR-Tools
CP-SAT places required catalog furniture on a 0.05 m grid. It preserves must-keep scene
objects at their exact input position and rotation, permits only 0° or 90° for new catalog
items, enforces the budget, keeps furniture out of opening approaches, and reserves an
accessible turning area when requested. Infeasible solves return a reason and no design.

The catalog source of truth is
`datasets/metadata/cleaning/furniture_catalog.jsonl`; neither the solver nor the 200-room
check requires PostgreSQL.

## Fixed-seed 200-room gate

Command:

```bash
uv run python scripts/check_optimizer_200.py
```

Seed: `20260930`.

- Rooms: 200
- Feasible designs: 109
- Infeasible rooms, counted separately: 91
- Independent Shapely checker violations on returned designs: 0
- Budget breaches on returned designs: 0
- Infeasible outputs without a readable reason: 0
- Median solve time across all 200 attempts: 4.141 ms

The 91 infeasible cases are expected hard-constraint outcomes. Typical causes are retained
furniture blocking an opening or another retained item, insufficient room for all required
categories and clearances, or an accessibility turning reservation that cannot coexist with
fixed furniture. They are not converted into invalid fallback designs.

## Geometry constants

- Grid size: 0.05 m
- Extra low-confidence wall inset: 0.10 m
- Minimum circulation/opening-approach width: 0.915 m (36 in)
- Minimum door clear width: 0.815 m (32 in)
- Accessible turning-space diameter: 1.525 m (60 in)

The three clearance values are named constants derived from the short cited notes in
`datasets/metadata/rag/ada_clearances.md` and `ergonomics.md`; the source PDFs were not
re-parsed.

## Independent checking, trace, BOM, and rendering

`critic/deterministic.py` uses Shapely and does not import the CP-SAT model. It audits room
bounds, overlap, opening clearance and circulation, exact must-keep pose, required-category
presence, accessibility, budget, and BOM equality.

Each feasible result carries an `OptimizerTrace` beside the locked `Design`, including
binding constraints, rejected catalog alternatives, and all six objective terms. The BOM
aggregates `item_id`, category, quantity, unit price, and line total; its total is required
to equal `Design.cost`. PNG and SVG renderers use the same solver coordinates. Local examples
are written under `datasets/processed/phase3/` and remain gitignored.

The aesthetics term is deterministic style-tag overlap. Sustainability is a deterministic
material lookup. Both are placeholders until Phase 4; no CLIP model, embedding, pgvector
write, recommendation training, weight sweep, Pareto front, or NSGA-II was added.

## API and scope

`POST /scenes` accepts and persists a manual `SceneGraph`.
`POST /designs/optimize` accepts a scene id plus the gold `Requirement`, returns one audited
design with trace and BOM or an infeasible reason, and persists only feasible requirements
and designs. `GET /health` remains unchanged. No migration, frontend work, CORS, natural
language parser, RAG retrieval, explanations, or design-version writes were added.

3D-FRONT and 3D-FUTURE were not used. No data was downloaded or rebuilt in Phase 3.
