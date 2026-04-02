"""Tests for mcp_server/rag/store.py — pgvector storage and similarity search.

All asyncpg calls are mocked — no real database connection required.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_server.rag.chunker import Chunk
from mcp_server.rag.store import SearchResult, list_all_documents, search_similar, store_document


def _make_mock_conn():
    """Return a mock asyncpg connection with transaction support.

    asyncpg's conn.transaction() returns a Transaction object directly
    (not a coroutine) which is then used as an async context manager.
    We replicate this by setting transaction as a regular MagicMock (not
    AsyncMock) that returns an async-context-manager-compatible object.
    """
    conn = MagicMock()
    # transaction() must be a regular call (not awaited), returning an ACM
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    return conn


def _make_chunk(content: str, page_number: int | None = None, chunk_index: int = 0) -> Chunk:
    return Chunk(content=content, page_number=page_number, chunk_index=chunk_index)


# ---------------------------------------------------------------------------
# store_document tests
# ---------------------------------------------------------------------------


class TestStoreDocument:
    @pytest.mark.asyncio
    async def test_returns_uuid_string(self):
        """store_document returns a non-empty UUID string."""
        import uuid

        conn = _make_mock_conn()
        chunks = [_make_chunk("Drought data for Ceará.", page_number=1, chunk_index=0)]
        embeddings = [[0.1] * 384]

        result = await store_document(conn, "ceara.pdf", "application/pdf", chunks, embeddings, page_count=1)

        assert isinstance(result, str)
        uuid.UUID(result)  # raises if not valid UUID

    @pytest.mark.asyncio
    async def test_transaction_is_entered(self):
        """store_document wraps all inserts in a single transaction."""
        conn = _make_mock_conn()
        chunks = [_make_chunk("Some content.", chunk_index=0)]
        embeddings = [[0.2] * 384]

        await store_document(conn, "report.txt", "text/plain", chunks, embeddings)

        conn.transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_called_for_document_and_each_chunk(self):
        """store_document executes 1 + N inserts (document row + N chunk rows)."""
        conn = _make_mock_conn()
        n_chunks = 3
        chunks = [_make_chunk(f"Chunk {i}", chunk_index=i) for i in range(n_chunks)]
        embeddings = [[0.1 * i] * 384 for i in range(n_chunks)]

        await store_document(conn, "multi.txt", "text/plain", chunks, embeddings)

        # 1 document insert + 3 chunk inserts = 4 calls total
        assert conn.execute.call_count == 1 + n_chunks

    @pytest.mark.asyncio
    async def test_mismatched_chunks_embeddings_raises_value_error(self):
        """store_document raises ValueError when chunks and embeddings counts differ."""
        conn = _make_mock_conn()
        chunks = [_make_chunk("A"), _make_chunk("B")]
        embeddings = [[0.1] * 384]  # only 1, but 2 chunks

        with pytest.raises(ValueError, match="chunks.*embeddings"):
            await store_document(conn, "mismatch.txt", "text/plain", chunks, embeddings)

    @pytest.mark.asyncio
    async def test_empty_document_stores_zero_chunks(self):
        """store_document with no chunks inserts only the document row."""
        conn = _make_mock_conn()

        result = await store_document(conn, "empty.txt", "text/plain", [], [])

        assert isinstance(result, str)
        # Only the document INSERT was executed — no chunk inserts
        assert conn.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_page_count_passed_to_document_insert(self):
        """page_count value is forwarded to the document INSERT."""
        conn = _make_mock_conn()
        chunks = [_make_chunk("Page content.", page_number=1, chunk_index=0)]
        embeddings = [[0.5] * 384]

        await store_document(conn, "doc.pdf", "application/pdf", chunks, embeddings, page_count=10)

        # The first execute call is the document INSERT — check page_count arg
        first_call_args = conn.execute.call_args_list[0][0]  # positional args
        assert 10 in first_call_args


# ---------------------------------------------------------------------------
# search_similar tests
# ---------------------------------------------------------------------------


def _make_search_row(
    content: str = "Drought in Ceará.",
    filename: str = "ceara.pdf",
    page_number: int | None = 2,
    chunk_index: int = 0,
    document_id: str = "doc-uuid-1",
    upload_date: datetime | None = None,
    similarity: float = 0.85,
) -> dict:
    return {
        "content": content,
        "filename": filename,
        "page_number": page_number,
        "chunk_index": chunk_index,
        "document_id": document_id,
        "upload_date": upload_date or datetime(2026, 4, 1, 10, 0, 0),
        "similarity": similarity,
    }


class TestSearchSimilar:
    @pytest.mark.asyncio
    async def test_returns_search_result_objects(self):
        """search_similar maps DB rows to SearchResult dataclass instances."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[_make_search_row()])

        results = await search_similar(conn, query_embedding=[0.1] * 384)

        assert len(results) == 1
        assert isinstance(results[0], SearchResult)

    @pytest.mark.asyncio
    async def test_result_fields_mapped_correctly(self):
        """Each SearchResult field is populated from the corresponding DB column."""
        conn = _make_mock_conn()
        row = _make_search_row(
            content="CO2 emissions rising.",
            filename="report.pdf",
            page_number=5,
            chunk_index=3,
            document_id="abc-123",
            similarity=0.92,
        )
        conn.fetch = AsyncMock(return_value=[row])

        results = await search_similar(conn, query_embedding=[0.2] * 384)
        r = results[0]

        assert r.content == "CO2 emissions rising."
        assert r.source == "report.pdf"
        assert r.page_number == 5
        assert r.chunk_index == 3
        assert r.document_id == "abc-123"
        assert r.similarity_score == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_empty_result_set_returns_empty_list(self):
        """search_similar with no matching rows returns []."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[])

        results = await search_similar(conn, query_embedding=[0.3] * 384)

        assert results == []

    @pytest.mark.asyncio
    async def test_min_score_passed_as_query_param(self):
        """min_score is forwarded to the SQL query as a parameter."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[])

        await search_similar(conn, query_embedding=[0.1] * 384, min_score=0.7)

        call_args = conn.fetch.call_args[0]  # positional args to fetch()
        assert 0.7 in call_args

    @pytest.mark.asyncio
    async def test_limit_passed_as_query_param(self):
        """limit is forwarded to the SQL query as a parameter."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[])

        await search_similar(conn, query_embedding=[0.1] * 384, limit=10)

        call_args = conn.fetch.call_args[0]
        assert 10 in call_args

    @pytest.mark.asyncio
    async def test_multiple_results_returned(self):
        """search_similar returns all rows from the DB response."""
        conn = _make_mock_conn()
        rows = [_make_search_row(similarity=0.9), _make_search_row(similarity=0.75)]
        conn.fetch = AsyncMock(return_value=rows)

        results = await search_similar(conn, query_embedding=[0.1] * 384)

        assert len(results) == 2
        assert results[0].similarity_score == pytest.approx(0.9)
        assert results[1].similarity_score == pytest.approx(0.75)

    @pytest.mark.asyncio
    async def test_none_page_number_preserved(self):
        """Non-paginated documents (page_number=None) are preserved in results."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[_make_search_row(page_number=None)])

        results = await search_similar(conn, query_embedding=[0.1] * 384)

        assert results[0].page_number is None


