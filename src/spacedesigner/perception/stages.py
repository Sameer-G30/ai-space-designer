"""GPU model stages. Each stage loads one model, runs, and frees the GPU (needs .venv-train)."""

# Annotations on Python 3.11.
from __future__ import annotations

# Garbage collection helps release GPU memory between stages.
import gc

# Numerical arrays.
import numpy as np

# Pillow image type.
from PIL import Image

# Locked room types and furniture classes.
from spacedesigner.data.taxonomy import FURNITURE_CLASSES, ROOM_TYPES

# Weight locations recorded in Phase 7a.
from spacedesigner.training.classifier import WEIGHTS_PATH as CLASSIFIER_WEIGHTS
from spacedesigner.training.detector import BEST_WEIGHTS as DETECTOR_WEIGHTS
from spacedesigner.training.detector import IMAGE_SIZE as DETECTOR_SIZE

# Approved Hugging Face checkpoints.
DEPTH_CHECKPOINT = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
SAM_CHECKPOINT = "facebook/sam2.1-hiera-tiny"

# Depth model input size (multiple of 14). 518 is the model's native size.
DEPTH_SIZE = 518

# Detections below this score are ignored.
DETECTION_CONF = 0.25

# Most detections sent to the mask model.
MAX_DETECTIONS = 20


# Raised when a weight file from Phase 7a is missing. Nothing is trained to replace it.
class MissingWeights(RuntimeError):
    """A required weight file is not on disk."""


# Release GPU memory and report the peak since the last reset.
def _finish_stage() -> float:
    """Return peak allocated MiB for the stage, then clear the cache."""
    # Torch import.
    import torch

    # Peak allocated memory in MiB (0 on CPU).
    peak = torch.cuda.max_memory_allocated() / 2**20 if torch.cuda.is_available() else 0.0
    # Free Python objects first so their tensors can be released.
    gc.collect()
    # Return cached blocks to the driver.
    if torch.cuda.is_available():
        # Empty the allocator cache.
        torch.cuda.empty_cache()
        # Reset the peak counter for the next stage.
        torch.cuda.reset_peak_memory_stats()
    # Report the peak.
    return float(peak)


# Device used by every stage.
def device() -> str:
    """Return cuda when available, else cpu."""
    # Torch import.
    import torch

    # One GPU, one model at a time.
    return "cuda" if torch.cuda.is_available() else "cpu"


# Classify the room type with the Phase 7a ConvNeXt head.
def classify_room(image: Image.Image) -> tuple[list[tuple[str, float]], float]:
    """Return (top-3 room types with probabilities, peak VRAM MiB)."""
    # Torch import.
    import torch

    # Model builder shared with training.
    from spacedesigner.training.classifier import build_model, make_transforms

    # Missing weights stop the pipeline. Nothing is retrained.
    if not CLASSIFIER_WEIGHTS.exists():
        # Name the file.
        raise MissingWeights(f"missing {CLASSIFIER_WEIGHTS}")
    # Build without downloading the backbone weights, then load the fine-tuned state.
    model = build_model(pretrained=False)
    # Load the saved weights on CPU first.
    state = torch.load(CLASSIFIER_WEIGHTS, map_location="cpu")
    # Some checkpoints wrap the state dict.
    model.load_state_dict(state.get("model", state) if isinstance(state, dict) else state)
    # Move to the device in inference mode.
    model = model.to(device()).eval()
    # Same transform as training.
    transform = make_transforms(model, train=False)
    # One-image batch.
    batch = transform(image).unsqueeze(0).to(device())
    # No gradients at inference.
    with torch.no_grad():
        # Class probabilities.
        probs = torch.softmax(model(batch), dim=1)[0].cpu().numpy()
    # Indices of the three best rooms.
    top = np.argsort(-probs)[:3]
    # Free the GPU and read the peak.
    del model, batch
    # Peak for the report.
    peak = _finish_stage()
    # Names with probabilities.
    return [(ROOM_TYPES[i], float(probs[i])) for i in top], peak


# Fine-tuned YOLO-World-S kept loaded for repeated calls (the evaluation reuses it).
class Detector:
    """Hold the detector so a batch run loads it once."""

    # Load the weights once.
    def __init__(self) -> None:
        """Load the Phase 7a detector, or stop if the weights are missing."""
        # Missing weights stop the pipeline.
        if not DETECTOR_WEIGHTS.exists():
            # Name the file.
            raise MissingWeights(f"missing {DETECTOR_WEIGHTS}")
        # Ultralytics is only in .venv-train.
        from ultralytics import YOLOWorld

        # Load the fine-tuned detector.
        self.model = YOLOWorld(str(DETECTOR_WEIGHTS))

    # Detect on one image.
    def __call__(self, image: Image.Image) -> list[tuple[str, float, np.ndarray]]:
        """Return [(class, score, xyxy box)], best first."""
        # Predict at the training size.
        result = self.model.predict(
            image, imgsz=DETECTOR_SIZE, conf=DETECTION_CONF, device=device(), verbose=False
        )[0]
        # Collected detections.
        found: list[tuple[str, float, np.ndarray]] = []
        # Walk the boxes.
        for box in result.boxes:
            # Class name, with underscores restored.
            name = result.names[int(box.cls)].replace(" ", "_")
            # Ignore anything outside the locked list.
            if name not in FURNITURE_CLASSES:
                # Skip it.
                continue
            # Keep the class, score, and pixel box.
            found.append((name, float(box.conf), box.xyxy[0].cpu().numpy()))
        # Best first, capped.
        return sorted(found, key=lambda d: -d[1])[:MAX_DETECTIONS]

    # Release the model.
    def close(self) -> float:
        """Free the GPU and return the peak MiB."""
        # Drop the reference.
        del self.model
        # Peak for the report.
        return _finish_stage()


