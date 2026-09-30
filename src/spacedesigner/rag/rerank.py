"""bge-reranker-base over the top hybrid candidates. CPU only, loaded on first use."""

# Annotations on Python 3.11.
from __future__ import annotations

# Cross-encoder approved for the top-20 rerank.
RERANKER_MODEL = "BAAI/bge-reranker-base"


# Lazy CPU reranker. Importing this module does not download weights.
class BgeReranker:
    """Score query and passage pairs with bge-reranker-base on the CPU."""

    # Log name.
    name = RERANKER_MODEL

    # Remember the checkpoint without loading it.
    def __init__(self, model_name: str = RERANKER_MODEL) -> None:
        """Store the checkpoint id."""
        # Hugging Face id or a local path.
        self.model_name = model_name
        # Tokenizer, created on first use.
        self._tokenizer = None
        # Cross-encoder, created on first use.
        self._model = None

    # Load weights on the CPU the first time they are needed.
    def _load(self) -> None:
        """Download is allowed for this checkpoint. The load stays on CPU."""
        # Already resident.
        if self._model is not None:
            # Do not load twice.
            return
        # Import here so tests that never rerank do not import torch.
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        # Matching tokenizer.
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        # Sequence classifier on CPU so it does not compete with qwen on the GPU.
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name).eval()
        # Force CPU.
        self._model.to("cpu")

    # Higher is more relevant. The raw logit is enough to sort.
    def score(self, query: str, passages: list[str]) -> list[float]:
        """Return one score per passage, in the same order."""
        # Nothing to score.
        if not passages:
            # Empty result.
            return []
        # Load on first use.
        self._load()
        # Torch stays inside the call.
        import torch

        # The same query is paired with every passage.
        encoded = self._tokenizer(
            [query] * len(passages),
            passages,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        # No gradients.
        with torch.no_grad():
            # One logit per pair.
            logits = self._model(**encoded).logits.view(-1)
        # Plain floats for sorting.
        return [float(value) for value in logits.cpu().tolist()]
