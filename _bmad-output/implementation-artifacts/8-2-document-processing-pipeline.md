# Story 8.2: Document Processing Pipeline

**Status:** ready-for-dev
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-2-document-processing-pipeline
**Created:** 2026-04-01

---

## Story

As a developer,
I want a pipeline that extracts text from uploaded files, chunks it, generates embeddings, and stores them in pgvector,
so that uploaded documents become searchable via vector similarity.

---

## Acceptance Criteria

**AC1:** Given the `mcp_server/rag/` module, when processing an uploaded PDF document, then `chunker.py` uses `pymupdf4llm` to extract text with page-level metadata preserved (page_number per chunk).

**AC2:** Given the `mcp_server/rag/` module, when processing TXT, MD, or CSV files, then `chunker.py` extracts text directly (CSV: stringify rows), with `page_number = None` (non-paginated format).

**AC3:** Given a text extraction result from any format, when chunking, then text is split into fixed-size chunks of 512 tokens with 64 token overlap, configurable via `DATA360_RAG_CHUNK_SIZE` and `DATA360_RAG_CHUNK_OVERLAP` env vars.

**AC4:** Given the `mcp_server/rag/embeddings.py` module, when generating embeddings for a list of text chunks, then it uses `sentence-transformers/all-MiniLM-L6-v2` and produces 384-dimension float vectors.

**AC5:** Given the embedding model is loaded for the first time, when `get_embedder()` is called, then the model is loaded once and cached as a module-level singleton; subsequent calls reuse the cached model without reloading.

**AC6:** Given the `mcp_server/rag/store.py` module, when storing document chunks, then `store_document(filename, mime_type, chunks)` inserts one row into `documents` and one row per chunk into `document_chunks`, using asyncpg.

**AC7:** Given a stored set of document chunks, when `search_similar(query_embedding, limit, min_score)` is called in `store.py`, then it queries `document_chunks` using the `<=>` cosine distance operator, converts distance to similarity via `similarity = 1 - distance`, filters results where `similarity >= min_score`, and returns the top `limit` results sorted by descending similarity.

**AC8:** Given the `mcp_server/rag/processor.py` module, when `process_upload(filename, mime_type, file_bytes)` is called, then it orchestrates the full pipeline: extract text → chunk → generate embeddings → store in pgvector, returning `{"success": True, "document_id": "<uuid>", "chunk_count": N}`.

**AC9:** Given a corrupt PDF or empty file, when `process_upload` is called, then it returns `{"success": False, "error": "<descriptive message>", "error_type": "processing_error"}` without raising an exception.

**AC10:** Given any module in `mcp_server/rag/`, when logging, then it uses `logging.getLogger(__name__)` — no `print()` statements anywhere.

**AC11:** Given `mcp_server/config.py`, when loading RAG configuration, then it reads `DATA360_RAG_CHUNK_SIZE` (default: 512), `DATA360_RAG_CHUNK_OVERLAP` (default: 64), and `DATA360_RAG_ENABLED` from environment variables.

**AC12:** Given `pyproject.toml`, when RAG dependencies are added, then `pymupdf4llm` and `sentence-transformers` are added as project dependencies.

**AC13:** Given the test suite in `tests/mcp_server/test_rag/`, when running `uv run pytest tests/mcp_server/test_rag/`, then all tests pass.

---

## Tasks / Subtasks

### Task 1: Add RAG dependencies to `pyproject.toml` (AC: #12)

- [ ] Run: `uv add pymupdf4llm sentence-transformers`
- [ ] Verify `pyproject.toml` now lists `pymupdf4llm` and `sentence-transformers` under `[project.dependencies]`
- [ ] Run `uv sync` and verify the environment resolves cleanly
- [ ] Commit: `feat(8-2): add pymupdf4llm and sentence-transformers dependencies`

### Task 2: Update `mcp_server/config.py` with RAG config (AC: #11)

- [ ] Add the following RAG-specific configuration to `mcp_server/config.py`:

```python
import os

# --- existing config unchanged above ---

# RAG Configuration (feature-flagged via DATA360_RAG_ENABLED)
RAG_ENABLED: bool = os.getenv("DATA360_RAG_ENABLED", "false").lower() == "true"
RAG_CHUNK_SIZE: int = int(os.getenv("DATA360_RAG_CHUNK_SIZE", "512"))
RAG_CHUNK_OVERLAP: int = int(os.getenv("DATA360_RAG_CHUNK_OVERLAP", "64"))
```

