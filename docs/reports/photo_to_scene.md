# Phase 7b: photo to scene graph

All numbers come from public data with ground truth. No personal photos and no tape measure were used. Numbers are read from `models/photo_to_scene_metrics.json` (gitignored), written by `scripts/eval_photo_to_scene.py`.

## What the pipeline does

`POST /scenes/photo?scene_id=..&known_length_m=..&known_axis=..` takes the raw image bytes as the body, under the existing `/scenes` prefix.

1. Privacy pass in the API process (Pillow): EXIF, GPS, thumbnails, and ICC profiles are dropped by rebuilding the image from pixels. The camera rotation is applied to the pixels. The one number kept is the 35 mm equivalent focal length, used for field of view.
2. The sanitized PNG goes to a child process (`.venv-train`, CUDA torch). Its first step blurs faces (YuNet through OpenCV, `models/pretrained/face_detection_yunet_2023mar.onnx`, gitignored). If that file is missing the pipeline stops; it never skips the blur.
3. Stages run one at a time and free the GPU between them: room classifier (ConvNeXt-Tiny, 224 px), detector (YOLO-World-S fine-tune, 640 px), SAM2.1 Hiera-Tiny masks from the detector boxes, Depth Anything V2 Small metric-indoor (518 px short side). The API asks Ollama to unload `qwen2.5:7b` before the child starts.
4. Geometry (numpy): back-project depth, RANSAC floor plane (normal within 35° of camera up), RANSAC ceiling plane (above 1.8 m, within 15° of the floor normal), RANSAC line for the dominant wall direction, then the floor and wall points plus the camera foot give a wall-aligned rectangle (1 % trimmed at each end). Detections lifted through their masks become floor objects; doors and windows become openings on the nearest wall.
5. Scale, in this order: a typed length (`known_axis` is length, width, or height) scales everything and gives `high`; otherwise the metric depth is used and every dimension is `low`. A height from the no-ceiling fallback stays `low` even with a typed length. The scene-level confidence is the weakest of the three, because the locked schema has one label. The per-dimension labels are returned beside the scene. A typed length that disagrees with the photo by more than 5 times is refused with HTTP 422.
6. The scene is saved with the existing versioning: a first photo for a scene id is version 1, a repeat is the previous version plus 1. The page then saves the user's corrected room as the next version. Low confidence already insets every wall by 0.10 m in the optimizer (`LOW_CONFIDENCE_MARGIN_M`); no constant was edited.

Image size: depth 518 px short side. A sweep on 120 NYU train frames (not test) gave AbsRel 0.479 at 364, 0.301 at 518, and 0.306 at 700, so 518 was kept. Peak VRAM, measured with `torch.cuda.max_memory_allocated` per stage on the full pipeline: classifier 131 MiB, detector 92 MiB, SAM2 517 MiB, depth 341 MiB, so the largest single stage is 517 MiB. Eval peaks: depth on NYU 246 MiB, depth on SUN RGB-D 319 MiB, segmentation 566 MiB. One request on this machine took about 17 s including model loading.

## Depth: NYU Depth V2 test split

654 frames, Kinect depth masked to 0.5–10 m, invalid pixels ignored. The depth model was trained on synthetic Hypersim data, so there is no overlap with NYU.

| metric | value |
| --- | ---: |
| AbsRel | 0.2132 |
| RMSE (m) | 0.6199 |
| delta1 (< 1.25) | 0.6771 |
| AbsRel after per-image median scaling | 0.0741 |

The raw error is mostly a global scale bias (the model over-estimates by about 1.1 to 1.4 times on NYU), not a shape error. It was not corrected. This is why metric-depth-only output is labelled `low`.

## Segmentation: NYU test labels

Detector boxes prompt SAM2; the masks are painted into a label map and scored against the NYU label map (taxonomy classes only; 255 unlabeled pixels ignored). Only 64 frames are scored: NYU test frames whose SUN RGB-D twin is also in the SUN RGB-D test split, because the detector trained on the SUN train split and the other NYU test frames would leak. Mean IoU over the 26 classes is 0.3466. Strong: nightstand 0.80, sofa 0.71, bed 0.69, tv 0.68, plant 0.67, dresser 0.65. Zero: armchair, bench, side_table, tv_stand, rug, window (no correct detection, or no GT pixels matched). These are pixel IoU values aggregated over the 64 frames, not per-instance numbers.

## Room dimensions: SUN RGB-D test images with a 3D layout

1006 images have depth and a layout polygon. 533 were dropped because the layout was not a plausible room (a side under 1 m, or a height outside 1.8–5 m); 473 are scored. Ground truth is the minimum-area rectangle around the largest annotated floor polygon, and height is Ymax − Ymin. Two benchmarks:

- full room: the whole annotated room. A single photo cannot see all of it.
- visible part: the same polygon clipped to the camera view wedge (from the assumed field of view) and to the sensor's far range. This is the fairer test of the geometry.

