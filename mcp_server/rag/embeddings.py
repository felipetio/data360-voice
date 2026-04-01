"""Embedding generation using sentence-transformers/all-MiniLM-L6-v2.

Model produces 384-dimension float vectors. Singleton pattern: model loaded once at
first use and cached for the server lifetime.
"""

import logging
import threading

logger = logging.getLogger(__name__)

_embedder = None  # module-level singleton
_embedder_lock = threading.Lock()


def get_embedder():
    """Return the cached SentenceTransformer model, loading it on first call.

    Thread-safe: uses a double-checked locking pattern so concurrent callers
    don't trigger multiple model loads.
    """
    global _embedder  # noqa: PLW0603
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            logger.info("Loading sentence-transformers/all-MiniLM-L6-v2 (384 dims)…")
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded and cached.")
    return _embedder


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate 384-dimension embeddings for a list of text strings.

    Args:
        texts: List of strings to embed.

    Returns:
        List of 384-dimension float vectors, one per input string.
    """
    if not texts:
        return []
    model = get_embedder()
    embeddings = model.encode(texts, show_progress_bar=False)
    return [emb.tolist() for emb in embeddings]


def generate_query_embedding(query: str) -> list[float]:
    """Generate a single 384-dimension embedding for a search query."""
    results = generate_embeddings([query])
    return results[0]
