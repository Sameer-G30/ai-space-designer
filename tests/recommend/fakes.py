"""Deterministic stand-in for CLIP so tests never load model weights."""

# hashlib turns text into reproducible numbers.
import hashlib

# numpy builds the vectors.
import numpy as np


# Hash-seeded unit vectors; identical text always gets the identical vector.
class FakeEmbedder:
    """Implements the TextEmbedder protocol without any model."""

    # Cache key that differs from the real checkpoint.
    name = "fake-embedder"

    # Embed each text with a generator seeded from its hash.
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Return unit-length pseudo-random rows."""
        # Collect one row per text.
        rows = []
        # Build each vector from a seed derived from the text.
        for text in texts:
            # Seed from the first eight bytes of the digest.
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            # Draw a 16-dimensional normal vector.
            vector = np.random.default_rng(seed).normal(size=16).astype(np.float32)
            # Normalize to unit length.
            rows.append(vector / np.linalg.norm(vector))
        # Stack into a matrix.
        return np.stack(rows)
