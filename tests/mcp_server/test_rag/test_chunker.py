"""Tests for mcp_server/rag/chunker.py — text extraction and chunking."""

from pathlib import Path

import pytest

from mcp_server.rag.chunker import Chunk, chunk_document

FIXTURES = Path(__file__).parent.parent / "fixtures" / "documents"


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

    def test_sample_pdf_fixture_exists(self):
        assert (FIXTURES / "sample.pdf").exists()

    def test_sample_pdf_chunk_extracts_text(self):
        """PDF fixture contains known text that survives extraction and chunking."""
        pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()
        chunks = chunk_document(pdf_bytes, "application/pdf")
        assert len(chunks) >= 1
        combined = " ".join(c.content for c in chunks).lower()
        # Known text inserted when the fixture was generated
        assert "brazil" in combined or "drought" in combined or "climate" in combined

    def test_sample_pdf_chunks_have_page_numbers(self):
        """PDF chunks carry page_number metadata."""
        pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()
        chunks = chunk_document(pdf_bytes, "application/pdf")
        assert len(chunks) >= 1
        assert all(c.page_number is not None for c in chunks)