The focal length is the default 26 mm equivalent (about a 69° wide view). SUN RGB-D intrinsics were not used. Errors are median / mean / 90th percentile in cm (n = 473).

No measurement, metric depth only:

| dimension | full room | visible part |
| --- | ---: | ---: |
| length | 152 / 251 / 634 | 96 / 127 / 265 |
| width | 77 / 112 / 250 | 105 / 121 / 224 |
| height | 44 / 55 / 100 | 44 / 55 / 100 |

Same geometry on the Kinect sensor depth (a floor on how good the plane fitting can be; it is worse on length in the full-room case because the sensor range is short):

| dimension | full room | visible part |
| --- | ---: | ---: |
| length | 213 / 315 / 708 | 38 / 70 / 176 |
| width | 65 / 125 / 338 | 42 / 63 / 136 |
| height | 44 / 53 / 99 | 44 / 53 / 99 |

Scale from one measurement: one ground-truth length is treated as the typed length, and the error is on the other two. Median / mean / 90th percentile in cm.

| anchor | other dimension | full room | visible part |
| --- | --- | ---: | ---: |
| length | width | 146 / 216 / 552 | 48 / 70 / 154 |
| length | height | 88 / 148 / 375 | 62 / 76 / 150 |
| width | length | 197 / 303 / 689 | 63 / 99 / 220 |
| width | height | 60 / 89 / 197 | 79 / 87 / 168 |
| height | length | 191 / 268 / 645 | 118 / 179 / 427 |
| height | width | 91 / 138 / 321 | 106 / 148 / 316 |

How much the measurement helps: on the visible part, anchoring the length cuts the width error from 105 to 48 cm (median). Anchoring the width cuts the length error from 96 to 63 cm. It does not help everywhere: anchoring to a height, or to any length on the full-room benchmark, often makes the other dimensions worse, because a typed length that includes parts of the room the photo never shows does not match what the depth model measured. Height is about 44 cm off either way. In short, one typed wall helps when the photo shows that wall, and the page tells the user to correct the numbers before solving.

## Not run

- Structured3D room-dimension error: the perspective RGB and depth zips are not on disk (`scenes_complete_for_photo_or_depth_check` is 0). Not run. Nothing was downloaded to make it exist.
- No Structured3D photo, panorama, 3D-FRONT, or NYU raw data was used.
- Face-blur recall was not measured. A spot check on Places365 validation images found faces in 4 images within the first 1500 scanned (the scan stopped at 4), and the blur removed their detail, but there is no labelled face set on disk, so no detection rate is claimed. The unit tests cover metadata stripping; the blur test runs only where OpenCV is installed (`.venv-train`).

## Caveats

- The geometry settings (floor points and the camera foot in the extent, ceiling support threshold of 1 % of points) were set while looking at about the first 120 test layouts. There is no validation layout split, so the dimension numbers may be a little optimistic.
- A single view cannot see unseen walls. The estimate is the visible part of the room plus the camera position.
- Objects are footprints of visible surfaces, all `low`, `movable`, and not kept. Doors and windows are placed on the nearest wall from their 3D extent and were not evaluated.
- The default focal length happens to match the SUN RGB-D kv2 sensor. NYU (kv1) has a narrower view, which is one likely contributor to the depth scale bias.

## Repeat the checks

```
uv run ruff check .
uv run pytest
uv run python scripts/verify_datasets.py
uv run python scripts/check_optimizer_200.py
.venv-train/bin/python scripts/eval_photo_to_scene.py depth     # NYU test, about 1 min
.venv-train/bin/python scripts/eval_photo_to_scene.py seg       # NYU test frames with a SUN test twin
.venv-train/bin/python scripts/eval_photo_to_scene.py dims      # SUN RGB-D layouts, about 2 min
.venv-train/bin/python scripts/eval_photo_to_scene.py depth --split train --limit 120 --size 364   # size sweep
.venv-train/bin/python -m spacedesigner.perception.worker datasets/processed/sun_rgbd/images/test/sun_00030.jpg
```

## Browser check

Servers: this project's Postgres, `uv run uvicorn spacedesigner.api.main:app --port 8001` with `DATABASE_URL` from `.env`, `npm run dev` in `frontend/`. A SUN RGB-D test image was attached to the file input through the page's own `change` event (the browser tool cannot open a file dialog).

- Desktop: upload, known length 4.5 m as the length, Estimate. The form filled room type bedroom, length 4.50, width 4.08, height 2.01, confidence high, 6 objects, 0 openings. The page said the photo estimate was saved as version 2 and the corrected room would be version 3. Width was edited to 4.2, and Save room and solve returned a 4-point Pareto set.
- 390 px wide: upload with no length. The page said the metric estimate was used, confidence low on all three, and that low confidence insets every wall by 0.10 m. No horizontal overflow (scroll width 390). Solve returned a 5-point Pareto set.
- No screenshots were committed.