- [ ] Verify `.env.example` already has `DATA360_RAG_ENABLED=false` (added in 8-1 Task 6)
- [ ] Add to `.env.example`:
  ```
  DATA360_RAG_CHUNK_SIZE=512
  DATA360_RAG_CHUNK_OVERLAP=64
  ```
- [ ] Commit: `feat(8-2): add RAG chunk config to mcp_server/config.py`

### Task 3: Create `mcp_server/rag/__init__.py` and `mcp_server/rag/chunker.py` (AC: #1, #2, #3)

- [ ] Create `mcp_server/rag/__init__.py` (empty)
- [ ] Create `mcp_server/rag/chunker.py`:

```python
"""Text extraction and chunking for RAG document processing.

Supports: PDF (pymupdf4llm), TXT, MD, CSV.
Chunk size and overlap are configurable via DATA360_RAG_CHUNK_SIZE / DATA360_RAG_CHUNK_OVERLAP.
"""

import csv
import io
import logging
from dataclasses import dataclass

import pymupdf4llm

from mcp_server import config

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    content: str
    page_number: int | None  # None for non-paginated formats (TXT, MD, CSV)
    chunk_index: int          # 0-based position within the document


def extract_text_pdf(file_bytes: bytes) -> list[tuple[str, int]]:
    """Extract (text, page_number) tuples from a PDF using pymupdf4llm."""
    import pymupdf  # noqa: PLC0415
    doc = pymupdf.Document(stream=file_bytes, filetype="pdf")
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = pymupdf4llm.to_markdown(doc, pages=[page_num - 1])
        if text.strip():
            pages.append((text, page_num))
    return pages


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
    """
    words = text.split()
    word_chunk = max(1, int(chunk_size * 0.75))
    word_overlap = max(0, int(overlap * 0.75))
    chunks = []
    start = 0
    while start < len(words):
        end = start + word_chunk
        chunk_text = " ".join(words[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(words):
            break
        start += word_chunk - word_overlap
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
        pages = extract_text_pdf(file_bytes)
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
```

- [ ] Commit: `feat(8-2): add mcp_server/rag/chunker.py`

### Task 4: Create `mcp_server/rag/embeddings.py` (AC: #4, #5)

- [ ] Create `mcp_server/rag/embeddings.py`:

```python
"""Embedding generation using sentence-transformers/all-MiniLM-L6-v2.

Model produces 384-dimension float vectors. Singleton pattern: model loaded once at
first use and cached for the server lifetime.
"""

import logging

logger = logging.getLogger(__name__)

_embedder = None  # module-level singleton


def get_embedder():
    """Return the cached SentenceTransformer model, loading it on first call."""
    global _embedder  # noqa: PLW0603
    if _embedder is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        logger.info("Loading sentence-transformers/all-MiniLM-L6-v2 (384 dims)…")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded and cached.")
    return _embedder


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate 384-dimension embeddings for a list of text strings.

    Args:
        texts: List of strings to embed.

    Returns:
        List of 384-dimension float vectors, one per input string.
    """
    if not texts:
        return []
    model = get_embedder()
    embeddings = model.encode(texts, show_progress_bar=False)
    return [emb.tolist() for emb in embeddings]


def generate_query_embedding(query: str) -> list[float]:
    """Generate a single 384-dimension embedding for a search query."""
    results = generate_embeddings([query])
    return results[0]
```

- [ ] Commit: `feat(8-2): add mcp_server/rag/embeddings.py`

### Task 5: Create `mcp_server/rag/store.py` (AC: #6, #7)

- [ ] Create `mcp_server/rag/store.py`:

