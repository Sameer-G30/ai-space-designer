"""Pretrained CLIP text embeddings, loaded lazily and never trained."""

# Protocol lets tests and scripts inject any embedder with the same method.
from typing import Protocol

# numpy stores and normalizes the embedding matrices.
import numpy as np

# Pretrained checkpoint approved for Phase 4 (text tower only, CPU, no fine-tuning).
CLIP_CHECKPOINT = "openai/clip-vit-base-patch32"


# Minimal contract shared by the real CLIP model and test doubles.
class TextEmbedder(Protocol):
    """Turn short texts into L2-normalized row vectors."""

    # Stable name stored beside cached vectors so stale caches are detected.
    name: str

    # Embed a batch of texts into a (n, d) float32 matrix.
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Return one unit-length row per input text."""


# Real CLIP text tower. Nothing heavy happens until embed_texts is first called.
class ClipTextEmbedder:
    """Embed text with the pretrained CLIP text encoder on the CPU."""

    # Cache key identifying the checkpoint that produced the vectors.
    name = CLIP_CHECKPOINT

    # Defer every heavy import and weight load so importing this module is free.
    def __init__(self, checkpoint: str = CLIP_CHECKPOINT) -> None:
        """Remember the checkpoint without loading it."""
        # Checkpoint id (or local path) to load on first use.
        self._checkpoint = checkpoint
        # Tokenizer is created on first use.
        self._tokenizer = None
        # Text model is created on first use.
        self._model = None

    # Load the tokenizer and text tower once, inside the first call only.
    def _load(self) -> None:
        """Load pretrained weights on demand."""
        # Nothing to do when the model is already resident.
        if self._model is not None:
            # Return early to avoid a second load.
            return
        # Import here so module import stays light (no torch at import time).
        from transformers import CLIPModel, CLIPTokenizer

        # Load the tokenizer that matches the checkpoint.
        self._tokenizer = CLIPTokenizer.from_pretrained(self._checkpoint)
        # Load the full CLIP model; only its text tower is used afterwards.
        self._model = CLIPModel.from_pretrained(self._checkpoint).eval()

    # Embed texts and return unit-length vectors.
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Return normalized CLIP text features for the supplied texts."""
        # Make sure the weights are resident.
        self._load()
        # Import torch lazily for the same reason as transformers.
        import torch

        # Tokenize with CLIP's 77-token limit and pad to the longest text.
        tokens = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        # Inference only: no gradients, no training.
        with torch.no_grad():
            # Project pooled text states into the shared CLIP embedding space.
            features = self._model.get_text_features(**tokens)
        # transformers 5 may wrap the tensor in an output object; unwrap when needed.
        if not isinstance(features, torch.Tensor):
            # Prefer the pooled projection when a wrapper is returned.
            features = features.pooler_output
        # Move to numpy for storage and cosine math.
        matrix = features.cpu().numpy().astype(np.float32)
        # Normalize each row so dot products are cosine similarities.
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
