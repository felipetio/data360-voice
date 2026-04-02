"""Tests for Chainlit upload integration (Story 8.4).

Covers:
- AC1: on_message inspects message.elements for cl.File when rag_enabled=True
- AC2: Unsupported MIME type rejected with clear error
- AC3: Oversized file rejected with clear error
- AC4: "Processing document..." status message sent before processing
- AC5: "Document ready for search (N chunks)" sent on success
- AC6: Exception and structured error handled gracefully
- AC7: RAG disabled → uploads silently ignored
- AC8: process_upload() called with correct args (conn, filename, mime_type, file_bytes)
- AC9: Pool=None guard → error message, no crash
- AC10: All tests pass (this file itself)
- AC11: rag_max_upload_mb loaded from settings (tested via config import)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.db as _app_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings and app/chat load without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")
    monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "10")


@pytest.fixture(autouse=True)
def reset_db_pool():
    """Ensure app.db.pool is None before and after each test."""
    _app_db.pool = None
    yield
    _app_db.pool = None


def _make_file_element(name: str = "report.pdf", mime: str = "application/pdf", path: str = "/tmp/report.pdf"):
    """Build a minimal mock cl.File element."""
    el = MagicMock()
    el.name = name
    el.mime = mime
    el.path = path
    return el


def _make_pool_mock():
    """Build a mock asyncpg pool with acquire() context manager."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


# ---------------------------------------------------------------------------
# AC11: rag_max_upload_mb in app/config
# ---------------------------------------------------------------------------


class TestConfigSettings:
    def test_rag_max_upload_mb_has_default(self):
        """AC11: rag_max_upload_mb is a config setting with default 20."""
        from app.config import Settings

        s = Settings(
            anthropic_api_key="test-key",
            database_url="postgresql://localhost/test",
            rag_enabled=False,
        )
        assert s.rag_max_upload_mb == 20

    def test_rag_enabled_field_default_is_false(self):
        """RAG field default is False (env vars and .env may override at runtime)."""
        from app.config import Settings

        field = Settings.model_fields["rag_enabled"]
        assert field.default is False


# ---------------------------------------------------------------------------
# AC2: MIME type filtering
# ---------------------------------------------------------------------------


class TestMimeTypeFilter:
    @pytest.mark.asyncio
    async def test_unsupported_mime_rejected(self):
        """AC2: image/png rejected with unsupported file type error."""
        el = _make_file_element(name="photo.png", mime="image/png")
        sent_messages = []

        with (
            patch("app.chat.cl.Message", side_effect=lambda content: _capture_msg(content, sent_messages)),
            patch("app.chat.settings") as mock_settings,
        ):
            mock_settings.rag_max_upload_mb = 20

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and result.startswith("ERROR:")
        assert any("Unsupported file type" in m for m in sent_messages)

    @pytest.mark.asyncio
    async def test_pdf_accepted(self):
        """AC2: application/pdf is an accepted MIME type (gets past MIME check)."""
        el = _make_file_element(mime="application/pdf")
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=1024),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"fake pdf")
            mock_proc.return_value = {"success": True, "chunk_count": 3}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")

    @pytest.mark.asyncio
    async def test_txt_accepted(self):
        """AC2: text/plain is an accepted MIME type."""
        el = _make_file_element(name="notes.txt", mime="text/plain", path="/tmp/notes.txt")
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=512),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"text content")
            mock_proc.return_value = {"success": True, "chunk_count": 2}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")

    @pytest.mark.asyncio
    async def test_csv_accepted(self):
        """AC2: text/csv is an accepted MIME type."""
        el = _make_file_element(name="data.csv", mime="text/csv", path="/tmp/data.csv")
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=200),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"col1,col2\n1,2")
            mock_proc.return_value = {"success": True, "chunk_count": 1}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")

    @pytest.mark.asyncio
    async def test_markdown_accepted(self):
        """AC2: text/markdown is an accepted MIME type."""
        el = _make_file_element(name="doc.md", mime="text/markdown", path="/tmp/doc.md")
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=300),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"# Heading\nContent")
            mock_proc.return_value = {"success": True, "chunk_count": 1}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")


# ---------------------------------------------------------------------------
# AC3: Size limit enforcement
# ---------------------------------------------------------------------------


class TestSizeLimit:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        """AC3: File exceeding DATA360_RAG_MAX_UPLOAD_MB is rejected with clear error."""
        el = _make_file_element()
        oversized_bytes = 21 * 1024 * 1024  # 21 MB
        sent_messages = []

        with (
            patch("app.chat.cl.Message", side_effect=lambda content: _capture_msg(content, sent_messages)),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=oversized_bytes),
        ):
            mock_settings.rag_max_upload_mb = 20

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and result.startswith("ERROR:")
        assert any("too large" in m.lower() or "MB" in m for m in sent_messages)

    @pytest.mark.asyncio
    async def test_file_exactly_at_limit_accepted(self):
        """AC3: File exactly at the MB limit is NOT rejected (≤ boundary)."""
        el = _make_file_element()
        exactly_limit_bytes = 20 * 1024 * 1024  # exactly 20 MB
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=exactly_limit_bytes),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"x")
            mock_proc.return_value = {"success": True, "chunk_count": 10}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")


# ---------------------------------------------------------------------------
# AC4 & AC5: Status messages
# ---------------------------------------------------------------------------


