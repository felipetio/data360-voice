"""Static analysis tests for RAG database schema files.

These tests validate SQL file content without requiring a running database.
This approach works in CI without a PostgreSQL service.
"""

from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent.parent / "db"


class TestChainlitSchemaFile:
    """Verify 001_chainlit_schema.sql contains all required Chainlit tables."""

    def test_chainlit_schema_file_exists(self):
        assert (SCHEMA_DIR / "001_chainlit_schema.sql").exists(), (
            "db/001_chainlit_schema.sql not found — did you rename db/init.sql?"
        )

    def test_init_sql_removed(self):
        assert not (SCHEMA_DIR / "init.sql").exists(), (
            "db/init.sql still exists — remove after renaming to 001_chainlit_schema.sql"
        )

    def test_chainlit_tables_present(self):
        content = (SCHEMA_DIR / "001_chainlit_schema.sql").read_text()
        for table in ["users", "threads", "steps", "elements", "feedbacks"]:
            assert (
                f'CREATE TABLE IF NOT EXISTS "{table}"' in content or f"CREATE TABLE IF NOT EXISTS {table}" in content
            ), f"Chainlit table '{table}' missing from 001_chainlit_schema.sql"


class TestRagSchemaFile:
    """Verify 002_rag_schema.sql defines all required RAG structures."""

    def test_rag_schema_file_exists(self):
        assert (SCHEMA_DIR / "002_rag_schema.sql").exists(), "db/002_rag_schema.sql not found"

    def test_vector_extension_enabled(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE EXTENSION IF NOT EXISTS vector" in content, (
            "pgvector extension declaration missing from 002_rag_schema.sql"
        )

    def test_documents_table_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS documents" in content

    def test_document_chunks_table_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS document_chunks" in content

    def test_embedding_column_correct_dimensions(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "vector(384)" in content, (
            "embedding column must be vector(384) — all-MiniLM-L6-v2 produces 384 dimensions"
        )

    def test_hnsw_index_defined(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "USING hnsw" in content, "HNSW index missing — required for cosine similarity search"

    def test_cosine_ops_index(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "vector_cosine_ops" in content, "vector_cosine_ops required for <=> cosine distance operator"

    def test_fk_document_id_cascade(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        assert "ON DELETE CASCADE" in content, "document_chunks.document_id FK must cascade delete"

    def test_documents_required_columns(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        for col in ["filename", "mime_type", "upload_date", "page_count", "metadata"]:
            assert col in content, f"documents table missing column: {col}"

    def test_document_chunks_required_columns(self):
        content = (SCHEMA_DIR / "002_rag_schema.sql").read_text()
        for col in ["document_id", "content", "page_number", "chunk_index", "embedding", "metadata"]:
            assert col in content, f"document_chunks table missing column: {col}"


class TestDbSchemaOrdering:
    """Verify file naming ensures correct init script execution order."""

    def test_schema_files_have_numeric_prefix(self):
        sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
        assert len(sql_files) == 2, f"Expected 2 SQL files in db/, found: {[f.name for f in sql_files]}"

    def test_chainlit_schema_runs_first(self):
        sql_files = sorted(SCHEMA_DIR.glob("*.sql"))
        assert sql_files[0].name == "001_chainlit_schema.sql"
        assert sql_files[1].name == "002_rag_schema.sql"
