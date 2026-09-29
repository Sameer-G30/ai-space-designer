"""Turn the ADA PDF, the MoHUA PDF, and the short cited summaries into section chunks.

Chunk text is written under datasets/processed/rag/ (gitignored). The MoHUA guideline is all rights
reserved and is stored for retrieval only, so no chunk text goes into any tracked file.
"""

# Annotations on Python 3.11.
from __future__ import annotations

# Silences pypdf font warnings.
import logging

# Section and header patterns.
import re

# Tallies.
from collections import Counter

# Pure-Python PDF text reader (pypdf, BSD-3-Clause).
from pypdf import PdfReader

# Paths and helpers.
from spacedesigner.data.common import (
    cleaning_dir,
    processed_dir,
    raw_dir,
    repo_root,
    write_json,
    write_jsonl,
)

# pypdf logs one warning per unparsed font; the text we need still extracts, so keep errors only.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# A chunk is split into parts once it passes this many characters.
MAX_CHARS = 1800

# A chunk shorter than this many characters is dropped as too small to retrieve.
MIN_CHARS = 80

# A line that repeats on more than this share of pages is a running header or footer.
REPEAT_SHARE = 0.08

# Digits are replaced by this token so "page 27" and "page 28" count as the same line.
DIGITS = re.compile(r"\d+")

# ADA section heading, such as "403.5.1 Clear Width." or "CHAPTER 4: ACCESSIBLE ROUTES".
ADA_HEADING = re.compile(r"^(?:(\d{3}(?:\.\d+)*)\s+[A-Z][A-Za-z ,/&'()-]+\.?|CHAPTER\s+\d+:.*)$")

# MoHUA section heading, such as "4.4.2 Resting Seats" (numbered, capitalized title).
MOHUA_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,4})\.?\s+[A-Z][A-Za-z ,/&'()-]{3,}$")

# Bare page-number lines and roman numerals.
PAGE_NUMBER = re.compile(r"^(?:\d{1,4}|[ivxlc]{1,6})$", re.IGNORECASE)

# Topic keywords in priority order; the first hit names the chunk topic.
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("turning_space", ("turning space", "wheelchair turn")),
    ("clear_width", ("clear width", "walking surface", "passage")),
    ("door", ("door", "doorway", "threshold")),
    ("ramp_stair", ("ramp", "stair", "handrail")),
    ("bathroom", ("toilet", "bathroom", "water closet", "lavatory", "shower")),
    ("kitchen", ("kitchen", "sink", "work surface", "counter")),
    ("bedroom", ("bed ", "bedroom", "sleeping")),
    ("seating", ("seat", "bench", "chair")),
    ("reach_range", ("reach", "knee", "toe clearance")),
    ("controls", ("switch", "hardware", "control", "operable")),
    ("circulation", ("route", "circulation", "corridor", "path of travel")),
    ("lighting_signage", ("signage", "lighting", "contrast", "tactile")),
)


def normalize_line(line: str) -> str:
    """Collapse digits and whitespace so repeated headers and footers compare equal."""
    # Replace numbers, squeeze spaces, and lowercase.
    return " ".join(DIGITS.sub("#", line).split()).lower()


def find_running_lines(pages: list[list[str]]) -> set[str]:
    """Return the normalized lines that appear on more than REPEAT_SHARE of the pages."""
    # Count each normalized line once per page.
    counts: Counter = Counter()
    # Walk each page.
    for lines in pages:
        # Set removes repeats within the page.
        for key in {normalize_line(line) for line in lines if line.strip()}:
            # One more page with this line.
            counts[key] += 1
    # Cut-off in pages.
    limit = max(3, int(REPEAT_SHARE * len(pages)))
    # Lines above the cut-off are headers or footers.
    return {key for key, n in counts.items() if n > limit}


def strip_page(lines: list[str], running: set[str]) -> tuple[list[str], int]:
    """Remove running headers, footers, and bare page numbers. Return (kept lines, n removed)."""
    # Lines that survive.
    kept: list[str] = []
    # Number removed.
    removed = 0
    # Check each line.
    for raw in lines:
        # Trim outer whitespace.
        line = raw.strip()
        # Blank lines carry no text.
        if not line:
            # Next line.
            continue
        # Running header or footer, or a bare page number.
        if normalize_line(line) in running or PAGE_NUMBER.match(line):
            # Count the removal.
            removed += 1
            # Next line.
            continue
        # Keep the text.
        kept.append(line)
    # Give both back.
    return kept, removed