class TestStatusMessages:
    @pytest.mark.asyncio
    async def test_processing_and_success_messages_sent(self):
        """AC4+AC5: 'Processing document...' then 'Document ready for search (N chunks)' messages."""
        el = _make_file_element()
        sent_messages = []
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", side_effect=lambda content: _capture_msg(content, sent_messages)),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=1024),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"content")
            mock_proc.return_value = {"success": True, "chunk_count": 7}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and not result.startswith("ERROR:")
        assert any("Processing" in m for m in sent_messages), f"Missing processing msg. Got: {sent_messages}"
        assert any("ready for search" in m for m in sent_messages), f"Missing ready msg. Got: {sent_messages}"
        assert any("7 chunks" in m for m in sent_messages), f"Missing chunk count. Got: {sent_messages}"


# ---------------------------------------------------------------------------
# AC6: Exception and structured error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_process_upload_exception_handled(self):
        """AC6: Exception from process_upload returns ERROR string and sends error message."""
        el = _make_file_element()
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=1024),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"content")
            mock_proc.side_effect = RuntimeError("Embedding model failed")

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and result.startswith("ERROR:")

    @pytest.mark.asyncio
    async def test_process_upload_structured_error_handled(self):
        """AC6: Structured error dict from process_upload returns ERROR string with error message."""
        el = _make_file_element()
        sent_messages = []
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", side_effect=lambda content: _capture_msg(content, sent_messages)),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=1024),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=b"content")
            mock_proc.return_value = {"success": False, "error": "Corrupt PDF", "error_type": "processing_error"}

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and result.startswith("ERROR:")
        assert any("Failed to process" in m or "Corrupt PDF" in m for m in sent_messages)


# ---------------------------------------------------------------------------
# AC7: RAG disabled — no upload processing
# ---------------------------------------------------------------------------


class TestRagDisabled:
    @pytest.mark.asyncio
    async def test_upload_not_processed_when_rag_disabled(self):
        """AC7: When rag_enabled=False, on_message does NOT call _process_upload_element."""
        el = _make_file_element()
        mock_message = MagicMock()
        mock_message.content = "hello"
        mock_message.elements = [el]

        with (
            patch("app.chat.settings") as mock_settings,
            patch("app.chat._process_upload_element", new_callable=AsyncMock) as mock_process,
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat._agentic_loop", new_callable=AsyncMock),
        ):
            mock_settings.rag_enabled = False
            mock_settings.conversation_history_limit = 50
            session_mock.get = MagicMock(return_value=[])

            from app.chat import on_message

            await on_message(mock_message)

        mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# Attachment-only message (no text content) — agentic loop must be skipped
# ---------------------------------------------------------------------------


class TestAttachmentOnlyMessage:
    @pytest.mark.asyncio
    async def test_empty_content_skips_agentic_loop(self):
        """on_message with elements but no text content must NOT call _agentic_loop."""
        el = _make_file_element()
        mock_message = MagicMock()
        mock_message.content = ""  # attachment-only, no text
        mock_message.elements = [el]

        with (
            patch("app.chat.settings") as mock_settings,
            patch("app.chat._process_upload_element", new_callable=AsyncMock, return_value="ctx"),
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat._agentic_loop", new_callable=AsyncMock) as mock_loop,
        ):
            mock_settings.rag_enabled = True
            mock_settings.conversation_history_limit = 10
            session_mock.get = MagicMock(return_value=[])

            from app.chat import on_message

            await on_message(mock_message)

        mock_loop.assert_not_called()


# ---------------------------------------------------------------------------
# AC8: process_upload receives correct arguments
# ---------------------------------------------------------------------------


class TestProcessUploadArgs:
    @pytest.mark.asyncio
    async def test_process_upload_called_with_correct_args(self):
        """AC8: process_upload() receives conn, filename, mime_type, file_bytes."""
        el = _make_file_element(name="report.pdf", mime="application/pdf", path="/tmp/report.pdf")
        fake_bytes = b"fake pdf content"
        mock_pool, mock_conn = _make_pool_mock()
        _app_db.pool = mock_pool

        with (
            patch("app.chat.cl.Message", return_value=AsyncMock()),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=len(fake_bytes)),
            patch("app.chat.asyncio") as mock_asyncio,
            patch("mcp_server.rag.processor.process_upload", new_callable=AsyncMock) as mock_proc,
        ):
            mock_settings.rag_max_upload_mb = 20
            mock_asyncio.to_thread = AsyncMock(return_value=fake_bytes)
            mock_proc.return_value = {"success": True, "chunk_count": 3}

            from app.chat import _process_upload_element

            await _process_upload_element(el)

        mock_proc.assert_called_once_with(
            conn=mock_conn,
            filename="report.pdf",
            mime_type="application/pdf",
            file_bytes=fake_bytes,
        )


# ---------------------------------------------------------------------------
# AC9: Pool unavailable
# ---------------------------------------------------------------------------


class TestPoolUnavailable:
    @pytest.mark.asyncio
    async def test_upload_skipped_when_pool_none(self):
        """AC9: When db pool is None, upload returns ERROR string with error message."""
        el = _make_file_element()
        _app_db.pool = None  # explicitly None
        sent_messages = []

        with (
            patch("app.chat.cl.Message", side_effect=lambda content: _capture_msg(content, sent_messages)),
            patch("app.chat.settings") as mock_settings,
            patch("os.path.getsize", return_value=1024),
        ):
            mock_settings.rag_max_upload_mb = 20

            from app.chat import _process_upload_element

            result = await _process_upload_element(el)

        assert result is not None and result.startswith("ERROR:")
        assert any("RAG database is not available" in m for m in sent_messages)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _capture_msg(content, sent_messages):
    """Create a mock Message that captures content and tracks sends."""
    msg = AsyncMock()
    msg.content = content
    sent_messages.append(content)
    return msg
