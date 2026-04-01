"""Tests for MCP RAG tools — search_documents and list_documents."""

import importlib
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.rag.citation import build_citation_source  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_server_with_rag_enabled():
    """Re-import mcp_server.server with RAG_ENABLED=True so the conditional
    tool registration block actually runs, regardless of the env var set in CI.
    """
    import mcp_server.config as cfg

    original = cfg.RAG_ENABLED
    cfg.RAG_ENABLED = True
    # Remove cached module so the if-block re-executes on next import
    if "mcp_server.server" in sys.modules:
        del sys.modules["mcp_server.server"]
    module = importlib.import_module("mcp_server.server")
    # Restore so other tests are unaffected
    cfg.RAG_ENABLED = original
    return module


# ---------------------------------------------------------------------------
# Citation tests (no RAG flag dependency)
# ---------------------------------------------------------------------------


class TestBuildCitationSource:
    def test_pdf_with_page_number(self):
        dt = datetime(2026, 4, 1, 12, 0, 0)
        result = build_citation_source("report.pdf", dt, page_number=3, chunk_index=5)
        assert result == "report.pdf (uploaded 2026-04-01), p. 3"

    def test_txt_no_page_number(self):
        dt = datetime(2026, 4, 1, 12, 0, 0)
        result = build_citation_source("data.txt", dt, page_number=None, chunk_index=2)
        assert result == "data.txt (uploaded 2026-04-01), chunk 2"

    def test_csv_no_page_number(self):
        dt = datetime(2026, 3, 15, 8, 0, 0)
        result = build_citation_source("indicators.csv", dt, page_number=None, chunk_index=0)
        assert result == "indicators.csv (uploaded 2026-03-15), chunk 0"

    def test_md_no_page_number(self):
        dt = datetime(2026, 1, 10, 0, 0, 0)
        result = build_citation_source("notes.md", dt, page_number=None, chunk_index=7)
        assert result == "notes.md (uploaded 2026-01-10), chunk 7"

    def test_page_number_zero_treated_as_set(self):
        dt = datetime(2026, 4, 1)
        # page_number=0 is falsy but valid — must NOT fall back to chunk format
        result = build_citation_source("doc.pdf", dt, page_number=0, chunk_index=0)
        assert "p. 0" in result

    def test_date_object_accepted(self):
        from datetime import date

        d = date(2026, 6, 1)
        result = build_citation_source("report.pdf", d, page_number=1, chunk_index=0)
        assert "2026-06-01" in result


# ---------------------------------------------------------------------------
# search_documents tests
# ---------------------------------------------------------------------------


class TestSearchDocumentsTool:
    @pytest.fixture
    def mock_search_result(self):
        result = MagicMock()
        result.content = "Drought conditions in Ceará increased significantly."
        result.source = "ceara_report.pdf"
        result.page_number = 4
        result.chunk_index = 2
        result.similarity_score = 0.87
        result.document_id = "abc-123"
        result.upload_date = datetime(2026, 4, 1, 10, 0, 0)
        return result

    @pytest.mark.asyncio
    async def test_search_returns_results(self, mock_search_result):
        # Patch in the source modules (where the names actually live at call time)
        with (
            patch("mcp_server.rag.embeddings.generate_query_embedding", return_value=[0.1] * 384),
            patch("mcp_server.rag.store.search_similar", new_callable=AsyncMock, return_value=[mock_search_result]),
        ):
            srv = _reload_server_with_rag_enabled()

            mock_pool = MagicMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
            srv._db_pool = mock_pool

            result = await srv.search_documents("drought Ceará", limit=5)

        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["source"] == "ceara_report.pdf"
        assert result["data"][0]["similarity_score"] == 0.87
        assert result["data"][0]["CITATION_SOURCE"] == "ceara_report.pdf (uploaded 2026-04-01), p. 4"
        assert result["data"][0]["upload_date"] == "2026-04-01T10:00:00"

    @pytest.mark.asyncio
    async def test_search_returns_empty_list(self):
        with (
            patch("mcp_server.rag.embeddings.generate_query_embedding", return_value=[0.1] * 384),
            patch("mcp_server.rag.store.search_similar", new_callable=AsyncMock, return_value=[]),
        ):
            srv = _reload_server_with_rag_enabled()

            mock_pool = MagicMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
            srv._db_pool = mock_pool

            result = await srv.search_documents("no match query")

        assert result["success"] is True
        assert result["data"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_search_handles_exception(self):
        with patch("mcp_server.rag.embeddings.generate_query_embedding", side_effect=Exception("embed failed")):
            srv = _reload_server_with_rag_enabled()
            result = await srv.search_documents("drought")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "embed failed" in result["error"]


# ---------------------------------------------------------------------------
# list_documents tests
# ---------------------------------------------------------------------------


class TestListDocumentsTool:
    @pytest.fixture
    def mock_doc(self):
        return {
            "id": "doc-uuid-1",
            "filename": "climate_report.pdf",
            "mime_type": "application/pdf",
            "upload_date": datetime(2026, 4, 1, 9, 0, 0),
            "page_count": 12,
            "chunk_count": 48,
        }

    @pytest.mark.asyncio
    async def test_list_returns_documents(self, mock_doc):
        with patch("mcp_server.rag.store.list_all_documents", new_callable=AsyncMock, return_value=[mock_doc]):
            srv = _reload_server_with_rag_enabled()

            mock_pool = MagicMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
            srv._db_pool = mock_pool

            result = await srv.list_documents(limit=20)

        assert result["success"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["filename"] == "climate_report.pdf"
        assert result["data"][0]["upload_date"] == "2026-04-01T09:00:00"
        assert result["data"][0]["chunk_count"] == 48

    @pytest.mark.asyncio
    async def test_list_handles_exception(self):
        with patch(
            "mcp_server.rag.store.list_all_documents",
            new_callable=AsyncMock,
            side_effect=Exception("pool exhausted"),
        ):
            srv = _reload_server_with_rag_enabled()

            mock_pool = MagicMock()
            mock_conn = AsyncMock()
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
            srv._db_pool = mock_pool

            result = await srv.list_documents()

        assert result["success"] is False
        assert result["error_type"] == "api_error"


# ---------------------------------------------------------------------------
# Feature flag test
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_rag_disabled_existing_tools_unaffected(self):
        """When RAG_ENABLED=False, existing tools must still be present."""
        import mcp_server.server as srv

        # Ensure we have a clean module loaded with current flag state
        assert hasattr(srv, "search_indicators")
        assert hasattr(srv, "get_data")
        assert hasattr(srv, "get_metadata")
        assert hasattr(srv, "list_indicators")

    def test_rag_enabled_tools_registered(self):
        """When RAG_ENABLED=True, search_documents and list_documents must exist."""
        srv = _reload_server_with_rag_enabled()
        assert hasattr(srv, "search_documents")
        assert hasattr(srv, "list_documents")
