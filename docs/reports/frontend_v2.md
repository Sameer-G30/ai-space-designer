# Phase 10: full page flow

The page from Phases 5–9 was not rewritten. Playwright drives that page on http://localhost:3000. The browser does not call port 8001. Same-origin Next.js handlers still proxy with `API_URL`.

## What the test does

`frontend/e2e/mvp-flow.spec.ts` runs once at 1280×900 and once at 390×844. Both passes do the same steps.

1. Open `/` and read `API status: ok (HTTP 200)`.
2. Set a fresh scene id.
3. If the perception worker, the saved detector, the room classifier, YuNet, SAM2.1 Hiera-Tiny, and Depth Anything V2 Metric-Indoor-Small are on disk, upload a SUN RGB-D test JPEG and type a known height of 2.7 m. If that scale is rejected, the same file is tried with metric depth. If a weight file is missing, the photo step is skipped with that reason and the typed room continues. Nothing is downloaded.
4. Change the room width. A photo width under 4.5 m is set to 5.20 m. A larger width is increased by 0.10 m. A short length, an implausible height, or a door under 0.90 m is corrected before solving.
5. Parse one sentence. The structured fields must become budget 80000, style scandinavian, 1 occupant, desk, and chair. The solver-constants line must be shown.
6. Save and solve. The result must be 1 to 8 Pareto points, a 2D plan, and a 3D view. Each caption is `box` or `Objaverse mesh`. A mesh route that returns HTTP 200 must show `Objaverse mesh`.
7. Render this design. The depth map and the segmentation map must appear, plus either a generated image or the existing not-run note, and a critic line that starts with `advisory.` or `not_run.`. Photorealism is not checked.
8. Read the bill of materials, including an `item_id` and a total, with no line-total mismatch.
9. Explain this design, run the prefilled what-if, and compare versions. Version 2 must appear.
10. The document must not be wider than the viewport. No request may use port 8001.

## This run

Playwright 1.63.0, Chromium, `npm run test:e2e` from `frontend/`. Postgres and the API on port 8001 were already up. Playwright started Next.js because nothing was listening on port 3000, then stopped that server when the run finished.

Both viewports passed (3.7 minutes).

| | desktop | narrow |
| --- | --- | --- |
| photo | `datasets/processed/sun_rgbd/images/test/sun_00030.jpg` | same file |
| known height | 2.7 m accepted | 2.7 m accepted |
| estimate | 6 objects, 0 openings, 0 faces blurred | same |
| width correction | 5.47 m to 5.57 m | 5.47 m to 5.57 m |
| Pareto points | 4 | 4 |
| 3D caption on the rendered point | chair Objaverse mesh, desk box | same |
| image | generated | generated |
| critic line | advisory. advisory only; the geometric checker was not overridden | same |

The photo weights were present, so the skip path was not taken. A generated image is not a claim that the furniture looks right.

## Manual walkthrough

The IDE browser cannot set a file input (`DOM.setFileInputFiles` is blocked), so this walkthrough did not upload the SUN JPEG. The photo path above is the Playwright run.

On http://127.0.0.1:3000 at 1280×900, with the API already ok:

- Scene id `manual-walk-1`, home office, length 6 m, width changed from 6 m to 5.5 m, height 2.8 m, high confidence, one south door 0.9 m wide.
- Sentence: "I want to redo my home office in a scandinavian style. I need a desk and a chair. The budget is 80000 rupees for 1 person."
- Parse filled style `scandinavian`, left the width at 5.5 m, and listed retrieved numbers with source, page, and topic. Solver constants stayed 0.05 m, 0.10 m, 0.915 m, 0.815 m, and 1.525 m.
- Solve: 4 points, `style_backend` `openai/clip-vit-base-patch32`, sweep 93.9 ms. The cheapest point was boxes (`cat_chair_023`, `cat_desk_015`), total ₹7,200.00. The best-style point cost ₹15,100.00 and captioned both the chair and the desk `Objaverse mesh`. The 2D plan showed both footprints.
- Render this design returned an inpainted image, the depth map, and the segmentation map. Unchanged-region SSIM was 1.000. Consistency was mismatched (0 of 2 projected objects, 1 extra detection, regeneration limit reached). The critic line was advisory and said the geometric checker was not overridden. It listed four disagreement lines and did not change the design.
- Explain this design: rephrased from the templated facts, verified 1.000, with sources including `design.cost` INR 15100.00.
- What-if at the prefilled budget 88000: score change 0.002860, cost change ₹0.00, warm-started with 2 hints, 17.5 ms, no items added, removed, or moved. The page said the Pareto set was unchanged.
- Compare versions showed version 1 and version 2 for the Pareto design.
- At 390 px wide the same finished page had `scrollWidth` equal to `clientWidth` (overflow 0). The plan, the mesh captions, the what-if banner, and the version table were still on the page.

## Checks

- `uv run ruff check .` clean
- `uv run pytest`: 145 passed, 1 skipped, one StarletteDeprecationWarning about httpx versus httpx2. The skipped test is the face-blur check that needs OpenCV in `.venv-train`. The previous README count of 143 was from before the camera-aim tests already in `ca94b5c`.
- `uv run python scripts/verify_datasets.py`: `phase1_complete`
- `uv run python scripts/check_optimizer_200.py`: 109 feasible, 91 infeasible, 0 checker violations, 0 budget breaches. Median solve time on this machine was 4.254 ms.
- From `frontend/`: `npm run lint` and `npm run build`
- `npm run test:e2e`: 2 passed

## What was not built

No page rewrite, no second 3D engine, no SDXL, no second ControlNet, no schema change, no migration, no CLIP fine-tune, and no edit to the parser, RAG, recommender, photo pipeline, optimizer, explanations, named clearance constants, or the Phase 9 diffusion and critic models. Phase 11 was not started.

## Repeat

Postgres and the API must already be up. From `frontend/`:

```bash
npm run test:e2e
```

That command uses http://localhost:3000 and starts `npm run dev` only when that port is free. A missing perception weight skips the photo step and still runs the typed-room flow. It does not download a replacement.
