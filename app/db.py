"""Application-level asyncpg connection pool.

The pool is created once during FastAPI lifespan startup (app/main.py) when
DATA360_RAG_ENABLED=true, and torn down on shutdown. Set to None when RAG is
disabled to keep the import cost zero.

Usage in other modules (lazy import to avoid loading asyncpg when RAG is off):
    from app.db import pool as db_pool
    async with db_pool.acquire() as conn:
        ...
"""

from __future__ import annotations

# Module-level pool reference — set during application lifespan startup.
# Type: asyncpg.Pool | None
pool = None
