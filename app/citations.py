"""Citation registry pipeline — deterministic citation extraction from MCP tool responses.

Builds a structured reference list from tool outputs server-side, ensuring
journalists can trust every source attribution. The LLM places [n] markers;
this module builds the reference list that explains what each marker means.
"""

import json
import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Language-adaptive reference list titles
_REFERENCE_TITLES: dict[str, str] = {
    "en": "References",
    "pt": "Referências",
    "es": "Referencias",
    "fr": "Références",
    "de": "Referenzen",
}


def _collapse_years(years: list[int]) -> str:
    """Collapse a sorted list of years into a compact range string.

    Examples:
        [2015, 2016, 2017, 2020, 2022] → "2015-2017, 2020, 2022"
        [2022] → "2022"
        [] → ""
    """
    if not years:
        return ""
    sorted_years = sorted(set(years))
    ranges: list[str] = []
    start = prev = sorted_years[0]
    for year in sorted_years[1:]:
        if year == prev + 1:
            prev = year
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = year
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def extract_references(tool_outputs: Sequence[str | None]) -> list[dict[str, Any]]:
    """Extract raw citation data from MCP tool result strings.

    Parses each tool output as JSON and looks for ``data`` arrays containing
    records with a ``CITATION_SOURCE`` field.  Returns a flat list of raw
    reference dicts (not yet deduplicated).

    Args:
        tool_outputs: Raw string outputs from MCP tool calls. ``None`` entries
            are silently skipped.

    Returns:
        List of dicts, each with keys like ``source``, ``indicator_code``,
        ``database_id``, ``year``, ``type``, and optionally document fields.
    """
    raw_refs: list[dict[str, Any]] = []

    for output in tool_outputs:
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(parsed, dict):
            continue

        # Skip error responses
        if not parsed.get("success", True):
            continue

        data = parsed.get("data")
        if not isinstance(data, list):
            continue

        for record in data:
            if not isinstance(record, dict):
                continue
            citation_source = record.get("CITATION_SOURCE")
            if not citation_source:
                continue

            # Determine if this is a document or API citation
            is_document = "similarity_score" in record or "page_number" in record

            if is_document:
                ref: dict[str, Any] = {
                    "source": citation_source,
                    "indicator_code": "",
                    "indicator_name": "",
                    "database_id": "",
                    "year": None,
                    "type": "document",
                    "filename": record.get("source", ""),
                    "upload_date": "",
                    "page": record.get("page_number"),
                    "chunk": record.get("chunk_index"),
                }
            else:
                indicator = record.get("INDICATOR", "")
                # Extract short code: WB_WDI_EN_ATM_CO2E_KT → EN_ATM_CO2E_KT
                db_id = record.get("DATABASE_ID", "")
                short_code = indicator
                if db_id and indicator.startswith(f"{db_id}_"):
                    short_code = indicator[len(db_id) + 1 :]

                year_raw = record.get("TIME_PERIOD")
                year = None
                if year_raw is not None:
                    try:
                        year = int(str(year_raw).strip())
                    except (ValueError, TypeError):
                        pass

                ref = {
                    "source": citation_source,
                    "indicator_code": short_code,
                    "indicator_name": record.get("COMMENT_TS", ""),
                    "database_id": db_id,
                    "year": year,
                    "type": "api",
                }

            raw_refs.append(ref)

    return raw_refs


def deduplicate_references(raw_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate raw references by (database_id, indicator_code) for API refs
    and (filename, page) for document refs. Merges year ranges.

    Args:
        raw_refs: Flat list from :func:`extract_references`.

    Returns:
        Deduplicated list with sequential ``id`` starting from 1.
    """
    # Use ordered dict approach to preserve insertion order
    groups: dict[tuple[str, ...], dict[str, Any]] = {}

    for ref in raw_refs:
        if ref["type"] == "document":
            key = ("doc", ref.get("filename", ""), str(ref.get("page", "")))
        else:
            key = ("api", ref["database_id"], ref["indicator_code"])

        if key not in groups:
            entry = {
                "source": ref["source"],
                "indicator_code": ref.get("indicator_code", ""),
                "indicator_name": ref.get("indicator_name", ""),
                "database_id": ref.get("database_id", ""),
                "years_set": set(),
                "type": ref["type"],
            }
            # Copy document-specific fields
            if ref["type"] == "document":
                entry["filename"] = ref.get("filename", "")
                entry["upload_date"] = ref.get("upload_date", "")
                entry["page"] = ref.get("page")
                entry["chunk"] = ref.get("chunk")
            groups[key] = entry

        # Accumulate years
        year = ref.get("year")
        if year is not None:
            groups[key]["years_set"].add(year)

        # Use first non-empty indicator_name
        if not groups[key]["indicator_name"] and ref.get("indicator_name"):
            groups[key]["indicator_name"] = ref["indicator_name"]

    # Build final list with sequential IDs
    result: list[dict[str, Any]] = []
    for idx, entry in enumerate(groups.values(), start=1):
        years_set = entry.pop("years_set")
        entry["id"] = idx
        entry["years"] = _collapse_years(sorted(years_set))
        result.append(entry)

    return result


def format_reference_list(references: list[dict[str, Any]], language: str = "en") -> str:
    """Format the deduplicated reference list as a markdown block.

    Args:
        references: Deduplicated list from :func:`deduplicate_references`.
        language: ISO 639-1 language code for the title.

    Returns:
        Formatted markdown string, or empty string if no references.
    """
    if not references:
        return ""

    title = _REFERENCE_TITLES.get(language, "References")
    lines = [f"**{title}**\n"]

    for ref in references:
        ref_id = ref["id"]
        if ref["type"] == "document":
            filename = ref.get("filename", "unknown")
            source = ref.get("source", filename)
            line = f"[{ref_id}] {source}"
        else:
            source = ref.get("source", "Unknown")
            indicator_name = ref.get("indicator_name", "")
            indicator_code = ref.get("indicator_code", "")
            years = ref.get("years", "")

            parts = [f"[{ref_id}]"]
            if indicator_name:
                parts.append(f'"{indicator_name}"')
            if indicator_code:
                parts.append(f"({indicator_code}),")
            parts.append(f"{source}")
            if years:
                parts.append(f"({years}).")
            else:
                parts.append(".")

            line = " ".join(parts)

        lines.append(line)

    return "\n".join(lines)