```python
"""pgvector storage and similarity search for document chunks.

Depends on: db/002_rag_schema.sql (documents + document_chunks tables, HNSW index).
Uses asyncpg for all database operations.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from mcp_server.rag.chunker import Chunk

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    content: str
    source: str           # original filename
    page_number: int | None
    chunk_index: int
    similarity_score: float
    document_id: str
    upload_date: datetime


async def store_document(
    conn: asyncpg.Connection,
    filename: str,
    mime_type: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    page_count: int | None = None,
) -> str:
    """Insert document metadata and all chunks into pgvector.

    Returns the new document UUID.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have equal length")

    doc_id = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO documents (id, filename, mime_type, upload_date, page_count, metadata)
        VALUES ($1, $2, $3, NOW(), $4, '{}'::jsonb)
        """,
        doc_id,
        filename,
        mime_type,
        page_count,
    )

    for chunk, embedding in zip(chunks, embeddings):
        chunk_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO document_chunks (id, document_id, content, page_number, chunk_index, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, '{}'::jsonb)
            """,
            chunk_id,
            doc_id,
            chunk.content,
            chunk.page_number,
            chunk.chunk_index,
            str(embedding),  # asyncpg + pgvector: pass as string representation
        )

    logger.info("Stored document '%s' with %d chunks (id=%s)", filename, len(chunks), doc_id)
    return doc_id


async def search_similar(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    limit: int = 5,
    min_score: float = 0.3,
) -> list[SearchResult]:
    """Search document_chunks by cosine similarity.

    Converts pgvector cosine distance to similarity: similarity = 1 - distance.
    Filters results where similarity >= min_score.
    Returns results sorted by descending similarity score.
    """
    rows = await conn.fetch(
        """
        SELECT
            dc.content,
            d.filename,
            dc.page_number,
            dc.chunk_index,
            d.id::text AS document_id,
            d.upload_date,
            1 - (dc.embedding <=> $1::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE 1 - (dc.embedding <=> $1::vector) >= $2
        ORDER BY dc.embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_embedding),
        min_score,
        limit,
    )
    return [
        SearchResult(
            content=row["content"],
            source=row["filename"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
            similarity_score=float(row["similarity"]),
            document_id=row["document_id"],
            upload_date=row["upload_date"],
        )
        for row in rows
    ]


async def list_all_documents(
    conn: asyncpg.Connection,
    limit: int = 20,
) -> list[dict]:
    """Return all documents with metadata and chunk counts."""
    rows = await conn.fetch(
        """
        SELECT
            d.id::text,
            d.filename,
            d.mime_type,
            d.upload_date,
            d.page_count,
            COUNT(dc.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        GROUP BY d.id, d.filename, d.mime_type, d.upload_date, d.page_count
        ORDER BY d.upload_date DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(row) for row in rows]
```

- [ ] Commit: `feat(8-2): add mcp_server/rag/store.py`

### Task 6: Create `mcp_server/rag/processor.py` (AC: #8, #9, #10)

- [ ] Create `mcp_server/rag/processor.py`:

```python
"""Upload pipeline orchestrator for RAG document processing.

Pipeline: extract text → chunk → generate embeddings → store in pgvector.
All errors are caught and returned as structured responses — no exceptions raised.
"""

import logging

import asyncpg

from mcp_server.rag.chunker import chunk_document
from mcp_server.rag.embeddings import generate_embeddings
from mcp_server.rag.store import store_document

logger = logging.getLogger(__name__)


async def process_upload(
    conn: asyncpg.Connection,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
) -> dict:
    """Orchestrate the full RAG pipeline for an uploaded document.

    Returns:
        Success: {"success": True, "document_id": "<uuid>", "chunk_count": N}
        Failure: {"success": False, "error": "<message>", "error_type": "processing_error"}
    """
    if not file_bytes:
        return {
            "success": False,
            "error": f"Empty file: '{filename}' contains no data",
            "error_type": "processing_error",
        }

    try:
        logger.info("Processing upload: '%s' (%s, %d bytes)", filename, mime_type, len(file_bytes))

        # Step 1: Extract and chunk text
        chunks = chunk_document(file_bytes, mime_type)
        if not chunks:
            return {
                "success": False,
                "error": f"No text could be extracted from '{filename}'",
                "error_type": "processing_error",
            }
        logger.debug("Extracted %d chunks from '%s'", len(chunks), filename)

        # Step 2: Generate embeddings
        texts = [chunk.content for chunk in chunks]
        embeddings = generate_embeddings(texts)
        logger.debug("Generated %d embeddings for '%s'", len(embeddings), filename)

        # Step 3: Determine page count (max page_number for PDFs, None otherwise)
        page_count: int | None = None
        if mime_type == "application/pdf":
            pages_with_number = [c.page_number for c in chunks if c.page_number is not None]
            page_count = max(pages_with_number) if pages_with_number else None

        # Step 4: Store in pgvector
        document_id = await store_document(conn, filename, mime_type, chunks, embeddings, page_count)

        logger.info("Successfully processed '%s' → doc_id=%s, chunks=%d", filename, document_id, len(chunks))
        return {
            "success": True,
            "document_id": document_id,
            "chunk_count": len(chunks),
        }

    except ValueError as exc:
        logger.warning("Validation error processing '%s': %s", filename, exc)
        return {
            "success": False,
            "error": str(exc),
            "error_type": "processing_error",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error processing '%s': %s", filename, exc, exc_info=True)
        return {
            "success": False,
            "error": f"Failed to process '{filename}': {exc}",
            "error_type": "processing_error",
        }
```

