# Story 8.4: Chainlit Upload Integration

**Status:** review
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-4-chainlit-upload-integration
**Created:** 2026-04-01

---

## Story

As a user,
I want to attach documents in the chat and have them processed automatically,
So that I can add context to my conversations without extra steps.

---

## Acceptance Criteria

**AC1:** Given the Chainlit app is running with `DATA360_RAG_ENABLED=true`, when a user attaches a file to their message, then `app/chat.py` inspects `message.elements` for `cl.File` attachments and routes them through the upload handler before processing the text query.

**AC2:** Given a file is attached, when the MIME type is checked, then only `application/pdf`, `text/plain`, `text/markdown`, and `text/csv` are accepted; any other MIME type causes an immediate error reply: `"Unsupported file type '{mime_type}'. Please upload a PDF, TXT, MD, or CSV file."` — and the message loop does not continue.

**AC3:** Given a valid MIME type, when the file size is checked, then files exceeding `DATA360_RAG_MAX_UPLOAD_MB` (default `20`) are rejected with a clear error: `"File '{filename}' is too large ({size_mb:.1f} MB). Maximum allowed size is {limit_mb} MB."` — and the message loop does not continue.

**AC4:** Given a valid file (correct MIME type and within size limit), when processing begins, then the user sees a status message: `"⏳ Processing document..."` sent before calling `process_upload()`.

**AC5:** Given `process_upload()` completes successfully, when the result is returned, then the user sees a follow-up message: `"✅ Document ready for search ({n_chunks} chunks). You can now ask questions about it."` — where `n_chunks` is taken from the returned pipeline result.

**AC6:** Given `process_upload()` raises an exception or returns a structured error, when the error is caught, then the user sees `"❌ Failed to process document: {error_message}."` — and the rest of the message is still handled normally (text query proceeds if present).

**AC7:** Given `DATA360_RAG_ENABLED=false`, when a user attaches a file, then `message.elements` is not inspected for upload processing; file attachments are silently ignored (standard Chainlit element handling) and only the text portion of the message is processed.

**AC8:** Given `process_upload()` from `mcp_server/rag/processor.py`, when called from `app/chat.py`, then it receives: `file_bytes` (the uploaded file contents as `bytes`, read via `asyncio.to_thread`), `filename` (original filename), `mime_type`, and a live asyncpg connection acquired from the shared `app.db.pool`.

**AC9:** Given the upload handling code, when `DATA360_RAG_ENABLED=true` but no asyncpg pool is available (pool is `None`), then the user sees `"❌ RAG database is not available. Upload cannot be processed."` and processing is skipped.

**AC10:** Given the test suite `tests/app/test_upload.py`, when running `uv run pytest tests/app/test_upload.py`, then all tests pass.

**AC11:** Given `app/config.py`, when `DATA360_RAG_ENABLED=true`, then a new setting `rag_max_upload_mb: int` is loaded from `DATA360_RAG_MAX_UPLOAD_MB` env var with default `20`.

---

## Tasks / Subtasks

### Task 1: Add `rag_max_upload_mb` to `app/config.py` (AC: #11)

- [x] Open `app/config.py` and add alongside the RAG-related settings block:
  ```python
  # RAG upload settings
  rag_max_upload_mb: int = int(os.getenv("DATA360_RAG_MAX_UPLOAD_MB", "20"))
  ```
- [x] Add to `.env.example`:
  ```
  DATA360_RAG_MAX_UPLOAD_MB=20   # max file upload size in MB when RAG is enabled
  ```
- [x] Commit: `feat(8-4): add rag_max_upload_mb to app/config`

### Task 2: Add `_process_upload_element()` helper to `app/chat.py` (AC: #1–#9)

- [x] Add the following imports at the top of `app/chat.py` (guard with `if settings.rag_enabled:`):
  ```python
  # Imported lazily inside helper to avoid loading sentence-transformers when RAG is off
  ```
  Add unconditionally (these are lightweight):
  ```python
  import os
  ```
  (already present — skip if duplicate)

