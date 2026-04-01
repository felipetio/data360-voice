"""Upload pipeline orchestrator for RAG document processing.

Pipeline: extract text → chunk → generate embeddings → store in pgvector.
All errors are caught and returned as structured responses — no exceptions raised.
"""

import logging

import asyncpg

from mcp_server.rag.chunker import chunk_document
from mcp_server.rag.embeddings import generate_embeddings
from mcp_server.rag.store import store_document

logger = logging.getLogger(__name__)


async def process_upload(
    conn: asyncpg.Connection,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
) -> dict:
    """Orchestrate the full RAG pipeline for an uploaded document.

    Returns:
        Success: {"success": True, "document_id": "<uuid>", "chunk_count": N}
        Failure: {"success": False, "error": "<message>", "error_type": "processing_error"}
    """
    if not file_bytes:
        return {
            "success": False,
            "error": f"Empty file: '{filename}' contains no data",
            "error_type": "processing_error",
        }

    try:
        logger.info("Processing upload: '%s' (%s, %d bytes)", filename, mime_type, len(file_bytes))

        # Step 1: Extract and chunk text
        chunks = chunk_document(file_bytes, mime_type)
        if not chunks:
            return {
                "success": False,
                "error": f"No text could be extracted from '{filename}'",
                "error_type": "processing_error",
            }
        logger.debug("Extracted %d chunks from '%s'", len(chunks), filename)

        # Step 2: Generate embeddings
        texts = [chunk.content for chunk in chunks]
        embeddings = generate_embeddings(texts)
        logger.debug("Generated %d embeddings for '%s'", len(embeddings), filename)

        # Step 3: Determine page count (max page_number for PDFs, None otherwise)
        page_count: int | None = None
        if mime_type == "application/pdf":
            pages_with_number = [c.page_number for c in chunks if c.page_number is not None]
            page_count = max(pages_with_number) if pages_with_number else None

        # Step 4: Store in pgvector
        document_id = await store_document(conn, filename, mime_type, chunks, embeddings, page_count)

        logger.info("Successfully processed '%s' → doc_id=%s, chunks=%d", filename, document_id, len(chunks))
        return {
            "success": True,
            "document_id": document_id,
            "chunk_count": len(chunks),
        }

    except ValueError as exc:
        logger.warning("Validation error processing '%s': %s", filename, exc)
        return {
            "success": False,
            "error": str(exc),
            "error_type": "processing_error",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error processing '%s': %s", filename, exc, exc_info=True)
        return {
            "success": False,
            "error": f"Failed to process '{filename}': {exc}",
            "error_type": "processing_error",
        }