- [ ] Commit: `feat(8-2): add mcp_server/rag/processor.py`

### Task 7: Create test fixtures and test suite (AC: #13)

- [ ] Create fixture directory and files:
  - `tests/mcp_server/test_rag/__init__.py` (empty)
  - `tests/mcp_server/fixtures/documents/sample.md` — small known-content Markdown
  - `tests/mcp_server/fixtures/documents/sample.txt` — small known-content plain text
  - `tests/mcp_server/fixtures/documents/sample.csv` — small known-content CSV (3 columns, 5 rows)

- [ ] Create `tests/mcp_server/test_rag/test_chunker.py`:

```python
"""Tests for mcp_server/rag/chunker.py — text extraction and chunking."""

from pathlib import Path

import pytest

from mcp_server.rag.chunker import Chunk, chunk_document

FIXTURES = Path(__file__).parent.parent.parent / "mcp_server" / "fixtures" / "documents"


class TestChunkDocument:
    def test_txt_returns_chunks(self):
        content = b"This is a test document. " * 100
        chunks = chunk_document(content, "text/plain")
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_txt_page_number_is_none(self):
        content = b"Hello world " * 50
        chunks = chunk_document(content, "text/plain")
        assert all(c.page_number is None for c in chunks)

    def test_md_returns_chunks(self):
        content = b"# Title\n\nSome content here. " * 80
        chunks = chunk_document(content, "text/markdown")
        assert len(chunks) > 0

    def test_md_page_number_is_none(self):
        content = b"# Title\n\nContent " * 50
        chunks = chunk_document(content, "text/markdown")
        assert all(c.page_number is None for c in chunks)

    def test_csv_returns_chunks(self):
        content = b"country,value,year\nBrazil,100,2020\nIndia,200,2021\n" * 20
        chunks = chunk_document(content, "text/csv")
        assert len(chunks) > 0

    def test_csv_page_number_is_none(self):
        content = b"a,b\n1,2\n3,4\n" * 20
        chunks = chunk_document(content, "text/csv")
        assert all(c.page_number is None for c in chunks)

    def test_chunk_index_sequential(self):
        content = b"word " * 1000
        chunks = chunk_document(content, "text/plain")
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_chunk_size_respected(self):
        content = b"word " * 500
        chunks = chunk_document(content, "text/plain", chunk_size=100, overlap=0)
        # Each chunk should have approximately 75 words (100 * 0.75)
        for chunk in chunks[:-1]:  # last chunk may be smaller
            word_count = len(chunk.content.split())
            assert word_count <= 80, f"Chunk too large: {word_count} words"

    def test_overlap_produces_more_chunks(self):
        content = b"word " * 500
        chunks_no_overlap = chunk_document(content, "text/plain", chunk_size=100, overlap=0)
        chunks_with_overlap = chunk_document(content, "text/plain", chunk_size=100, overlap=50)
        assert len(chunks_with_overlap) >= len(chunks_no_overlap)

    def test_unsupported_mime_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            chunk_document(b"data", "application/octet-stream")

    def test_empty_content_returns_empty_list(self):
        chunks = chunk_document(b"", "text/plain")
        assert chunks == []


class TestFixtureDocuments:
    def test_sample_txt_fixture_exists(self):
        assert (FIXTURES / "sample.txt").exists()

    def test_sample_md_fixture_exists(self):
        assert (FIXTURES / "sample.md").exists()

    def test_sample_csv_fixture_exists(self):
        assert (FIXTURES / "sample.csv").exists()
```

- [ ] Create `tests/mcp_server/test_rag/test_embeddings.py`:

