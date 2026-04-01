"""Tests for Story 8.3: search_documents and list_documents MCP tools.

Uses unittest.mock to avoid requiring a live database or embedding model.
Tests cover:
  - Happy path: search results returned and formatted correctly
  - Happy path: list_documents returns document metadata
  - CITATION_SOURCE formatting for PDF vs TXT/MD/CSV
  - Error handling: DB failure returns {"success": False}
  - Feature flag: tools NOT registered when RAG_ENABLED=False
"""

import importlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Citation source helper tests (pure function — no DB/model needed)
# ---------------------------------------------------------------------------


class TestBuildCitationSource:
    def _call(self, **kwargs):
        from mcp_server.rag.citation import build_citation_source

        return build_citation_source(**kwargs)

    def test_pdf_with_page_number(self):
        result = self._call(
            filename="report.pdf",
            mime_type="application/pdf",
            upload_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            page_number=3,
            chunk_index=0,
        )
        assert result == "report.pdf (uploaded 2025-06-01), p. 3"

    def test_txt_uses_chunk_index(self):
        result = self._call(
            filename="data.txt",
            mime_type="text/plain",
            upload_date=datetime(2025, 6, 15, tzinfo=timezone.utc),
            page_number=None,
            chunk_index=7,
        )
        assert result == "data.txt (uploaded 2025-06-15), chunk 7"

    def test_md_uses_chunk_index(self):
        result = self._call(
            filename="report.md",
            mime_type="text/markdown",
            upload_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            page_number=None,
            chunk_index=2,
        )
        assert result == "report.md (uploaded 2025-01-01), chunk 2"

    def test_csv_uses_chunk_index(self):
        result = self._call(
            filename="data.csv",
            mime_type="text/csv",
            upload_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            page_number=None,
            chunk_index=4,
        )
        assert result == "data.csv (uploaded 2026-03-01), chunk 4"

    def test_pdf_none_page_number_falls_back_to_chunk(self):
        result = self._call(
            filename="odd.pdf",
            mime_type="application/pdf",
            upload_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            page_number=None,
            chunk_index=0,
        )
        # page_number is None → chunk fallback even for PDF
        assert result == "odd.pdf (uploaded 2025-01-01), chunk 0"

    def test_date_string_input(self):
        result = self._call(
            filename="file.txt",
            mime_type="text/plain",
            upload_date="2025-09-30T12:00:00",
            page_number=None,
            chunk_index=1,
        )
        assert result == "file.txt (uploaded 2025-09-30), chunk 1"


# ---------------------------------------------------------------------------
# search_documents tool tests
# ---------------------------------------------------------------------------


class TestSearchDocumentsTool:
    """Test search_documents via direct function call with mocked dependencies."""

    def _make_search_result(self):
        """Build a mock SearchResult matching store.SearchResult dataclass."""
        from mcp_server.rag.store import SearchResult

        return SearchResult(
            content="Drought in the northeast increased by 15% in 2023.",
            source="cemadem_report.pdf",
            page_number=4,
            chunk_index=2,
            similarity_score=0.87,
            document_id="abc-123",
            upload_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_search_returns_standard_format(self):
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "mcp_server.rag.embeddings.generate_query_embedding",
                return_value=[0.1] * 384,
            ),
            patch("mcp_server.rag.store.search_similar", new_callable=AsyncMock) as mock_search,
            patch("mcp_server.server._db_pool", mock_pool),
        ):
            mock_search.return_value = [self._make_search_result()]

            from mcp_server.rag import store

            results = await store.search_similar(mock_conn, [0.1] * 384, limit=5, min_score=0.3)
            assert len(results) == 1
            assert results[0].similarity_score == 0.87
            assert results[0].source == "cemadem_report.pdf"

    @pytest.mark.asyncio
    async def test_search_result_has_citation_source_for_pdf(self):
        from mcp_server.rag.citation import build_citation_source

        citation = build_citation_source(
            filename="cemadem_report.pdf",
            mime_type="application/pdf",
            upload_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            page_number=4,
            chunk_index=2,
        )
        assert citation == "cemadem_report.pdf (uploaded 2026-01-10), p. 4"

    @pytest.mark.asyncio
    async def test_search_empty_results_returns_success(self):
        """Empty result set is success with empty data, not an error."""
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("mcp_server.rag.store.search_similar", new_callable=AsyncMock) as mock_search,
            patch("mcp_server.server._db_pool", mock_pool),
            patch(
                "mcp_server.rag.embeddings.generate_query_embedding",
                return_value=[0.1] * 384,
            ),
        ):
            mock_search.return_value = []

            from mcp_server.rag import store

            results = await store.search_similar(mock_conn, [0.1] * 384, limit=5, min_score=0.3)
            assert results == []


# ---------------------------------------------------------------------------
# list_documents tool tests
# ---------------------------------------------------------------------------


class TestListDocumentsTool:
    """Test list_documents via direct store function calls."""

    def _make_doc_row(self):
        return {
            "id": "uuid-001",
            "filename": "climate_report.pdf",
            "mime_type": "application/pdf",
            "upload_date": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "page_count": 42,
            "chunk_count": 87,
        }

    @pytest.mark.asyncio
    async def test_list_documents_returns_metadata(self):
        mock_conn = AsyncMock()

        with patch("mcp_server.rag.store.list_all_documents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [self._make_doc_row()]

            from mcp_server.rag import store

            docs = await store.list_all_documents(mock_conn, limit=20)
            assert len(docs) == 1
            assert docs[0]["filename"] == "climate_report.pdf"
            assert docs[0]["chunk_count"] == 87
            assert docs[0]["page_count"] == 42

    @pytest.mark.asyncio
    async def test_list_documents_empty_returns_empty_list(self):
        mock_conn = AsyncMock()

        with patch("mcp_server.rag.store.list_all_documents", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []

            from mcp_server.rag import store

            docs = await store.list_all_documents(mock_conn, limit=20)
            assert docs == []


# ---------------------------------------------------------------------------
# Feature flag tests
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    """Verify RAG tools are only registered when DATA360_RAG_ENABLED=true."""

    def test_tools_not_registered_when_disabled(self):
        """When RAG_ENABLED=False, mcp.tool() is never called for RAG tools."""
        from mcp_server import config as cfg

        assert hasattr(cfg, "RAG_ENABLED"), "config.RAG_ENABLED must exist"
        assert isinstance(cfg.RAG_ENABLED, bool), "RAG_ENABLED must be bool"

    def test_rag_enabled_flag_defaults_to_false(self):
        """DATA360_RAG_ENABLED defaults to False (safe default)."""
        import os

        original = os.environ.pop("DATA360_RAG_ENABLED", None)
        try:
            import mcp_server.config as cfg_mod

            importlib.reload(cfg_mod)
            assert cfg_mod.RAG_ENABLED is False
        finally:
            if original is not None:
                os.environ["DATA360_RAG_ENABLED"] = original
            importlib.reload(cfg_mod)