- [x] Add the helper function **before** the `on_message` handler:

  ```python
  _ACCEPTED_MIME_TYPES = {
      "application/pdf",
      "text/plain",
      "text/markdown",
      "text/csv",
  }

  async def _process_upload_element(element: cl.File) -> bool:
      """Process a single uploaded file element via the RAG pipeline.

      Sends status messages to the user and calls process_upload().
      Returns True if processing succeeded (or was skipped gracefully),
      False if a fatal error occurred that should abort the upload.

      This function is only called when DATA360_RAG_ENABLED=true.
      """
      from app.db import pool as db_pool  # lazy — avoids import when RAG off
      from mcp_server.rag.processor import process_upload

      filename = element.name or "uploaded_file"
      mime_type = element.mime or ""
      file_path = element.path  # Chainlit writes the file to a temp path

      # --- MIME type check ---
      if mime_type not in _ACCEPTED_MIME_TYPES:
          await cl.Message(
              content=f"⚠️ Unsupported file type '{mime_type}'. Please upload a PDF, TXT, MD, or CSV file."
          ).send()
          return False

      # --- Size check ---
      limit_mb = settings.rag_max_upload_mb
      try:
          size_bytes = os.path.getsize(file_path)
      except OSError:
          size_bytes = 0
      size_mb = size_bytes / (1024 * 1024)
      if size_mb > limit_mb:
          await cl.Message(
              content=(
                  f"⚠️ File '{filename}' is too large ({size_mb:.1f} MB). "
                  f"Maximum allowed size is {limit_mb} MB."
              )
          ).send()
          return False

      # --- Pool availability check ---
      if db_pool is None:
          await cl.Message(
              content="❌ RAG database is not available. Upload cannot be processed."
          ).send()
          return False

      # --- Processing ---
      await cl.Message(content="⏳ Processing document...").send()
      try:
          async with db_pool.acquire() as conn:
              result = await process_upload(
                  path=file_path,
                  filename=filename,
                  mime_type=mime_type,
                  conn=conn,
              )

          if isinstance(result, dict) and not result.get("success", True):
              error_msg = result.get("error", "Unknown error")
              await cl.Message(content=f"❌ Failed to process document: {error_msg}.").send()
              return False

          n_chunks = result.get("chunk_count", result.get("n_chunks", "?")) if isinstance(result, dict) else "?"
          await cl.Message(
              content=f"✅ Document ready for search ({n_chunks} chunks). You can now ask questions about it."
          ).send()
          return True

      except Exception as exc:
          logger.error("Upload processing failed for '%s': %s", filename, exc)
          await cl.Message(content=f"❌ Failed to process document: {exc}.").send()
          return False
  ```

- [x] Commit: `feat(8-4): add _process_upload_element helper to app/chat.py`

### Task 3: Wire upload handler into `on_message` (AC: #1, #7)

- [x] In the `on_message` handler, add upload processing immediately **before** appending the user message to history:

  ```python
  @cl.on_message
  async def on_message(message: cl.Message):
      # --- RAG upload handling (only when RAG is enabled) ---
      if settings.rag_enabled and message.elements:
          for element in message.elements:
              if isinstance(element, cl.File):
                  await _process_upload_element(element)
          # If message has ONLY attachments and no text, skip the agentic loop
          if not message.content.strip():
              return

      # Retrieve conversation history and append new user turn
      history = cl.user_session.get("history", [])
      history.append({"role": "user", "content": message.content})
      # ... rest of existing handler unchanged ...
  ```

  > **Note:** Do not modify any existing code below the injection point. The rest of `on_message` (history trim, MCP call, `_agentic_loop`) remains unchanged.

- [x] Commit: `feat(8-4): wire upload handler into on_message`

### Task 4: Confirm `app/db.py` exports a `pool` (AC: #8)

