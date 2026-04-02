# Story 8.6: RAG Test Suite

**Status:** done
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-6-rag-test-suite
**Created:** 2026-04-02

---

## Story

As a developer,
I want comprehensive tests for the entire RAG pipeline,
So that I can verify correctness and catch regressions end-to-end.

---

## Acceptance Criteria

**AC1:** Given the test directory `tests/mcp_server/test_rag/`, when running `uv run pytest tests/mcp_server/test_rag/`, then all tests pass.

**AC2:** Given `test_chunker.py`, when tests run, then it tests text extraction from PDF, TXT, MD, CSV formats AND tests chunk sizing (512 tokens default) and overlap (64 tokens default) AND tests metadata preservation (filename, page number, chunk index) AND tests error handling for corrupt/empty files.

**AC3:** Given `test_embeddings.py`, when tests run, then it tests embedding generation produces 384-dimension vectors AND tests singleton model caching (model loaded once).

**AC4:** Given `test_store.py`, when tests run, then it tests pgvector storage and retrieval AND tests cosine similarity search returns results ranked by score AND tests min_score filtering AND tests CITATION_SOURCE generation for document chunks.

**AC5:** Given `test_processor.py`, when tests run, then it tests end-to-end pipeline with fixture documents AND tests error propagation from each pipeline stage.

**AC6:** Given `test_rag_tools.py`, when tests run, then it tests `search_documents` tool with mocked store AND tests `list_documents` tool response format AND tests feature flag: tools not registered when `DATA360_RAG_ENABLED=false`.

**AC7:** Given fixture documents in `tests/mcp_server/fixtures/documents/`, when used in tests, then fixtures include a small PDF, TXT, and MD file with known content for assertion.

**AC8:** Given the full test suite, when running `uv run pytest -v`, then all 257+ existing tests continue to pass (no regressions).

---

## Tasks / Subtasks

### Task 1: Add PDF fixture (AC: #7)

- [x] Create a minimal valid PDF at `tests/mcp_server/fixtures/documents/sample.pdf` using `reportlab` or Python's built-in `struct` to generate a minimal valid PDF — OR use `fpdf2` which is already available. Check `pyproject.toml` for available PDF-generation libraries first.
- [x] The PDF must contain at least one page with known text content (e.g. "Climate data Brazil. Drought in Nordeste region.") so assertions can check extracted text.
- [x] Add `test_pdf_fixture_exists` and `test_sample_pdf_chunk_extracts_text` tests to `test_chunker.py` (alongside existing fixture tests).
- [x] Commit: `test(8-6): add sample.pdf fixture and PDF chunker tests`

### Task 2: Add `test_store.py` with mocked asyncpg (AC: #4)

- [x] Create `tests/mcp_server/test_rag/test_store.py`.
- [x] All DB calls must be mocked with `AsyncMock` — no real DB connection required.
- [x] Cover `store_document()`:
  - happy path: returns a UUID string, calls `conn.transaction()` then `conn.execute()` for document row + each chunk row.
  - mismatched chunks/embeddings raises `ValueError`.
  - transaction context manager is entered (ensure data integrity wrapper tested).
- [x] Cover `search_similar()`:
  - returns `SearchResult` objects with correct fields mapped from mock rows.
  - results are filtered by `min_score` (verify SQL param passed correctly).
  - empty result set returns empty list.
- [x] Cover `list_all_documents()`:
  - returns list of dicts with expected keys (`id`, `filename`, `mime_type`, `upload_date`, `page_count`, `chunk_count`).
  - empty DB returns empty list.
- [x] Cover `build_citation_source()` from `citation.py` for all format variants (PDF p. N, TXT/MD chunk N, CSV chunk N).
  - **Note:** `TestBuildCitationSource` already exists in `test_tools.py` — do NOT duplicate. `test_store.py` should focus on store functions only; citation is already tested.
- [x] Run: `uv run pytest tests/mcp_server/test_rag/test_store.py -v`
- [x] All tests pass.
- [x] Commit: `test(8-6): add test_store.py for pgvector storage and retrieval`

### Task 3: Full validation (AC: #1, #8)