# ---------------------------------------------------------------------------
# list_all_documents tests
# ---------------------------------------------------------------------------


def _make_doc_row(
    doc_id: str = "doc-uuid-1",
    filename: str = "climate.pdf",
    mime_type: str = "application/pdf",
    upload_date: datetime | None = None,
    page_count: int = 5,
    chunk_count: int = 20,
) -> dict:
    return {
        "id": doc_id,
        "filename": filename,
        "mime_type": mime_type,
        "upload_date": upload_date or datetime(2026, 4, 1, 9, 0, 0),
        "page_count": page_count,
        "chunk_count": chunk_count,
    }


class TestListAllDocuments:
    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        """list_all_documents returns a list of plain dicts."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[_make_doc_row()])

        result = await list_all_documents(conn)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    @pytest.mark.asyncio
    async def test_doc_fields_present(self):
        """Each doc dict contains all required metadata fields."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[_make_doc_row(filename="report.pdf", chunk_count=48)])

        result = await list_all_documents(conn)
        doc = result[0]

        assert doc["filename"] == "report.pdf"
        assert doc["chunk_count"] == 48
        assert "mime_type" in doc
        assert "upload_date" in doc
        assert "page_count" in doc

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self):
        """list_all_documents with no rows returns []."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[])

        result = await list_all_documents(conn)

        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_documents_returned(self):
        """list_all_documents returns all documents from the DB response."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(
            return_value=[
                _make_doc_row(filename="a.pdf"),
                _make_doc_row(filename="b.txt"),
                _make_doc_row(filename="c.csv"),
            ]
        )

        result = await list_all_documents(conn)

        assert len(result) == 3
        assert {doc["filename"] for doc in result} == {"a.pdf", "b.txt", "c.csv"}

    @pytest.mark.asyncio
    async def test_limit_passed_as_query_param(self):
        """limit is forwarded to the SQL query."""
        conn = _make_mock_conn()
        conn.fetch = AsyncMock(return_value=[])

        await list_all_documents(conn, limit=50)

        call_args = conn.fetch.call_args[0]
        assert 50 in call_args
