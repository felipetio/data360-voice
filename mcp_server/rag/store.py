"""pgvector storage and similarity search for document chunks.

Depends on: db/002_rag_schema.sql (documents + document_chunks tables, HNSW index).
Uses asyncpg for all database operations.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from mcp_server.rag.chunker import Chunk

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    content: str
    source: str  # original filename
    page_number: int | None
    chunk_index: int
    similarity_score: float
    document_id: str
    upload_date: datetime


async def store_document(
    conn: asyncpg.Connection,
    filename: str,
    mime_type: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    page_count: int | None = None,
) -> str:
    """Insert document metadata and all chunks into pgvector.

    Returns the new document UUID.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have equal length")

    doc_id = str(uuid.uuid4())
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO documents (id, filename, mime_type, upload_date, page_count, metadata)
            VALUES ($1, $2, $3, NOW(), $4, '{}'::jsonb)
            """,
            doc_id,
            filename,
            mime_type,
            page_count,
        )

        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO document_chunks (id, document_id, content, page_number, chunk_index, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::vector, '{}'::jsonb)
                """,
                chunk_id,
                doc_id,
                chunk.content,
                chunk.page_number,
                chunk.chunk_index,
                str(embedding),  # asyncpg + pgvector: pass as string representation
            )

    logger.info("Stored document '%s' with %d chunks (id=%s)", filename, len(chunks), doc_id)
    return doc_id


async def search_similar(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    limit: int = 5,
    min_score: float = 0.3,
) -> list[SearchResult]:
    """Search document_chunks by cosine similarity.

    Converts pgvector cosine distance to similarity: similarity = 1 - distance.
    Filters results where similarity >= min_score.
    Returns results sorted by descending similarity score.
    """
    rows = await conn.fetch(
        """
        SELECT
            dc.content,
            d.filename,
            dc.page_number,
            dc.chunk_index,
            d.id::text AS document_id,
            d.upload_date,
            1 - (dc.embedding <=> $1::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE 1 - (dc.embedding <=> $1::vector) >= $2
        ORDER BY dc.embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_embedding),
        min_score,
        limit,
    )
    return [
        SearchResult(
            content=row["content"],
            source=row["filename"],
            page_number=row["page_number"],
            chunk_index=row["chunk_index"],
            similarity_score=float(row["similarity"]),
            document_id=row["document_id"],
            upload_date=row["upload_date"],
        )
        for row in rows
    ]


async def list_all_documents(
    conn: asyncpg.Connection,
    limit: int = 20,
) -> list[dict]:
    """Return all documents with metadata and chunk counts."""
    rows = await conn.fetch(
        """
        SELECT
            d.id::text,
            d.filename,
            d.mime_type,
            d.upload_date,
            d.page_count,
            COUNT(dc.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        GROUP BY d.id, d.filename, d.mime_type, d.upload_date, d.page_count
        ORDER BY d.upload_date DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(row) for row in rows]