def pick_topic(text: str) -> str:
    """Name the topic of a chunk from keywords, or 'general'."""
    # Lowercase once.
    lowered = text.lower()
    # First keyword group with a hit wins.
    for topic, words in TOPICS:
        # Any keyword present.
        if any(word in lowered for word in words):
            # Done.
            return topic
    # Nothing matched.
    return "general"


def split_long(text: str) -> list[str]:
    """Split a long section into parts of at most MAX_CHARS, breaking at sentence ends."""
    # Short enough already.
    if len(text) <= MAX_CHARS:
        # One part.
        return [text]
    # Sentences, roughly.
    sentences = re.split(r"(?<=[.;:])\s+", text)
    # Parts being built.
    parts: list[str] = []
    # Current part.
    current = ""
    # Add sentences until the limit.
    for sentence in sentences:
        # Would overflow and there is already text.
        if current and len(current) + len(sentence) + 1 > MAX_CHARS:
            # Close the part.
            parts.append(current)
            # Start the next.
            current = sentence
        else:
            # Extend the part.
            current = f"{current} {sentence}".strip()
    # Last part.
    if current:
        # Keep it.
        parts.append(current)
    # Give the parts back.
    return parts


def chunk_pdf(
    path, source: str, heading_re: re.Pattern, license_note: str
) -> tuple[list[dict], dict]:
    """Read a PDF and return (chunks, stats). Chunks are split at numbered section headings."""
    # Open the PDF.
    reader = PdfReader(str(path))
    # Raw lines per page.
    pages = [(page.extract_text() or "").splitlines() for page in reader.pages]
    # Repeating header and footer lines.
    running = find_running_lines(pages)
    # Sections as (heading, section number, first page, last page, lines).
    sections: list[dict] = []
    # The section being filled; the front matter comes first.
    current = {
        "heading": "front matter",
        "section": "front_matter",
        "page": 1,
        "page_end": 1,
        "lines": [],
    }
    # Lines removed as headers or footers.
    removed_total = 0
    # Walk the pages.
    for number, lines in enumerate(pages, start=1):
        # Strip the running lines.
        kept, removed = strip_page(lines, running)
        # Tally.
        removed_total += removed
        # Walk the kept lines.
        for line in kept:
            # A heading starts a new section.
            match = heading_re.match(line)
            # Only short lines can be headings.
            if match and len(line) <= 90:
                # Close the previous section.
                sections.append(current)
                # Section number, or the whole line for chapter headings.
                key = match.group(1) if match.lastindex else line
                # Start the new section.
                current = {
                    "heading": line,
                    "section": key,
                    "page": number,
                    "page_end": number,
                    "lines": [],
                }
            else:
                # Body text.
                current["lines"].append(line)
                # Track the last page seen.
                current["page_end"] = number
    # Close the last section.
    sections.append(current)
    # Build the chunk rows.
    chunks: list[dict] = []
    # Reasons for dropped sections.
    dropped: Counter = Counter()
    # One index per page keeps ids stable.
    per_page: Counter = Counter()
    # Walk the sections.
    for section in sections:
        # Join the lines into one paragraph of text.
        text = " ".join(section["lines"]).strip()
        # Too little text to retrieve.
        if len(text) < MIN_CHARS:
            # Count it.
            dropped["too_short"] += 1
            # Next section.
            continue
        # Split long sections into parts.
        for part_index, part in enumerate(split_long(text)):
            # Skip a tiny tail.
            if len(part) < MIN_CHARS:
                # Count it.
                dropped["too_short"] += 1
                # Next part.
                continue
            # Next index on the start page.
            per_page[section["page"]] += 1
            # Assemble the row.
            chunks.append(
                {
                    "chunk_id": f"{source}_p{section['page']:04d}_{per_page[section['page']]:03d}",
                    "source": source,
                    "text": part,
                    "metadata": {
                        "source": source,
                        "page": section["page"],
                        "page_end": section["page_end"],
                        "section": section["section"],
                        "heading": section["heading"],
                        "topic": pick_topic(f"{section['heading']} {part}"),
                        "part": part_index + 1,
                        "license_note": license_note,
                    },
                }
            )
    # Stats for the report; counts only, no text.
    stats = {
        "pdf_pages": len(pages),
        "running_line_patterns_removed": len(running),
        "header_footer_lines_removed": removed_total,
        "sections_found": len(sections),
        "sections_dropped": dict(dropped),
        "chunks": len(chunks),
    }
    # Give both back.
    return chunks, stats


