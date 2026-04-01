-- 002_rag_schema.sql: pgvector extension and RAG document storage
-- Requires: pgvector/pgvector:pg16 Docker image (set in docker-compose.yml)
-- Execution order: runs after 001_chainlit_schema.sql (alphanumeric init order)
-- Feature flag: DATA360_RAG_ENABLED=true required at app runtime (schema always created)

-- Enable pgvector extension (pre-compiled in pgvector/pgvector:pg16 image)
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: tracks uploaded files with metadata
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    TEXT NOT NULL,
    mime_type   TEXT NOT NULL,
    upload_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    page_count  INT,                              -- NULL for non-paginated formats (TXT, MD, CSV)
    metadata    JSONB DEFAULT '{}'::jsonb
);

-- Document chunks: text segments with 384-dim vector embeddings for similarity search
-- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (produces 384-dim vectors)
-- Cosine distance operator: <=> (requires vector_cosine_ops index)
-- Similarity = 1 - cosine_distance (higher score = more similar)
CREATE TABLE IF NOT EXISTS document_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    page_number INT,           -- NULL for non-paginated formats (TXT, MD, CSV)
    chunk_index INT NOT NULL,  -- 0-based position within parent document
    embedding   vector(384),   -- all-MiniLM-L6-v2: exactly 384 dimensions
    metadata    JSONB DEFAULT '{}'::jsonb
);

-- HNSW index for approximate nearest-neighbor cosine similarity search
-- HNSW chosen over IVFFlat: no minimum row requirement, better recall at query time
-- vector_cosine_ops → enables <=> operator used in search_documents tool
-- Future stories (8.2, 8.3) query: ORDER BY embedding <=> $1 LIMIT $2
CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
