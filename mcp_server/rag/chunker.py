"""Text extraction and chunking for RAG document processing.

Supports: PDF (pymupdf4llm), TXT, MD, CSV.
Chunk size and overlap are configurable via DATA360_RAG_CHUNK_SIZE / DATA360_RAG_CHUNK_OVERLAP.
"""

import csv
import io
import logging
from dataclasses import dataclass

from mcp_server import config

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    content: str
    page_number: int | None  # None for non-paginated formats (TXT, MD, CSV)
    chunk_index: int  # 0-based position within the document


def extract_text_pdf(file_bytes: bytes) -> tuple[list[tuple[str, int]], int]:
    """Extract (text, page_number) tuples from a PDF using pymupdf4llm.

    Returns a tuple of (pages, total_page_count) where total_page_count is the
    actual number of pages in the PDF (including blank/unextractable pages).
    """
    import pymupdf  # noqa: PLC0415
    import pymupdf4llm  # noqa: PLC0415

    doc = pymupdf.Document(stream=file_bytes, filetype="pdf")
    total_pages = len(doc)
    pages: list[tuple[str, int]] = []
    try:
        for page_num in range(total_pages):
            text = pymupdf4llm.to_markdown(doc, pages=[page_num])
            if text.strip():
                pages.append((text, page_num + 1))
    finally:
        doc.close()
    return pages, total_pages


def extract_text_plain(file_bytes: bytes) -> str:
    """Extract text from TXT or MD files."""
    return file_bytes.decode("utf-8", errors="replace")


def extract_text_csv(file_bytes: bytes) -> str:
    """Stringify CSV rows into a readable text block."""
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [", ".join(row) for row in reader]
    return "\n".join(rows)


def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into fixed-size token-approximate chunks with overlap.

    Uses word-based approximation: 1 token ≈ 0.75 words (conservative estimate).
    Raises ValueError if overlap >= chunk_size (would cause infinite loop).
    """
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")
    words = text.split()
    if not words:
        return []
    word_chunk = max(1, int(chunk_size * 0.75))
    word_overlap = max(0, int(overlap * 0.75))
    # Ensure step is always positive after word conversion
    step = word_chunk - word_overlap
    if step < 1:
        step = 1
    chunks = []
    start = 0
    while start < len(words):
        end = start + word_chunk
        chunk_text = " ".join(words[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(words):
            break
        start += step
    return chunks


def chunk_document(
    file_bytes: bytes,
    mime_type: str,
    chunk_size: int = config.RAG_CHUNK_SIZE,
    overlap: int = config.RAG_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Extract and chunk a document based on its MIME type.

    Returns a list of Chunk objects with content, page_number, and chunk_index.
    Raises ValueError for unsupported MIME types.
    """
    supported = {"application/pdf", "text/plain", "text/markdown", "text/csv"}
    if mime_type not in supported:
        raise ValueError(f"Unsupported MIME type: {mime_type}. Supported: {supported}")

    chunks: list[Chunk] = []
    chunk_index = 0

    if mime_type == "application/pdf":
        pages, _total_pages = extract_text_pdf(file_bytes)
        for text, page_number in pages:
            for chunk_text in _split_into_chunks(text, chunk_size, overlap):
                chunks.append(Chunk(content=chunk_text, page_number=page_number, chunk_index=chunk_index))
                chunk_index += 1
    else:
        if mime_type == "text/csv":
            text = extract_text_csv(file_bytes)
        else:
            text = extract_text_plain(file_bytes)
        for chunk_text in _split_into_chunks(text, chunk_size, overlap):
            chunks.append(Chunk(content=chunk_text, page_number=None, chunk_index=chunk_index))
            chunk_index += 1

    logger.debug("Chunked document (%s) → %d chunks", mime_type, len(chunks))
    return chunks