```python
"""Tests for mcp_server/rag/embeddings.py — embedding generation and singleton."""

from unittest.mock import MagicMock, patch

from mcp_server.rag import embeddings as emb_module
from mcp_server.rag.embeddings import generate_embeddings, generate_query_embedding


class TestGenerateEmbeddings:
    def test_returns_384_dimensions(self):
        texts = ["drought in Brazil", "CO2 emissions"]
        result = generate_embeddings(texts)
        assert len(result) == 2
        assert all(len(vec) == 384 for vec in result)

    def test_empty_list_returns_empty(self):
        result = generate_embeddings([])
        assert result == []

    def test_single_text(self):
        result = generate_embeddings(["climate change"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_embeddings_are_floats(self):
        result = generate_embeddings(["test"])
        assert all(isinstance(v, float) for v in result[0])


class TestGenerateQueryEmbedding:
    def test_returns_single_384_vector(self):
        result = generate_query_embedding("drought northeast Brazil")
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)


class TestSingletonCaching:
    def test_model_loaded_only_once(self):
        # Reset singleton
        emb_module._embedder = None
        with patch("mcp_server.rag.embeddings.SentenceTransformer") as MockST:
            mock_model = MagicMock()
            mock_model.encode.return_value = [[0.1] * 384]
            MockST.return_value = mock_model

            emb_module.get_embedder()
            emb_module.get_embedder()
            emb_module.get_embedder()

            MockST.assert_called_once_with("all-MiniLM-L6-v2")
```

- [ ] Create `tests/mcp_server/test_rag/test_processor.py`:

```python
"""Tests for mcp_server/rag/processor.py — upload pipeline orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.rag.processor import process_upload


class TestProcessUpload:
    @pytest.fixture
    def mock_conn(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_empty_file_returns_error(self, mock_conn):
        result = await process_upload(mock_conn, "test.txt", "text/plain", b"")
        assert result["success"] is False
        assert result["error_type"] == "processing_error"
        assert "Empty file" in result["error"]

    @pytest.mark.asyncio
    async def test_unsupported_mime_returns_error(self, mock_conn):
        result = await process_upload(mock_conn, "test.bin", "application/octet-stream", b"data")
        assert result["success"] is False
        assert result["error_type"] == "processing_error"

    @pytest.mark.asyncio
    async def test_successful_txt_processing(self, mock_conn):
        content = b"This is a climate report about drought in Brazil. " * 20
        with patch("mcp_server.rag.processor.generate_embeddings") as mock_embed, \
             patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store:
            mock_embed.return_value = [[0.1] * 384]
            mock_store.return_value = "test-doc-uuid"

            result = await process_upload(mock_conn, "report.txt", "text/plain", content)

        assert result["success"] is True
        assert result["document_id"] == "test-doc-uuid"
        assert result["chunk_count"] >= 1

    @pytest.mark.asyncio
    async def test_successful_md_processing(self, mock_conn):
        content = b"# Report\n\nClimate data from Brazil shows rising temperatures.\n" * 20
        with patch("mcp_server.rag.processor.generate_embeddings") as mock_embed, \
             patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store:
            mock_embed.return_value = [[0.1] * 384]
            mock_store.return_value = "md-doc-uuid"

            result = await process_upload(mock_conn, "report.md", "text/markdown", content)

        assert result["success"] is True
        assert result["document_id"] == "md-doc-uuid"

    @pytest.mark.asyncio
    async def test_store_exception_returns_error(self, mock_conn):
        content = b"some text content " * 10
        with patch("mcp_server.rag.processor.generate_embeddings") as mock_embed, \
             patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store:
            mock_embed.return_value = [[0.1] * 384]
            mock_store.side_effect = Exception("DB connection failed")

            result = await process_upload(mock_conn, "report.txt", "text/plain", content)

        assert result["success"] is False
        assert result["error_type"] == "processing_error"
        assert "report.txt" in result["error"]
```

- [ ] Create fixture files:

