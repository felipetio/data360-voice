"""Tests for mcp_server/rag/processor.py — upload pipeline orchestration."""

from unittest.mock import AsyncMock, patch

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
        with (
            patch("mcp_server.rag.processor.generate_embeddings") as mock_embed,
            patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store,
        ):
            # Return one embedding per chunk (side_effect so we can return variable count)
            mock_embed.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
            mock_store.return_value = "test-doc-uuid"

            result = await process_upload(mock_conn, "report.txt", "text/plain", content)

        assert result["success"] is True
        assert result["document_id"] == "test-doc-uuid"
        assert result["chunk_count"] >= 1

    @pytest.mark.asyncio
    async def test_successful_md_processing(self, mock_conn):
        content = b"# Report\n\nClimate data from Brazil shows rising temperatures.\n" * 20
        with (
            patch("mcp_server.rag.processor.generate_embeddings") as mock_embed,
            patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store,
        ):
            mock_embed.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
            mock_store.return_value = "md-doc-uuid"

            result = await process_upload(mock_conn, "report.md", "text/markdown", content)

        assert result["success"] is True
        assert result["document_id"] == "md-doc-uuid"

    @pytest.mark.asyncio
    async def test_store_exception_returns_error(self, mock_conn):
        content = b"some text content " * 10
        with (
            patch("mcp_server.rag.processor.generate_embeddings") as mock_embed,
            patch("mcp_server.rag.processor.store_document", new_callable=AsyncMock) as mock_store,
        ):
            mock_embed.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
            mock_store.side_effect = Exception("DB connection failed")

            result = await process_upload(mock_conn, "report.txt", "text/plain", content)

        assert result["success"] is False
        assert result["error_type"] == "processing_error"
        assert "report.txt" in result["error"]