# Detect the 26 furniture classes with the fine-tuned YOLO-World-S.
def detect_furniture(image: Image.Image) -> tuple[list[tuple[str, float, np.ndarray]], float]:
    """Return ([(class, score, xyxy box)], peak VRAM MiB)."""
    # Load, run once, and free.
    detector = Detector()
    # Run.
    found = detector(image)
    # Free and read the peak.
    return found, detector.close()


# SAM2 kept loaded for repeated calls.
class Segmenter:
    """Hold SAM2 so a batch run loads it once."""

    # Load the processor and the tiny model.
    def __init__(self) -> None:
        """Load SAM2.1 Hiera-Tiny."""
        # The SAM2 classes.
        from transformers import Sam2Model, Sam2Processor

        # Processor.
        self.processor = Sam2Processor.from_pretrained(SAM_CHECKPOINT)
        # Model on the device in inference mode.
        self.model = Sam2Model.from_pretrained(SAM_CHECKPOINT).to(device()).eval()

    # One boolean mask per box.
    def __call__(self, image: Image.Image, boxes: list[np.ndarray]) -> list[np.ndarray]:
        """Return a mask at the photo size for every box prompt."""
        # Torch import.
        import torch

        # Masks collected in box order.
        masks: list[np.ndarray] = []
        # Prompt the boxes in small groups to bound memory.
        for start in range(0, len(boxes), 5):
            # This group of boxes as plain lists.
            group = [[float(v) for v in b] for b in boxes[start : start + 5]]
            # Encode the image and add the box prompts.
            inputs = self.processor(images=image, input_boxes=[group], return_tensors="pt")
            # Move tensors to the device.
            inputs = inputs.to(device())
            # No gradients at inference.
            with torch.no_grad():
                # One mask per box.
                outputs = self.model(**inputs, multimask_output=False)
            # Upscale the masks back to the photo size.
            full = self.processor.post_process_masks(
                outputs.pred_masks.cpu(), inputs["original_sizes"]
            )[0]
            # One boolean array per box.
            masks.extend(m[0].numpy().astype(bool) for m in full)
        # All masks.
        return masks

    # Release the model.
    def close(self) -> float:
        """Free the GPU and return the peak MiB."""
        # Drop the references.
        del self.model, self.processor
        # Peak for the report.
        return _finish_stage()


# Turn each box into a mask with SAM2.
def segment_boxes(image: Image.Image, boxes: list[np.ndarray]) -> tuple[list[np.ndarray], float]:
    """Return (one boolean mask per box, peak VRAM MiB)."""
    # Nothing to segment.
    if not boxes:
        # Empty result, no GPU use.
        return [], 0.0
    # Load, run once, and free.
    segmenter = Segmenter()
    # Run.
    masks = segmenter(image, boxes)
    # Free and read the peak.
    return masks, segmenter.close()


# Depth Anything V2 kept loaded for repeated calls.
class DepthModel:
    """Hold the metric indoor depth model so a batch run loads it once."""

    # Load the processor and model.
    def __init__(self, size: int = DEPTH_SIZE) -> None:
        """Load Depth Anything V2 Small (metric indoor) for a square input of the given size."""
        # The depth classes.
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        # Processor with the short side set to the chosen size; the aspect ratio is kept.
        self.processor = AutoImageProcessor.from_pretrained(
            DEPTH_CHECKPOINT, size={"height": size, "width": size}, keep_aspect_ratio=True
        )
        # Model on the device in inference mode.
        self.model = AutoModelForDepthEstimation.from_pretrained(DEPTH_CHECKPOINT)
        # Move to the device.
        self.model = self.model.to(device()).eval()

    # Predict metres for one image.
    def __call__(self, image: Image.Image) -> np.ndarray:
        """Return depth in metres at the photo size."""
        # Torch imports.
        import torch
        import torch.nn.functional as functional

        # Encode the photo.
        inputs = self.processor(images=image, return_tensors="pt").to(device())
        # No gradients at inference.
        with torch.no_grad():
            # Metric depth at the network resolution.
            predicted = self.model(**inputs).predicted_depth
        # Resize to the photo resolution.
        depth = functional.interpolate(
            predicted.unsqueeze(1), size=(image.height, image.width), mode="bilinear"
        )[0, 0]
        # Bring it to numpy.
        return depth.float().cpu().numpy()

    # Release the model.
    def close(self) -> float:
        """Free the GPU and return the peak MiB."""
        # Drop the references.
        del self.model, self.processor
        # Peak for the report.
        return _finish_stage()


# Predict metric depth with Depth Anything V2 Small (indoor metric checkpoint).
def predict_depth(image: Image.Image, size: int = DEPTH_SIZE) -> tuple[np.ndarray, float]:
    """Return (depth in metres at the photo size, peak VRAM MiB)."""
    # Load, run once, and free.
    model = DepthModel(size)
    # Run.
    depth = model(image)
    # Free and read the peak.
    return depth, model.close()