- [x] Check if `app/db.py` (or `app/data.py`) exposes a module-level `pool: asyncpg.Pool | None` for use by `_process_upload_element`.
- [x] If not present, add to the appropriate module:
  ```python
  # Module-level pool reference — set during application lifespan startup.
  pool: asyncpg.Pool | None = None
  ```
  And ensure the lifespan / startup hook assigns it:
  ```python
  import app.db as _app_db
  _app_db.pool = await asyncpg.create_pool(settings.database_url, ...)
  ```
- [x] If pool management already exists under a different name (e.g. `app.data`), adapt the import in `_process_upload_element` accordingly and document the actual path in Dev Notes below.
- [x] Commit: `feat(8-4): expose asyncpg pool reference in app/db`

### Task 5: Write test suite `tests/app/test_upload.py` (AC: #10)

- [x] Create `tests/app/test_upload.py`:

```python
"""Tests for Chainlit upload integration (Story 8.4)."""

import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _make_file_element(name="report.pdf", mime="application/pdf", path="/tmp/report.pdf", size=1024):
    """Build a minimal mock cl.File element."""
    el = MagicMock()
    el.name = name
    el.mime = mime
    el.path = path
    return el, size


# ---------------------------------------------------------------------------
# MIME type filtering
# ---------------------------------------------------------------------------

class TestMimeTypeFilter:
    @pytest.mark.asyncio
    async def test_pdf_accepted(self):
        el, _ = _make_file_element(mime="application/pdf")
        with patch("os.path.getsize", return_value=100), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": True, "chunk_count": 5}):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("chainlit.Message") as mock_msg_cls:
                mock_msg = AsyncMock()
                mock_msg_cls.return_value = mock_msg

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is True

    @pytest.mark.asyncio
    async def test_txt_accepted(self):
        el, _ = _make_file_element(name="data.txt", mime="text/plain", path="/tmp/data.txt")
        with patch("os.path.getsize", return_value=500), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": True, "chunk_count": 2}):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("chainlit.Message") as mock_msg_cls:
                mock_msg = AsyncMock()
                mock_msg_cls.return_value = mock_msg

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is True

    @pytest.mark.asyncio
    async def test_unsupported_mime_rejected(self):
        el, _ = _make_file_element(name="photo.png", mime="image/png")
        sent_messages = []

        async def fake_send(self):
            sent_messages.append(self.content)

        with patch("chainlit.Message") as mock_msg_cls:
            mock_instance = MagicMock()
            mock_instance.send = AsyncMock(side_effect=lambda: sent_messages.append(mock_instance.content))
            mock_msg_cls.return_value = mock_instance
            mock_msg_cls.side_effect = lambda content: mock_instance.__setattr__("content", content) or mock_instance

            from app.chat import _process_upload_element
            # Patch cl.Message directly in the module
            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                result = await _process_upload_element(el)

        assert result is False

    @pytest.mark.asyncio
    async def test_csv_accepted(self):
        el, _ = _make_file_element(name="indicators.csv", mime="text/csv", path="/tmp/indicators.csv")
        with patch("os.path.getsize", return_value=200), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": True, "chunk_count": 3}):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is True


# ---------------------------------------------------------------------------
# Size limit enforcement
# ---------------------------------------------------------------------------

class TestSizeLimit:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        """File exceeding DATA360_RAG_MAX_UPLOAD_MB is rejected."""
        el, _ = _make_file_element()
        oversized_bytes = (20 + 1) * 1024 * 1024  # 21 MB

        with patch("os.path.getsize", return_value=oversized_bytes), \
             patch("app.chat.settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_max_upload_mb = 20

            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is False
        mock_cl.Message.assert_called()
        call_content = mock_cl.Message.call_args[1].get("content") or mock_cl.Message.call_args[0][0]
        assert "too large" in call_content.lower() or "MB" in call_content

    @pytest.mark.asyncio
    async def test_file_at_limit_accepted(self):
        """File exactly at the limit is accepted."""
        el, _ = _make_file_element()
        exactly_limit_bytes = 20 * 1024 * 1024  # exactly 20 MB

        with patch("os.path.getsize", return_value=exactly_limit_bytes), \
             patch("app.chat.settings") as mock_settings, \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": True, "chunk_count": 10}):
            mock_settings.rag_enabled = True
            mock_settings.rag_max_upload_mb = 20

            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is True


# ---------------------------------------------------------------------------
# process_upload integration
# ---------------------------------------------------------------------------

class TestProcessUploadIntegration:
    @pytest.mark.asyncio
    async def test_processing_status_messages_sent(self):
        """'Processing document...' then 'Document ready for search' messages are sent."""
        el, _ = _make_file_element()
        messages_sent = []

        with patch("os.path.getsize", return_value=1024), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": True, "chunk_count": 7}):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.chat.cl") as mock_cl:
                def capture_message(content):
                    msg = AsyncMock()
                    msg.send = AsyncMock()
                    msg.content = content
                    messages_sent.append(content)
                    return msg

                mock_cl.Message.side_effect = capture_message
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is True
        assert any("Processing" in m for m in messages_sent)
        assert any("ready for search" in m for m in messages_sent)
        assert any("7 chunks" in m for m in messages_sent)

    @pytest.mark.asyncio
    async def test_process_upload_exception_handled(self):
        """Exception from process_upload returns False and sends error message."""
        el, _ = _make_file_element()

        with patch("os.path.getsize", return_value=1024), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   side_effect=RuntimeError("Embedding model failed")):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is False

    @pytest.mark.asyncio
    async def test_process_upload_structured_error_handled(self):
        """Structured error dict from process_upload returns False."""
        el, _ = _make_file_element()

        with patch("os.path.getsize", return_value=1024), \
             patch("app.db.pool", new=MagicMock()) as mock_pool, \
             patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Corrupt PDF"}):
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is False


# ---------------------------------------------------------------------------
# RAG disabled — no upload processing
# ---------------------------------------------------------------------------

class TestRagDisabled:
    @pytest.mark.asyncio
    async def test_upload_not_processed_when_rag_disabled(self):
        """When RAG_ENABLED=false, on_message does not call _process_upload_element."""
        from unittest.mock import patch, AsyncMock, MagicMock

        mock_message = MagicMock()
        mock_message.content = "hello"
        mock_message.elements = [_make_file_element()[0]]  # has a file

        with patch("app.chat.settings") as mock_settings, \
             patch("app.chat._process_upload_element", new_callable=AsyncMock) as mock_process, \
             patch("app.chat.cl") as mock_cl, \
             patch("app.chat._agentic_loop", new_callable=AsyncMock):
            mock_settings.rag_enabled = False
            mock_settings.conversation_history_limit = 50

            mock_cl.user_session = MagicMock()
            mock_cl.user_session.get = MagicMock(return_value=[])
            msg_mock = AsyncMock()
            msg_mock.send = AsyncMock()
            msg_mock.update = AsyncMock()
            mock_cl.Message.return_value = msg_mock
            mock_cl.File = type(mock_message.elements[0])

            from app.chat import on_message
            await on_message(mock_message)

        mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# Pool unavailable
# ---------------------------------------------------------------------------

class TestPoolUnavailable:
    @pytest.mark.asyncio
    async def test_upload_skipped_when_pool_none(self):
        """When db pool is None, upload returns False with error message."""
        el, _ = _make_file_element()

        with patch("os.path.getsize", return_value=1024), \
             patch("app.db.pool", new=None):
            with patch("app.chat.cl") as mock_cl:
                msg_mock = AsyncMock()
                msg_mock.send = AsyncMock()
                mock_cl.Message.return_value = msg_mock
                mock_cl.File = type(el)

                from app.chat import _process_upload_element
                result = await _process_upload_element(el)

        assert result is False
```