def chunk_summaries() -> list[dict]:
    """Chunk each short cited markdown summary at its '## ' headings."""
    # Output rows.
    chunks: list[dict] = []
    # Every summary file.
    for path in sorted((repo_root() / "datasets" / "metadata" / "rag").glob("*.md")):
        # Whole file text.
        body = path.read_text(encoding="utf-8")
        # Split at second-level headings; the first piece is the file title.
        pieces = re.split(r"^## ", body, flags=re.MULTILINE)[1:]
        # A file with no second-level headings is one section under its title line.
        if not pieces:
            # Title line without the leading "# ", then the body.
            title, _, rest = body.partition("\n")
            # Reassemble as one piece so the loop below handles it.
            pieces = [title.lstrip("# ").strip() + "\n" + rest]
        # Each piece is one section.
        for index, piece in enumerate(pieces, start=1):
            # Heading is the first line.
            heading, _, rest = piece.partition("\n")
            # Body text without blank lines.
            text = " ".join(line.strip() for line in rest.splitlines() if line.strip())
            # Tiny sections are skipped.
            if len(text) < MIN_CHARS:
                # Next piece.
                continue
            # Source id from the file name.
            source = f"summary_{path.stem}"
            # Assemble the row.
            chunks.append(
                {
                    "chunk_id": f"{source}_{index:03d}",
                    "source": source,
                    "text": text,
                    "metadata": {
                        "source": source,
                        "page": None,
                        "page_end": None,
                        "section": heading.strip(),
                        "heading": heading.strip(),
                        "topic": pick_topic(f"{heading} {text}"),
                        "part": 1,
                        "license_note": "project-written summary with cited section numbers",
                    },
                }
            )
    # Give the rows back.
    return chunks


def run() -> dict:
    """Chunk all three sources, write JSONL under processed/rag, and return counts only."""
    # Output folder (gitignored).
    out = processed_dir("rag")
    # ADA is a US government work.
    ada, ada_stats = chunk_pdf(
        raw_dir("rag") / "2010-ada-design-standards.pdf",
        "ada_2010",
        ADA_HEADING,
        "US Department of Justice, 2010 ADA Standards",
    )
    # MoHUA is all rights reserved and stored for retrieval only.
    mohua, mohua_stats = chunk_pdf(
        raw_dir("rag") / "mohua-harmonised-guidelines-2021.pdf",
        "mohua_2021",
        MOHUA_HEADING,
        "MoHUA 2021, all rights reserved, retrieval only",
    )
    # Project summaries.
    summaries = chunk_summaries()
    # All rows together.
    rows = ada + mohua + summaries
    # Write the chunks (text) to the ignored folder.
    write_jsonl(out / "chunks.jsonl", rows)
    # Tracked counts-only summary.
    summary = {
        "chunks_total": len(rows),
        "chunks_by_source": dict(sorted(Counter(r["source"] for r in rows).items())),
        "chunks_by_topic": dict(sorted(Counter(r["metadata"]["topic"] for r in rows).items())),
        "ada_2010": ada_stats,
        "mohua_2021": mohua_stats,
        "summary_chunks": len(summaries),
        "embedding": "null; embeddings are computed in Phase 6",
        "text_location": "datasets/processed/rag/chunks.jsonl (gitignored)",
    }
    # Tracked summary without any chunk text.
    write_json(cleaning_dir() / "rag_summary.json", summary)
    # Give it back.
    return summary
