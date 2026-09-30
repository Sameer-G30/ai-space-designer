# Phase 7a: CV model training

All numbers come from runs on the RTX 4060 Laptop GPU (8 GB), seed 20260930. Weights are in `models/` and are not committed.

## Room classifier

- Model: timm `convnext_tiny.in12k_ft_in1k`, new 15-way head, 224 px, batch 32, 12 epochs, AdamW (lr 2e-4, one-cycle), label smoothing 0.1, fp16 autocast.
- Data: the Phase 2a room-type export (Places365 val images plus SUN RGB-D scene labels) with the official splits: train 2434, val 358, test 331.
- The best epoch was chosen on val (val top-1 0.7933). The test split was scored once, after training.
- **Test top-1: 0.7492 (248 of 331).**
- Peak VRAM: 2317 MiB (PyTorch allocated, train plus val).
- Weakest classes (test recall): basement 0.36, home_theater 0.40, bedroom 0.59, living_room 0.63. Strongest: balcony 1.00, kitchen 0.93, corridor 0.88.
- Largest confusions (true -> predicted, count): basement -> corridor 6, living_room -> bedroom 5, bedroom -> living_room 5, home_theater -> living_room 4, bedroom -> kids_room 4.
- The full 15 x 15 matrix is in `models/room_classifier_metrics.json` and printed by the eval command. Some classes have only 10 test images, so per-class recall moves in steps of 0.1.
- No zero-shot baseline was run for the classifier. The plan asked for one only for the detector.

## Detector

- Model: YOLO-World-S v2 (`yolov8s-worldv2.pt`), the 26 locked furniture classes. Prompts use spaces for underscores (for example `coffee table`). Class ids and order are unchanged.
- Data: cleaned SUN RGB-D YOLO labels, official splits: train 7318, val 1118, test 1098 images.
- Image size 640, batch 8, 30 epochs, mixed precision (amp=True). Peak VRAM 3220 MiB reserved. YOLO-World-M was not tried because S fits comfortably and M was not requested.
- The best checkpoint was chosen by ultralytics on val. The test split was scored after training.

| Model (test split, 1098 images, 6231 boxes) | mAP50 | mAP50-95 |
| --- | --- | --- |
| Zero-shot YOLO-World-S, same checkpoint, 26 prompts | 0.343 | 0.260 |
| Fine-tuned | 0.558 | 0.434 |

- The zero-shot value differs in the fourth decimal between two runs (0.3426 and 0.3428). That comes from GPU non-determinism. The fine-tuned number was identical on re-evaluation.
- Metric: ultralytics box mAP, averaged over classes that have labels. It was not changed.

## Not trained, because the bytes are not on disk

- No Places365 train split (the 24 GB archive was not downloaded), so room types come from Places val plus SUN RGB-D scenes only. Small classes have about 80 train images.
- No Structured3D perspective RGB, no 3D-FRONT or 3D-FUTURE, no NYU raw. None of them were used.
- NYU frames that also appear in SUN RGB-D stay in the split Phase 2a gave them, so nothing leaks across splits.
- Dropped this phase: YOLO-World-M, CLIP fine-tuning, any photo pipeline (Phase 7b).

## Environment

`torch` in the main `.venv` is still the CPU build. Training uses a separate `.venv-train` (CUDA torch 2.14.0+cu130, timm, ultralytics) described in `requirements-train.txt`. The first ultralytics run fetched `yolov8s-worldv2.pt` and its CLIP text encoder. The first classifier run fetched the timm backbone.

## Repeat the evaluation

```bash
.venv-train/bin/python scripts/eval_room_classifier.py --split test
.venv-train/bin/python scripts/eval_detector.py
```

To retrain: `scripts/train_room_classifier.py` and `scripts/train_detector.py` with the same interpreter. Run them one at a time, and stop Ollama models first.
