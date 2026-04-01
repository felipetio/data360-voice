"""CITATION_SOURCE formatting for RAG search results.

Patterns (AC4):
  PDF:      "{filename} (uploaded {date}), p. {page_number}"
  TXT/MD/CSV: "{filename} (uploaded {date}), chunk {chunk_index}"
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"


def _format_date(upload_date) -> str:
    """Format upload_date as YYYY-MM-DD string (handles datetime or string)."""
    if isinstance(upload_date, datetime):
        return upload_date.strftime("%Y-%m-%d")
    # Already a string (e.g. from asyncpg row serialization)
    return str(upload_date)[:10]


def build_citation_source(
    filename: str,
    mime_type: str,
    upload_date,
    page_number: int | None,
    chunk_index: int,
) -> str:
    """Build a CITATION_SOURCE string for a search result chunk."""
    date_str = _format_date(upload_date)
    base = f"{filename} (uploaded {date_str})"

    if mime_type == _PDF_MIME and page_number is not None:
        return f"{base}, p. {page_number}"
    return f"{base}, chunk {chunk_index}"
