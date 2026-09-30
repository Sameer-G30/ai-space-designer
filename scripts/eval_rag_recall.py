"""Recall@5 for the hand-written standards questions. Chunk text is not printed."""

# Annotations on Python 3.11.
from __future__ import annotations

# JSON question file.
import json

# DATABASE_URL from .env when it is not already exported.
from dotenv import load_dotenv

# Repo path helper.
from spacedesigner.data.common import repo_root

# Searcher. Models load on the first query, on CPU.
from spacedesigner.rag.hybrid import HybridRetriever

# Tracked questions. They name chunk ids, not passages.
QUESTIONS = repo_root() / "datasets" / "metadata" / "rag" / "retrieval_questions.json"


# A question hits when any labelled chunk id is in the top 5.
def _hit(relevant: list[str], ranked: list[str]) -> bool:
    """Return True when the top 5 intersects the labelled ids."""
    # Membership.
    return any(chunk_id in ranked for chunk_id in relevant)


# PDF chunks are the non-summary ids. Summaries are a separate, easier target.
def _pdf_ids(relevant: list[str]) -> list[str]:
    """Return labelled ids that are not project summaries."""
    # summary_* sources are the four hand-written notes.
    return [chunk_id for chunk_id in relevant if not chunk_id.startswith("summary_")]


# Load the questions, search, and print Recall@5.
def main() -> int:
    """Return 0 after printing the rate."""
    # So the retriever can open Postgres without an exported shell variable.
    load_dotenv()
    # Question records.
    payload = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    # The list.
    questions = payload["questions"]
    # Shared CPU retriever.
    retriever = HybridRetriever()
    # Hits for the primary definition: any labelled chunk.
    hits = 0
    # Questions that name at least one PDF chunk.
    pdf_questions = 0
    # Those questions whose PDF chunk appears in the top 5.
    pdf_hits = 0
    # Walk the file in order.
    for question in questions:
        # Top 5 after fusion and rerank. The question text is used alone.
        ranked = [hit.chunk_id for hit in retriever.search(question["question"], limit=5)]
        # Labelled ids.
        relevant = list(question["relevant_chunk_ids"])
        # Primary hit.
        matched = _hit(relevant, ranked)
        # Count it.
        hits += int(matched)
        # PDF subset.
        pdf = _pdf_ids(relevant)
        # Only questions with a PDF label enter the secondary rate.
        if pdf:
            # One more PDF question.
            pdf_questions += 1
            # Hit when a labelled PDF chunk is in the top 5.
            pdf_hits += int(_hit(pdf, ranked))
        # Id, hit, and ranked ids. No passage text.
        print(f"{question['id']} hit={int(matched)} ranked={','.join(ranked)}")
    # Denominator.
    total = len(questions)
    # Primary rate.
    recall = hits / total if total else 0.0
    # Secondary rate.
    pdf_recall = pdf_hits / pdf_questions if pdf_questions else 0.0
    # Headlines.
    print(f"questions {total}")
    print(f"hits {hits}")
    print(f"recall_at_5 {recall:.6f}")
    print(f"pdf_questions {pdf_questions}")
    print(f"pdf_hits {pdf_hits}")
    print(f"pdf_recall_at_5 {pdf_recall:.6f}")
    # Measuring a low rate is still success.
    return 0


# Run only as a script.
if __name__ == "__main__":
    # Exit after the report lines.
    raise SystemExit(main())
