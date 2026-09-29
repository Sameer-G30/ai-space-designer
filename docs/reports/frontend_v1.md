# Phase 5 frontend v1

## Result

The Next.js page on port 3000 is the Phase 5 client. It still shows `GET /health`. The browser posts only to this Next.js app. Route handlers on the server call FastAPI with `API_URL` (default `http://127.0.0.1:8001`). CORS was not added. No new FastAPI route, schema change, or migration was added.

The page has a room form and a structured requirement form. Submit stores the scene with `POST /scenes`, then solves with `POST /designs/optimize`. A feasible body draws 1 to 8 Pareto points. Clicking a point selects that design for the 2D plan, the bill of materials, and the box view. An infeasible body shows the solver reason and draws nothing. HTTP 404 and 422 show the status and the FastAPI detail and draw nothing.

## What the page sends

- Room: scene id, one of the 15 room types, length, width, height in metres, confidence, optional doors and windows, optional existing objects. Scene version is 1. Object confidence is the room confidence. A kept object is sent with `must_keep` true and `movable` false, and its id is included in `must_keep_object_ids`.
- Requirement: budget in INR, one or more of the 23 catalog classes (not rug, door, or window), occupant count, one of the nine generator styles, accessibility, and all six weights. Weights are not rescaled to sum to 1. `raw_text` is always `""`. There is no sentence box.
- Floor frame: length is x, width is y, position is the footprint centre, dimensions are length, width, height, and 90 or 270 degrees swaps the floor edges. In the box view, floor x is world X, floor y is world Z, and height is world Y. The boxes are not Objaverse GLBs.

Prices are labelled synthetic INR. Style tags and materials are labelled as project labels. Sustainability is described as a material lookup, and the page says leather, rattan, linen_fabric, polyester_fabric, and cotton_fabric use 0.5. `style_backend` is shown as the API returned it.

The bill of materials uses `item_id` from each BOM line. The page does not parse a catalog id out of an object id.

## Walkthrough

Servers: Postgres from this project's Compose file, then `uv run uvicorn spacedesigner.api.main:app --host 127.0.0.1 --port 8001` with `DATABASE_URL` exported from `.env`, and `npm run dev` in `frontend/`. Opened http://localhost:3000.

Default room: scene id `room-1`, home office, 6 m by 6 m by 2.8 m, confidence high, one south door at 0.4 m with width 0.9 m, budget 80000 INR, must-have desk and chair, style modern, weights all 1, accessibility off.

- Health line: `API status: ok (HTTP 200)`.
- Feasible solve: 5 points, `style_backend` `openai/clip-vit-base-patch32`, 7 candidates, 0 dominated removed. The first point was `cheapest`, cost ₹7,200.00, chair `cat_chair_023` at centre 0.25, 1.18 and desk `cat_desk_015` at 1.75, 0.23. Line totals 1550 + 5650 equal the design cost.
- Clicked `most_sustainable`. Design id, plan centres, BOM item ids, and total all changed together: chair `cat_chair_003` at 0.30, 1.25, desk `cat_desk_009` at 1.73, 0.25, total ₹9,600.00. The 2D plan showed the south door and both footprints. The box view showed the blue chair, the yellow desk, and the red door.
- Budget 100 INR: `No design`, reason `minimum selected catalog cost INR 7200.00 exceeds budget INR 100.00`. No plan, no bill, no canvas.
- Door width 0.5 m with the budget restored: `No design`, reason `door openings below 0.815 m: [0]`. No plan, no bill, no canvas.
- Two kept objects with the same id: `API error`, `HTTP 422`, `objects: Value error, object ids must be unique`. No plan.
- A same-origin `POST /api/designs/optimize` for scene id `missing-scene` returned HTTP 404 and `{ "ok": false, "statusCode": 404, "detail": "scene not found" }`. The form always stores the scene before it solves, so that 404 is not on the happy path. The error panel is the same one that rendered the 422.

Desktop at 1280 px wide: the room fields sit in three columns and the health card is readable. Mobile at 390 px wide: the same fields stack in one column, the category checkboxes wrap to two columns, and the weights wrap to two columns.

## Checks

- `uv run ruff check .`
- `uv run pytest`: 76 passed, one known StarletteDeprecationWarning
- `uv run python scripts/verify_datasets.py`: `phase1_complete`
- `uv run python scripts/check_optimizer_200.py`: 109 feasible, 91 infeasible, 0 checker violations, 0 budget breaches. Median solve time on this machine was 3.57 ms. The gate was not retuned.
- From `frontend/`: `npm run lint` and `npm run build` (home route dynamic)

Screenshots were not saved into the repo.

## What was not built

No natural-language parser, no Ollama, no RAG embeddings, no new FastAPI route, no CORS, no CLIP download, no schema change, no migration, no explanations, no design versions, no counterfactual control, no GLB furniture, no chart library, and no drei. 3D-FRONT and 3D-FUTURE were not used.

## What could not be verified

Dragging the orbit control was not exercised. The initial camera frame was checked, and it shows the selected chair, desk, and door. The 404 body was checked on the optimize proxy. The form itself does not have a control that skips saving the scene, so the 404 text was not produced by the Save button.