- [x] Run: `uv run pytest tests/mcp_server/test_rag/ -v` — all RAG tests pass. (61 passed)
- [x] Run: `uv run pytest -v` — full suite, no regressions. (278 passed)
- [x] Run: `uv run ruff check . && uv run ruff format .` — clean.
- [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: `in-progress` → `review`.
- [x] Commit: `chore(8-6): final validation — all tests pass, ruff clean`

---

## Dev Notes

### Current State of `tests/mcp_server/test_rag/`

**Already implemented and passing (40 tests):**
- `test_chunker.py` — `TestChunkDocument` (10 tests), `TestFixtureDocuments` (3 tests — TXT, MD, CSV fixtures present)
- `test_embeddings.py` — `TestGenerateEmbeddings` (4 tests), `TestGenerateQueryEmbedding` (1 test), `TestSingletonCaching` (1 test)
- `test_processor.py` — `TestProcessUpload` (5 tests)
- `test_tools.py` — `TestBuildCitationSource` (6 tests), `TestSearchDocumentsTool` (4 tests), `TestListDocumentsTool` (3 tests), `TestFeatureFlag` (2 tests)

**Missing:**
1. `test_store.py` — no tests for `store.py` functions at all
2. PDF fixture at `tests/mcp_server/fixtures/documents/sample.pdf`
3. PDF-specific chunker tests (fixture-based)

### PDF Fixture Generation

Check `pyproject.toml` for available libraries. If `fpdf2` or `reportlab` is present, use it. Otherwise generate a minimal valid PDF using raw bytes (a 1-page PDF with known text can be synthesised in ~10 lines of Python using the PDF spec). Alternatively, use `pymupdf` (already a dependency via `pymupdf4llm`) to create a PDF programmatically.

**pymupdf approach (preferred — already a dep):**
```python
import pymupdf
doc = pymupdf.Document()
page = doc.new_page()
page.insert_text((72, 72), "Climate data Brazil. Drought in Nordeste region.")
pdf_bytes = doc.tobytes()
with open("tests/mcp_server/fixtures/documents/sample.pdf", "wb") as f:
    f.write(pdf_bytes)
```
Run this once as a script to generate the fixture, then commit the binary.

### `test_store.py` Implementation Pattern

`store.py` uses `asyncpg`. The standard mock pattern used elsewhere in this codebase (see `test_tools.py`):

```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

def _make_mock_conn():
    conn = AsyncMock()
    # transaction() is an async context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction.return_value = tx
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    return conn
```

**`store_document()` test — key assertions:**
- `conn.transaction()` called once (wraps the insert in a transaction)
- `conn.execute()` called `1 + len(chunks)` times (1 document row + N chunk rows)
- Returns a valid UUID string (check `uuid.UUID(result)` doesn't raise)

**`search_similar()` test — mock rows:**
asyncpg rows are dict-like. Mock them as dicts or use `MagicMock` with `__getitem__`:
```python
mock_row = {
    "content": "Drought data for Ceará region 2020.",
    "filename": "ceara.pdf",
    "page_number": 2,
    "chunk_index": 0,
    "document_id": "doc-uuid-1",
    "upload_date": datetime(2026, 4, 1),
    "similarity": 0.85,
}
conn.fetch = AsyncMock(return_value=[mock_row])
```

**`list_all_documents()` test:**
```python
mock_doc_row = {
    "id": "doc-uuid-1",
    "filename": "report.pdf",
    "mime_type": "application/pdf",
    "upload_date": datetime(2026, 4, 1),
    "page_count": 5,
    "chunk_count": 20,
}
conn.fetch = AsyncMock(return_value=[mock_doc_row])
```

### Existing RAG Source Files

- `mcp_server/rag/chunker.py` — `chunk_document()`, `extract_text_pdf()`, `extract_text_plain()`, `extract_text_csv()`, `_split_into_chunks()`
- `mcp_server/rag/embeddings.py` — `generate_embeddings()`, `generate_query_embedding()`, `get_embedder()` (singleton)
- `mcp_server/rag/store.py` — `store_document()`, `search_similar()`, `list_all_documents()`; `SearchResult` dataclass
- `mcp_server/rag/processor.py` — `process_upload()` orchestrates chunker → embeddings → store
- `mcp_server/rag/citation.py` — `build_citation_source()` (already tested in `test_tools.py`)

### Config

- `mcp_server/config.py`: `RAG_CHUNK_SIZE = 512`, `RAG_CHUNK_OVERLAP = 64` (defaults)
- Feature flag: `RAG_ENABLED` bool from `DATA360_RAG_ENABLED` env var

### Architecture Compliance

All new tests live under `tests/mcp_server/test_rag/`. No changes to `mcp_server/` source needed — this is a test-only story.

### Anti-Patterns

- **DON'T** use a real DB connection — all `asyncpg` calls must be mocked.
- **DON'T** duplicate `TestBuildCitationSource` — it already lives in `test_tools.py`.
- **DON'T** use `asyncio.run()` in tests — use `@pytest.mark.asyncio` (already configured in `pyproject.toml` with `asyncio_mode = "auto"`).
- **DON'T** add PDF fixture generation code inline in a test — generate the file once as a script and commit the binary.

### Branch & Commit Conventions

- Branch: `story/8-6-rag-test-suite`
- Commits: `test(8-6): ...` / `chore(8-6): ...`

### PR Description Format

```
## What This Does
Completes the RAG test suite for Epic 8 by adding the missing test_store.py
(pgvector storage/retrieval tests with mocked asyncpg) and a PDF fixture for
chunker testing. The rest of the test_rag/ suite (chunker, embeddings,
processor, tools, citation) was already implemented in stories 8-2 through 8-4.

## Key Code to Understand
- `tests/mcp_server/test_rag/test_store.py` — all-new; tests store_document,
  search_similar, list_all_documents with AsyncMock conn
- `tests/mcp_server/fixtures/documents/sample.pdf` — minimal one-page PDF
  generated via pymupdf for fixture-based chunker assertions

## Acceptance Criteria Covered
- [x] AC1: All RAG tests pass
- [x] AC2: Chunker tests (incl. PDF fixture)
- [x] AC3: Embeddings + singleton caching tests
- [x] AC4: Store tests (new)
- [x] AC5: Processor pipeline tests
- [x] AC6: RAG tools + feature flag tests
- [x] AC7: PDF fixture added
- [x] AC8: No regressions in full suite

## Files Changed
**New:**
- tests/mcp_server/test_rag/test_store.py
- tests/mcp_server/fixtures/documents/sample.pdf

**Modified:**
- tests/mcp_server/test_rag/test_chunker.py (PDF fixture tests added)
- _bmad-output/implementation-artifacts/sprint-status.yaml
```

### References

- [Source: `tests/mcp_server/test_rag/`] — existing 40 passing tests
- [Source: `mcp_server/rag/store.py`] — functions under test
- [Source: `tests/mcp_server/test_rag/test_tools.py`] — `_make_mock_pool()` pattern to reuse
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 8.6`] — AC source

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `test_store.py` initial run: `conn.transaction()` mock failed because `AsyncMock` makes it a coroutine, but asyncpg's `transaction()` returns a Transaction object directly (not a coroutine). Fixed by using `MagicMock(return_value=tx)` for `conn.transaction` instead of `AsyncMock`.

### Completion Notes List

- AC1: All 61 RAG tests pass ✅
- AC2: Chunker tests incl. PDF fixture (17 tests) ✅
- AC3: Embeddings + singleton caching (6 tests) — pre-existing ✅
- AC4: `test_store.py` — 18 new tests covering `store_document`, `search_similar`, `list_all_documents` ✅
- AC5: Processor pipeline tests (5 tests) — pre-existing ✅
- AC6: RAG tools + feature flag (15 tests) — pre-existing ✅
- AC7: `sample.pdf` fixture created via pymupdf, 1318 bytes, 1 page with known climate text ✅
- AC8: Full suite 278 passed, 0 failed (no regressions) ✅

### File List

- `tests/mcp_server/fixtures/documents/sample.pdf` (new)
- `tests/mcp_server/test_rag/test_chunker.py` (modified — added 3 PDF fixture tests)
- `tests/mcp_server/test_rag/test_store.py` (new — 18 tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/8-6-rag-test-suite.md` (modified)

---

## Change Log

- 2026-04-02: Story created by Bob (SM). Status → ready-for-dev.
- 2026-04-02: Story implemented by Amelia (Dev). Status → review.
