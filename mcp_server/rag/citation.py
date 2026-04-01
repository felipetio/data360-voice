"""Citation source builder for RAG search results.

Formats document chunk references into human-readable citation strings
suitable for inclusion in LLM responses.
"""

from datetime import date, datetime


def build_citation_source(
    source: str,
    upload_date: datetime | date,
    page_number: int | None,
    chunk_index: int,
) -> str:
    """Build a CITATION_SOURCE string for a document chunk.

    PDF chunks (page_number is not None):
        "{filename} (uploaded {YYYY-MM-DD}), p. {page_number}"

    TXT/MD/CSV chunks (page_number is None):
        "{filename} (uploaded {YYYY-MM-DD}), chunk {chunk_index}"

    Args:
        source: Original filename (e.g. "report.pdf").
        upload_date: Document upload timestamp (datetime or date).
        page_number: Page number for PDF chunks; None for non-paginated formats.
        chunk_index: 0-based chunk position within the document.

    Returns:
        Formatted citation string.
    """
    if isinstance(upload_date, datetime):
        date_str = upload_date.date().isoformat()
    else:
        date_str = upload_date.isoformat()

    prefix = f"{source} (uploaded {date_str})"

    if page_number is not None:
        return f"{prefix}, p. {page_number}"
    return f"{prefix}, chunk {chunk_index}"