- [x] Run: `uv run pytest tests/app/test_upload.py -v`
- [x] All tests pass
- [x] Commit: `test(8-4): add Chainlit upload integration test suite`

### Task 6: Full validation (AC: all)

- [x] Run: `uv run pytest -v` — no regressions across the full suite
- [x] Run: `uv run ruff check . && uv run ruff format .` — clean
- [ ] Manual smoke test: start the app locally, attach a PDF, verify status messages appear
- [x] Verify upload is skipped when `DATA360_RAG_ENABLED=false`
- [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: `8-4-chainlit-upload-integration: ready-for-dev` → `in-progress` (dev moves to `review` after implementation)
- [x] Commit: `chore(8-4): final validation — all tests pass, ruff clean`

---

## Dev Notes

### Upload Flow at a Glance

```
on_message(message)
  └── if rag_enabled and message.elements:
        for element in elements:
          if isinstance(element, cl.File):
            await _process_upload_element(element)
        if not message.content.strip():
          return   # attachment-only message — skip agentic loop
  └── [existing history / agentic loop logic — unchanged]
```

### `process_upload()` Signature (from Story 8.2)

```python
# mcp_server/rag/processor.py
async def process_upload(
    path: str,
    filename: str,
    mime_type: str,
    conn: asyncpg.Connection,
) -> dict:
    """
    Orchestrates: extract → chunk → embed → store.
    Returns {"success": True, "chunk_count": N} on success,
            {"success": False, "error": "<message>"} on failure.
    """
```

> **Adapter note:** If `processor.py` uses a different signature (e.g., `file_path` vs `path`), align the call site in `_process_upload_element` to match. Check `mcp_server/rag/processor.py` before coding.

### `app/db.py` Pool Pattern

The asyncpg pool shared by FastAPI and Chainlit lives in `app/data.py` (Chainlit datalayer) or `app/db.py`. Confirm which module holds the pool and import accordingly:

```python
# Option A — if app/db.py exposes it:
from app.db import pool as db_pool

# Option B — if app/data.py exposes it:
from app.data import pool as db_pool
```

Check `app/main.py` lifespan for where `create_pool` is called and which module the reference is stored in. The `_process_upload_element` helper uses a lazy import to keep the load cost zero when RAG is off.

### Accepted MIME Types

| Extension | MIME type |
|-----------|-----------|
| `.pdf` | `application/pdf` |
| `.txt` | `text/plain` |
| `.md` | `text/markdown` |
| `.csv` | `text/csv` |

Browsers may send `text/x-markdown` for `.md` files. If needed, add this to `_ACCEPTED_MIME_TYPES` and update AC2 accordingly.

### `cl.File` vs `cl.Element`

Chainlit wraps uploaded files as `cl.File` elements. The `message.elements` list may also contain `cl.Image`, `cl.Audio`, etc. The guard `isinstance(element, cl.File)` ensures only file attachments are routed through the upload handler.

### Anti-Patterns

- **DON'T** block the event loop — `process_upload()` is async; await it properly
- **DON'T** hard-code the upload size limit — read from `settings.rag_max_upload_mb`
- **DON'T** import `asyncpg`, `sentence-transformers`, or `processor` at module top-level — lazy imports in `_process_upload_element` keep startup fast when RAG is off
- **DON'T** silently swallow upload errors — always send a user-visible message
- **DON'T** modify the agentic loop — only the preamble of `on_message` changes
- **DON'T** add system prompt changes — that's Story 8.5

### Branch & Commit Conventions

- Branch: `story/8-4-chainlit-upload-integration`
- Commits: `feat(8-4): ...` / `test(8-4): ...` / `chore(8-4): ...`

### PR Description Format (mandatory)

```
## What This Does
Adds file upload handling to the Chainlit chat UI (app/chat.py). When
DATA360_RAG_ENABLED=true and a user attaches a PDF, TXT, MD, or CSV file,
the upload is routed through process_upload() from mcp_server/rag/processor.py.
Status messages guide the user through the processing flow. Unsupported
MIME types and oversized files are rejected with clear error messages.
When RAG is disabled, file attachments are silently ignored.

## Key Code to Understand
- `app/chat.py` → `_ACCEPTED_MIME_TYPES` — allowlist of valid MIME types
- `app/chat.py` → `_process_upload_element()` — validates, status-messages,
  and delegates to process_upload(); catches all exceptions; returns bool
- `app/chat.py` → `on_message()` — preamble added to iterate elements
  before the existing history/agentic-loop logic (unchanged)
- `app/config.py` → `rag_max_upload_mb` — configurable size cap via env var

## Acceptance Criteria Covered
- [x] AC1: message.elements inspected for cl.File when RAG enabled
- [x] AC2: Unsupported MIME type rejected with clear error
- [x] AC3: Oversized files rejected with clear error
- [x] AC4: "Processing document..." status sent before processing
- [x] AC5: "Document ready for search (N chunks)" sent on success
- [x] AC6: Exceptions and structured errors surfaced to user
- [x] AC7: RAG disabled → uploads silently ignored
- [x] AC8: process_upload() receives path, filename, mime_type, conn
- [x] AC9: Pool=None guard → error message, no crash
- [x] AC10: All tests pass
- [x] AC11: rag_max_upload_mb in app/config.py

## Files Changed
**Modified:**
- app/chat.py (_ACCEPTED_MIME_TYPES, _process_upload_element, on_message preamble)
- app/config.py (rag_max_upload_mb setting)
- .env.example (DATA360_RAG_MAX_UPLOAD_MB)
- _bmad-output/implementation-artifacts/sprint-status.yaml

**New:**
- tests/app/test_upload.py
```

---

## Dev Agent Record

### Agent Model Used

anthropic/claude-sonnet-4-6 (bmad-master)

### Debug Log References

- `process_upload()` signature differs from spec: takes `file_bytes: bytes` not `path: str`. Read file via `asyncio.to_thread` before calling.
- `app/db.py` did not exist — created new module with module-level `pool = None`; pool lifecycle managed in `app/main.py` FastAPI lifespan.
- `app/config.py` uses pydantic-settings without RAG fields — added `rag_enabled: bool` and `rag_max_upload_mb: int`.
- Tests: `patch("app.chat.cl")` fails due to Chainlit lazy registry. Used `patch("app.chat.cl.Message", ...)` pattern from existing test_chat.py instead.

### Completion Notes List

- ✅ AC1: `on_message` iterates `message.elements`, routes `cl.File` through `_process_upload_element` when `rag_enabled=True`
- ✅ AC2: `_ACCEPTED_MIME_TYPES` allowlist enforced; rejects unsupported MIME with clear error
- ✅ AC3: `os.path.getsize()` → size check against `settings.rag_max_upload_mb`; rejects oversized files
- ✅ AC4: `⏳ Processing document...` message sent before `process_upload()` call
- ✅ AC5: `✅ Document ready for search ({n_chunks} chunks)` message sent on success
- ✅ AC6: Exception and structured `{success: False}` errors both handled; user sees `❌ Failed to process document: ...`
- ✅ AC7: Guard `if settings.rag_enabled and message.elements:` — file attachments silently skipped when RAG off
- ✅ AC8: `process_upload()` called with `conn=conn, filename=, mime_type=, file_bytes=` (adapted from `path=` spec)
- ✅ AC9: `if _app_db.pool is None:` guard → `❌ RAG database is not available` error message
- ✅ AC10: 15/15 tests pass; 246/246 full suite passing
- ✅ AC11: `rag_max_upload_mb` in `app/config.py` loaded from `DATA360_RAG_MAX_UPLOAD_MB` env var (default 20)

### File List

**Modified:**
- `app/chat.py` (_ACCEPTED_MIME_TYPES, _process_upload_element, on_message preamble, asyncio import)
- `app/config.py` (rag_enabled, rag_max_upload_mb settings)
- `app/main.py` (FastAPI lifespan for pool management)
- `.env.example` (DATA360_RAG_MAX_UPLOAD_MB)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

**New:**
- `app/db.py` (module-level asyncpg pool reference)
- `tests/app/test_upload.py`

---

## Change Log

- 2026-04-01: Story created by Bob (SM). Status → ready-for-dev.
- 2026-04-02: Implemented by dev agent. All ACs satisfied. 246 tests passing. Status → review.