```bash
# sample.txt
mkdir -p tests/mcp_server/fixtures/documents
cat > tests/mcp_server/fixtures/documents/sample.txt << 'EOF'
Climate Change in Brazil: A Data Overview

Brazil contains approximately 60% of the Amazon rainforest, the world's largest tropical
rainforest. Deforestation rates have fluctuated significantly over the past two decades.
CO2 emissions from land use change remain a major contributor to Brazil's total greenhouse
gas output. Drought frequency in the northeast (Nordeste) region has increased.

Renewable energy accounts for over 80% of Brazil's electricity generation, primarily
from hydropower. However, prolonged droughts increasingly stress this energy source.
EOF

# sample.md
cat > tests/mcp_server/fixtures/documents/sample.md << 'EOF'
# CEMADEM Climate Report 2025

## Executive Summary

This report analyzes sub-national climate indicators for Brazil's northeast region.

## Key Findings

- Rainfall in Ceará decreased by 15% between 2015-2024
- Average temperatures rose 1.2°C above the historical mean
- Agricultural output declined 22% due to extended dry periods

## Data Sources

World Bank Data360 indicators cross-referenced with CPTEC regional models.
EOF

# sample.csv
cat > tests/mcp_server/fixtures/documents/sample.csv << 'EOF'
state,year,rainfall_mm,temp_celsius,drought_index
Ceará,2020,487,28.3,0.72
Ceará,2021,412,28.7,0.81
Pernambuco,2020,523,27.9,0.68
Pernambuco,2021,498,28.1,0.71
Bahia,2020,612,27.4,0.55
EOF
```

- [ ] Run tests: `uv run pytest tests/mcp_server/test_rag/ -v`
- [ ] All tests pass
- [ ] Commit: `test(8-2): add RAG pipeline unit tests and fixture documents`

### Task 8: Full test suite validation

- [ ] Run: `uv run pytest -v` — all existing tests still pass (no regressions)
- [ ] Run: `uv run ruff check . && uv run ruff format .` — no lint errors
- [ ] Verify `mcp_server/rag/` directory structure:
  ```
  mcp_server/rag/
  ├── __init__.py
  ├── chunker.py
  ├── embeddings.py
  ├── processor.py
  └── store.py
  ```
- [ ] Commit: `chore(8-2): final validation — all tests pass, ruff clean`

---

## Dev Notes

### Module Architecture

```
mcp_server/rag/
├── __init__.py       # empty, marks as package
├── chunker.py        # text extraction + splitting (no DB, no network)
├── embeddings.py     # sentence-transformers singleton (no DB)
├── store.py          # asyncpg operations against pgvector tables
└── processor.py      # orchestrator: calls chunker → embeddings → store
```

**Dependency graph (no cycles):**
```
processor.py → chunker.py
processor.py → embeddings.py
processor.py → store.py
store.py      → chunker.py (Chunk type)
embeddings.py → (sentence-transformers only)
chunker.py    → (pymupdf4llm, stdlib only)
```

### Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `pyproject.toml` | **Modify** | Add `pymupdf4llm`, `sentence-transformers` |
| `mcp_server/config.py` | **Modify** | Add `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP` |
| `.env.example` | **Modify** | Add `DATA360_RAG_CHUNK_SIZE=512`, `DATA360_RAG_CHUNK_OVERLAP=64` |
| `mcp_server/rag/__init__.py` | **New** | Empty |
| `mcp_server/rag/chunker.py` | **New** | Text extraction + chunking |
| `mcp_server/rag/embeddings.py` | **New** | sentence-transformers singleton |
| `mcp_server/rag/store.py` | **New** | asyncpg pgvector operations |
| `mcp_server/rag/processor.py` | **New** | Pipeline orchestrator |
| `tests/mcp_server/test_rag/__init__.py` | **New** | Empty |
| `tests/mcp_server/test_rag/test_chunker.py` | **New** | Chunking tests |
| `tests/mcp_server/test_rag/test_embeddings.py` | **New** | Embedding + singleton tests |
| `tests/mcp_server/test_rag/test_processor.py` | **New** | Pipeline orchestration tests |
| `tests/mcp_server/fixtures/documents/sample.txt` | **New** | Fixture |
| `tests/mcp_server/fixtures/documents/sample.md` | **New** | Fixture |
| `tests/mcp_server/fixtures/documents/sample.csv` | **New** | Fixture |

**DO NOT modify:** `mcp_server/server.py`, `app/`, `db/`, any existing test files outside `test_rag/`.
The `server.py` MCP tool registrations (`search_documents`, `list_documents`) belong to Story 8.3, not 8.2.

### Embedding Model: all-MiniLM-L6-v2

- **Dimensions:** Always 384 — matches `vector(384)` in `db/002_rag_schema.sql`
- **Download size:** ~90MB on first load, cached in `~/.cache/huggingface/`
- **Speed:** ~100ms for a batch of 10 chunks on CPU (acceptable for upload pipeline)
- **Singleton:** loaded once on first call to `get_embedder()`, reused for all subsequent uploads and searches

### Chunking Strategy: Word-Based Approximation

