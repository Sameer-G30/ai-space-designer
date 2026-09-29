"""Download the public ADA and MoHUA PDFs and record the summary license."""

# Puts the scripts directory on the import path for a direct python invocation.
import sys

# Resolves this file's directory without assuming the shell cwd.
from pathlib import Path

# The shared helper downloads the PDFs and writes license rows.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# run_dataset is called once per catalog dataset id.
from download_common import run_dataset  # noqa: E402

# Script entry point.
if __name__ == "__main__":
    # Fetch the two public PDFs first.
    pdf_code = run_dataset("rag_corpus")
    # Stop if a PDF download failed.
    if pdf_code != 0:
        # Propagate the download failure.
        raise SystemExit(pdf_code)
    # Record the hand-written summaries as their own license-log entry.
    raise SystemExit(run_dataset("rag_summaries"))
