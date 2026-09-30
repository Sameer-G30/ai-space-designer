"""bge-small-en-v1.5 document and query vectors. CPU only, loaded on first use."""

# Annotations on Python 3.11.
from __future__ import annotations

# Checkpoint approved for rag_chunks. It is not the CLIP catalog model.
BGE_MODEL = "BAAI/bge-small-en-v1.5"

# Official query prefix for this checkpoint. Documents are embedded without it.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# This checkpoint's vector width. Catalog CLIP vectors are 512 and must stay 512.
BGE_DIM = 384


# Lazy CPU embedder. Importing this module does not download weights.
class BgeEmbedder:
    """Embed texts with bge-small-en-v1.5 on the CPU."""

    # Cache and log name.
    name = BGE_MODEL

    # Remember the checkpoint without loading it.
    def __init__(self, model_name: str = BGE_MODEL) -> None:
        """Store the checkpoint id."""
        # Hugging Face id or a local path.
        self.model_name = model_name
        # Tokenizer, created on first use.
        self._tokenizer = None
        # Encoder, created on first use.
        self._model = None

    # Load weights on the CPU the first time they are needed.
    def _load(self) -> None:
        """Download is allowed for this checkpoint. The load stays on CPU."""
        # Already resident.
        if self._model is not None:
            # Do not load twice.
            return
        # Import here so tests that never embed do not import torch.
        from transformers import AutoModel, AutoTokenizer

        # Matching tokenizer.
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        # Encoder on CPU so the 7B Ollama model is not evicted from the GPU.
        self._model = AutoModel.from_pretrained(self.model_name).eval()
        # Force CPU even if a GPU is visible.
        self._model.to("cpu")

    # Embed a batch. Queries receive the prefix; documents do not.
    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        """Return one L2-normalized vector per text."""
        # Nothing to embed.
        if not texts:
            # Empty result.
            return []
        # Load on first use.
        self._load()
        # Torch stays inside the call.
        import torch

        # Queries use the checkpoint's retrieval prefix.
        prepared = [QUERY_PREFIX + text for text in texts] if query else list(texts)
        # Tokenize with the model's 512-token limit.
        encoded = self._tokenizer(
            prepared,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        # No gradients.
        with torch.no_grad():
            # CLS pooling, which is the published bge pooling.
            cls = self._model(**encoded).last_hidden_state[:, 0]
            # Unit length so pgvector cosine distance matches dot-product rank.
            normal = torch.nn.functional.normalize(cls, p=2, dim=1)
        # Plain lists for SQL and for the npz cache.
        return normal.cpu().tolist()