The implementation uses word count as a token proxy (1 token ≈ 0.75 words per GPT-2/LLM conventions). This avoids a tokenizer dependency while producing reasonably sized chunks:

- `DATA360_RAG_CHUNK_SIZE=512` tokens → ~384 words per chunk
- `DATA360_RAG_CHUNK_OVERLAP=64` tokens → ~48 words overlap

For the document types handled (reports, NDCs, research papers), word-based chunking produces semantically coherent results. A proper tokenizer can be added in a future iteration if precision is needed.

### pgvector Vector Format in asyncpg

asyncpg does not natively understand the `vector` type. Pass vectors as their string representation: `"[0.1, 0.2, ...]"` and cast in SQL: `$1::vector`. Example:

```python
await conn.execute(
    "INSERT INTO document_chunks (..., embedding) VALUES (..., $1::vector)",
    str(embedding_list),  # "[0.1, 0.2, ..., 0.384]"
)
```

The query in `store.py` also casts: `$1::vector` for the cosine distance operator `<=>`.

### Feature Flag Scope for 8.2

`DATA360_RAG_ENABLED` gates MCP tool registration (Story 8.3) and Chainlit upload handling (Story 8.4). Story 8.2 creates the **pipeline module only** — no tool registration, no Chainlit handlers. The pipeline is callable regardless of the flag, but it will only be invoked when the flag is true (via 8.3 and 8.4).

### Anti-Patterns

- **DON'T** register `search_documents` or `list_documents` MCP tools in this story — that's Story 8.3
- **DON'T** add upload handling to `app/chat.py` — that's Story 8.4
- **DON'T** modify `app/prompts.py` — that's Story 8.5
- **DON'T** use `print()` — use `logging.getLogger(__name__)`
- **DON'T** use `Optional[X]` — use `X | None` (project style)
- **DON'T** hardcode `384` in Python — it's defined once in `db/002_rag_schema.sql`; Python gets it from the model output at runtime
- **DON'T** use `IVFFlat` or `vector_l2_ops` — the schema uses HNSW with `vector_cosine_ops`
- **DON'T** use `tiktoken` or any tokenizer for chunking — word-based approximation is sufficient for MVP
- **DON'T** load the sentence-transformers model eagerly at module import time — use the lazy singleton via `get_embedder()`

### Testing Without a Real Database

`test_processor.py` mocks both `generate_embeddings` and `store_document` to avoid requiring a running PostgreSQL instance. `test_embeddings.py` calls the real sentence-transformers model (it will download ~90MB on first run in CI). If CI speed is a concern, mock `SentenceTransformer` in the singleton test.

### Branch & Commit Conventions

- Branch: `story/8-2-document-processing-pipeline`
- Commit format: `feat(8-2): ...` / `test(8-2): ...` / `chore(8-2): ...`
- Expected commits: 6-8 (one per task)

---

## Epic 8 Cross-Story Context (DO NOT implement — context only)

| Story | Scope | Dependency on 8.2 |
|-------|-------|-------------------|
| 8.3 | `search_documents` + `list_documents` MCP tools | Imports `processor.py`, `store.py`, `embeddings.py` |
| 8.4 | Chainlit upload handler in `app/chat.py` | Calls `process_upload()` from `processor.py` |
| 8.5 | System prompt DOCUMENT SEARCH section | No direct dependency on 8.2 |
| 8.6 | Full RAG test suite | Tests `test_rag/` expanded from 8.2 foundation |

---

## References

- [Source: epics.md#Story 8.2] — Acceptance criteria, module structure, pipeline steps
- [Source: epics.md#Epic 8] — FR49-FR56, feature flag behavior, cross-story context
- [Source: architecture.md#Project Structure] — `mcp_server/rag/` directory layout
- [Source: architecture.md#Cross-Cutting Concerns] — RAG data flow, feature flag isolation rules
- [Source: architecture.md#Data Architecture] — `search_documents` cosine similarity formula
- [Source: 8-1-pgvector-schema-and-database-migration.md] — Schema: `documents`, `document_chunks`, `vector(384)`, HNSW index
- [Source: pyproject.toml] — Dependency management with `uv add`


# Story 8.2: Document Processing Pipeline — Created 2026-04-01

Story file: `_bmad-output/implementation-artifacts/8-2-document-processing-pipeline.md`
Status: ready-for-dev
Sprint-status updated: 8-2 → ready-for-dev
