"""Room classifier: timm ConvNeXt-Tiny fine-tune and held-out evaluation (needs .venv-train)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Report files are JSON.
import json

# Paths for weights and reports.
from pathlib import Path

# Pure helpers that do not need torch.
from spacedesigner.training.room_data import (
    MODELS_DIR,
    confusion_matrix,
    load_split,
    summarize_confusion,
)

# Backbone approved for download: ImageNet-12k pretrained, ImageNet-1k fine-tuned ConvNeXt-Tiny.
BACKBONE = "convnext_tiny.in12k_ft_in1k"

# Where the fine-tuned weights go (gitignored).
WEIGHTS_PATH = MODELS_DIR / "room_classifier.pt"

# Where the held-out metrics go (tracked by nobody; the report quotes them).
METRICS_PATH = MODELS_DIR / "room_classifier_metrics.json"

# Input resolution of the backbone.
IMAGE_SIZE = 224


# Build the model with a fresh 15-way head.
def build_model(pretrained: bool):
    """Create the ConvNeXt-Tiny classifier."""
    # timm is only installed in .venv-train, so import it here.
    import timm

    # Head size is the locked room-type count.
    from spacedesigner.data.taxonomy import ROOM_TYPES

    # Pretrained weights download once from the Hugging Face hub.
    return timm.create_model(BACKBONE, pretrained=pretrained, num_classes=len(ROOM_TYPES))


# Image transforms shared by both scripts.
def make_transforms(model, train: bool):
    """Return the timm transform matching the backbone, with light augmentation for training."""
    # timm helpers.
    import timm.data

    # Read the backbone's own mean, std, and size.
    config = timm.data.resolve_data_config({}, model=model)
    # Build the matching transform.
    return timm.data.create_transform(**config, is_training=train)


# A torch Dataset over (path, label) pairs.
def make_dataset(split: str, transform):
    """Wrap one split as a torch dataset."""
    # Torch imports stay inside the function.
    from PIL import Image
    from torch.utils.data import Dataset

    # Pairs from the official split.
    pairs = load_split(split)

    # Dataset that opens images lazily.
    class RoomDataset(Dataset):
        # Number of images.
        def __len__(self) -> int:
            return len(pairs)

        # One (tensor, label) item.
        def __getitem__(self, index: int):
            # Path and label for this index.
            path, label = pairs[index]
            # Decode to RGB and transform.
            return transform(Image.open(path).convert("RGB")), label

    # Return an instance.
    return RoomDataset()


# Run the model over a split and return the predictions.
def predict_split(model, split: str, batch_size: int = 64) -> tuple[list[int], list[int]]:
    """Return (true labels, predicted labels) for one split."""
    # Torch import.
    import torch
    from torch.utils.data import DataLoader

    # Deterministic transform and no shuffling.
    loader = DataLoader(
        make_dataset(split, make_transforms(model, train=False)),
        batch_size=batch_size,
        num_workers=4,
    )
    # Evaluation mode turns dropout and stochastic depth off.
    model.eval()
    # Collect both lists.
    y_true: list[int] = []
    y_pred: list[int] = []
    # No gradients are needed.
    with torch.no_grad():
        # Iterate batches.
        for images, labels in loader:
            # Mixed precision keeps memory low.
            with torch.autocast("cuda", dtype=torch.float16):
                logits = model(images.cuda())
            # Arg-max is the top-1 prediction.
            y_pred.extend(logits.argmax(dim=1).cpu().tolist())
            # Keep the ground truth.
            y_true.extend(labels.tolist())
    # Hand back both.
    return y_true, y_pred


# Score one split and return the summary dictionary.
def evaluate(model, split: str) -> dict:
    """Compute top-1 and the confusion matrix for one split."""
    # Predictions.
    y_true, y_pred = predict_split(model, split)
    # Confusion matrix over the 15 room types.
    matrix = confusion_matrix(y_true, y_pred, 15)
    # Add the raw matrix to the summary.
    return {"split": split, **summarize_confusion(matrix), "confusion_matrix": matrix}


# Fine-tune the classifier.
def train(epochs: int = 12, batch_size: int = 32, lr: float = 2e-4, seed: int = 20260930) -> dict:
    """Train on the train split, keep the best val epoch, and score the test split once."""
    # Torch imports.
    import torch
    from torch.utils.data import DataLoader

    # Fix seeds so a rerun matches.
    torch.manual_seed(seed)
    # The GPU is required for this phase.
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; run this with .venv-train/bin/python.")
    # Model on the GPU.
    model = build_model(pretrained=True).cuda()
    # Loader for the train split with augmentation.
    train_loader = DataLoader(
        make_dataset("train", make_transforms(model, train=True)),
        batch_size=batch_size,
        shuffle=True,
        num_workers=4,
        drop_last=True,
    )
    # AdamW with weight decay is the usual ConvNeXt recipe.
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    # Cosine decay over all steps.
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=lr, total_steps=epochs * len(train_loader), pct_start=0.1
    )
    # Label smoothing softens noisy scene labels.
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.1)
    # Gradient scaling for fp16 autocast.
    scaler = torch.amp.GradScaler("cuda")
    # Reset the peak-memory counter so the report number is for training.
    torch.cuda.reset_peak_memory_stats()
    # Best validation accuracy so far.
    best_val = -1.0
    # Make sure models/ exists.
    MODELS_DIR.mkdir(exist_ok=True)
    # Epoch loop.
    for epoch in range(epochs):
        # Training mode.
        model.train()
        # Step loop.
        for images, labels in train_loader:
            # Move the batch to the GPU.
            images, labels = images.cuda(), labels.cuda()
            # Clear old gradients.
            optimizer.zero_grad(set_to_none=True)
            # Forward pass in fp16.
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_fn(model(images), labels)
            # Scaled backward pass.
            scaler.scale(loss).backward()
            # Optimizer step through the scaler.
            scaler.step(optimizer)
            # Update the scale factor.
            scaler.update()
            # Advance the learning-rate schedule.
            scheduler.step()
        # Score the val split only (test stays untouched for model selection).
        val = evaluate(model, "val")
        # Progress line.
        print(f"epoch {epoch + 1}/{epochs} loss {loss.item():.3f} val top1 {val['top1']:.4f}")
        # Keep the best val checkpoint.
        if val["top1"] > best_val:
            # Remember the score.
            best_val = val["top1"]
            # Save weights only.
            torch.save(model.state_dict(), WEIGHTS_PATH)
    # Peak VRAM in MiB during training and val.
    peak_mib = torch.cuda.max_memory_allocated() / 2**20
    # Reload the best checkpoint.
    model.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cuda"))
    # Final held-out score.
    metrics = {
        "backbone": BACKBONE,
        "epochs": epochs,
        "batch_size": batch_size,
        "image_size": IMAGE_SIZE,
        "peak_vram_mib": round(peak_mib, 1),
        "best_val_top1": best_val,
        "test": evaluate(model, "test"),
    }
    # Persist for the report.
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    # Hand back the numbers.
    return metrics


# Load saved weights and score a split.
def evaluate_saved(split: str = "test", weights: Path = WEIGHTS_PATH) -> dict:
    """Score the saved classifier on a split without retraining."""
    # Torch import.
    import torch

    # Architecture without downloading pretrained weights.
    model = build_model(pretrained=False)
    # Load the fine-tuned state.
    model.load_state_dict(torch.load(weights, map_location="cpu"))
    # Move to the GPU.
    return evaluate(model.cuda(), split)
