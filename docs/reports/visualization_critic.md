# Phase 9: visualization and the design critic

Numbers below are from one run of `uv run python scripts/eval_visualization.py` on this machine after the fp16 weights and `qwen2.5vl:7b` were installed. The mask-lock SSIM does not use a GPU. The live lines use one generated image.

## What was built

The 3D view still uses React Three Fiber. A catalog object whose id is `catalog::{item_id}::{index}` is looked up in `datasets/metadata/cleaning/furniture_catalog_provenance.json`. When that item has an `objaverse_uid` and `datasets/processed/objaverse/{uid}.glb` exists, the mesh is loaded through `GET /api/meshes/{itemId}` and scaled onto the solver footprint. Floor x is world X, floor y is world Z, and height is world Y. A kept object, or a catalog item with no cleaned file, stays a box. The box is not removed until the GLB is in the scene. Phase 2b's 141 cleaned meshes are reused. They were not downloaded or cleaned again.

`POST /designs/{id}/visualize` sits beside the existing design routes. `POST /requirements`, `POST /designs/optimize`, `POST /scenes`, `POST /scenes/photo`, `GET /designs/{id}/explanation`, `POST /designs/{id}/counterfactual`, and `GET /designs/{id}/versions` were not changed. The route loads the stored design, scene, and requirement. It does not write a new design and it does not add a database column. Alembic head is still `c550d1f16744`.

A software rasterizer draws the room and the furniture boxes from the scene graph. It writes a depth map (nearer pixels are brighter), a segmentation map (one colour per class, plus floor, wall, door, and window), and a mask. The mask covers objects the optimizer added or moved, dilated by a few pixels, then punched back off walls, doors, windows, and unchanged furniture. After a diffusion image is produced, those locked pixels are copied back from the scene-graph render, so walls and unmoved furniture stay byte-identical.

The diffusion worker is `python -m spacedesigner.visualize.diffusion_worker` under `.venv-train`. It is Stable Diffusion 1.5 inpainting (`runwayml/stable-diffusion-inpainting`) with ControlNet-depth (`lllyasviel/control_v11f1p_sd15_depth`), the fp16 safetensors variant, attention slicing, 20 steps. `from_pretrained` uses `local_files_only`. `.venv-train` has `diffusers` 0.40.0, `accelerate` 1.15.0, and `pydantic` 2.13.5. CUDA torch is still 2.14.0+cu130. The main `.venv` was not changed. The API process does not import diffusers. The segmentation map is returned to the page. It is not a second ControlNet. A second network was not added.

If a generated image exists and the Phase 7a detector weights are present, a separate `.venv-train` process runs that saved detector, diffs class and rough position (IoU at least 0.1) against the projected scene graph, and may try another seed. This eval used 2 attempts, seeds `20260930` and `20260931`. The service cap is 3. The detector is not loaded in the same process as diffusion.

`qwen2.5vl:7b` is asked for an aesthetic note and four hard flags: overlap, clearance, budget, and missing. The call sets `keep_alive` to 0. The geometric checker in `src/spacedesigner/critic/deterministic.py` is unchanged and remains authoritative. A disagreement line is written when one checker raises a hard kind the other does not. The design is not rejected or rewritten. The live row is in `datasets/processed/phase9/disagreements.jsonl`, which is gitignored.

## Mask-lock SSIM

Four fixed offices, each with a kept chair and a new desk. Render size 128. The editable pixels were painted red and then composited with the lock. SSIM is 1 when the locked pixels are byte-identical to the scene-graph render. `changed_pixels_min` is the smallest editable region, so the score is not from an image that was never edited.

| | value |
| --- | ---: |
| rooms | 4 |
| size | 128 |
| mean SSIM | 1.000000 |
| min SSIM | 1.000000 |
| changed pixels, minimum | 2071 |

This is the pixel lock. It is not a Stable Diffusion score.

## Live image

One office from the same fixture, rendered at 512 px. Stable Diffusion 1.5 inpainted the changed region under ControlNet-depth. Unchanged pixels were then copied back from the scene-graph render. SSIM on those locked pixels was 1.0. That is the pixel lock on a real generated image, not a claim that the diffusion model left those pixels untouched by itself.

The saved detector ran on that image. It matched the one projected object and also returned one extra detection. A second seed was tried. The cap was reached, so the image stayed mismatched. Consistency rate on this run: 0 of 1.

The fixture design stores cost 0 while the catalog desk is INR 9200, and the kept chair blocks the south door. The geometric checker reported both of those. The vision model flagged overlap, missing furniture, and budget, and did not flag clearance. Budget therefore agreed. The three disagreement lines were:

- vlm flagged missing and the geometric checker did not
- vlm flagged overlap and the geometric checker did not
- geometric checker found clearance and the vlm did not flag it

The design was not changed. The critic note was advisory.

`nvidia-smi` sampled the GPU every 2 seconds during this run. The highest reading was 6647 MiB. The diffusion worker's own peak, which does not include the vision model, was 3409.3 MiB. The card has 8188 MiB. Diffusion, the detector, and `qwen2.5vl:7b` were not loaded together.

| check | result |
| --- | ---: |
| unchanged-region SSIM after inpainting | 1.000000 (1 image, 512 px) |
| geometry-consistency rate | 0 of 1 |
| critic disagreement lines | 3 |
| diffusion worker peak | 3409.3 MiB |
| sampled GPU peak, including the critic | 6647 MiB |

## Browser

Default room, budget 80000, desk and chair, high confidence, one south door. API status was ok. The solve returned 5 Pareto points and `style_backend` `openai/clip-vit-base-patch32`.

The cheapest point used catalog items with no cleaned mesh (`cat_chair_023`, `cat_desk_015`). Both captions stayed `box`, and both mesh requests were 404. The best-style point loaded `cat_chair_004` (HTTP 200) and captioned the chair `Objaverse mesh`. Its desk (`cat_desk_008`) stayed a box.

Render this design returned HTTP 200. The page showed the depth map and the segmentation map, each 512 by 512, and the sentence that diffusion was not run because diffusers is not installed. The critic line said it was not run. There was one Generated image section. The document did not scroll sideways at 941 px or at 390 px, and the maps stayed inside the 390 px width.

The plan, bill of materials, explanation control, what-if control, and version control were still on the page. That walkthrough was before the weights were installed, so the page correctly said diffusion had not run. The live image numbers above are from `eval_visualization.py` after the weights and `qwen2.5vl:7b` were in place.

## Commands

```bash
uv run ruff check .
uv run pytest
uv run python scripts/verify_datasets.py
uv run python scripts/check_optimizer_200.py
uv run python scripts/eval_visualization.py
```

From `frontend/`: `npm run lint` and `npm run build`.

This run: ruff clean, pytest 143 passed and 1 skipped, `verify_datasets.py` printed `phase1_complete`, and `check_optimizer_200.py` printed 109 feasible, 91 infeasible, 0 checker violations, and 0 budget breaches. The skipped test is the face-blur check that needs OpenCV in `.venv-train`. Pytest still prints the known Starlette warning about httpx.
