"""Citation registry pipeline — deterministic citation extraction from MCP tool responses.

Builds a structured reference list from tool outputs server-side, ensuring
journalists can trust every source attribution. The LLM places [n] markers;
this module builds the reference list that explains what each marker means.
"""

import json
import logging
import re
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


def _parse_time_period_year(time_period: Any) -> int | None:
    """Parse a TIME_PERIOD value into a year integer.

    Handles the following formats from the Data360 API:
    - Simple year: ``"2022"`` → 2022
    - Quarter notation: ``"2022Q1"`` → 2022 (first 4 chars)
    - Range string: ``"2015-2022"`` → 2015 (start year only; use
      :func:`_parse_time_period_years` when all years in the range are needed)

    Returns ``None`` if the value cannot be parsed.
    """
    if time_period is None:
        return None
    raw = str(time_period).strip()
    # Take the first 4 characters which represent the year in all known formats
    year_str = raw[:4]
    try:
        return int(year_str)
    except (ValueError, TypeError):
        return None


def _parse_time_period_years(time_period: Any) -> list[int]:
    """Parse a TIME_PERIOD value into a list of year integers.

    Handles range strings like ``"2015-2022"`` by expanding to the full
    inclusive list of years (e.g. ``[2015, 2016, ..., 2022]``).
    For simple years and quarter notation, returns a single-element list.
    Returns an empty list if the value cannot be parsed.
    """
    if time_period is None:
        return []
    raw = str(time_period).strip()
    # Detect range format: starts with "YYYY-YYYY" (dash at position 4, digits at 5-8)
    if len(raw) >= 9 and raw[4] == "-" and raw[5:9].isdigit():
        start_str = raw[:4]
        end_str = raw[5:9]
        try:
            start = int(start_str)
            end = int(end_str)
            return list(range(start, end + 1))
        except (ValueError, TypeError):
            pass
    # Fall back to single year
    year = _parse_time_period_year(raw)
    return [year] if year is not None else []


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
                years = _parse_time_period_years(year_raw)

                ref = {
                    "source": citation_source,
                    "indicator_code": short_code,
                    "indicator_name": record.get("COMMENT_TS", ""),
                    "database_id": db_id,
                    "year": years[0] if years else None,  # backward compat
                    "years": years,
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

        # Accumulate years — support both legacy single-year and new multi-year list
        for year in ref.get("years", []):
            groups[key]["years_set"].add(year)
        # Also check legacy single year field for backward compat
        if not ref.get("years") and ref.get("year") is not None:
            groups[key]["years_set"].add(ref["year"])

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


# ---------------------------------------------------------------------------
# Marker sanitization — safety net for LLM narrative
# ---------------------------------------------------------------------------

# Matches [n] markers in prose. Anchored to ASCII [0-9] to avoid ValueError on
# Unicode digits (e.g., Arabic-Indic '[١]') that \d would match but int() rejects.
# Negative lookahead `(?!\()` preserves markdown-style link labels [n](url).
_CITATION_MARKER_RE = re.compile(r"\[([0-9]+)\](?!\()")

# Fenced code blocks (```...```) and inline code (`...`). Content inside these
# is masked out before marker stripping so code samples stay intact.
_CODE_SPAN_RE = re.compile(r"```[\s\S]*?```|`[^`\n]*`")

# Whitespace cleanup after stripping: collapse double spaces and remove the
# orphan space that would otherwise appear before punctuation.
_WS_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?])")
_WS_COLLAPSE_RE = re.compile(r" {2,}")


def strip_dangling_markers(text: str, max_id: int) -> tuple[str, list[int]]:
    """Drop ``[n]`` markers whose number is not in ``1..max_id``.

    Safety net for the case where the LLM emits sequential ``[1][2][3]`` for
    three tool calls covering the same indicator, but :func:`deduplicate_references`
    collapses them into a single ref — leaving ``[2]`` and ``[3]`` as orphans.
    This guarantees no dangling marker reaches the user, regardless of LLM behavior.

    Robustness guarantees:

    - Markdown link labels ``[n](url)`` are preserved via negative lookahead.
    - Content inside fenced code blocks ``` ``` ``` and inline ``` ` ``` spans
      is not processed — code samples stay intact.
    - Only ASCII digits are matched, so Unicode-digit markers (e.g. ``[١]``)
      never hit ``int()`` and cannot raise ``ValueError``.
    - After stripping, double spaces and spaces-before-punctuation are cleaned
      up so the narrative reads naturally.

    Returns:
        Tuple of (cleaned_text, list_of_dropped_ids). The list preserves the
        order and multiplicity of dropped ids for observability/logging.
    """
    dropped: list[int] = []

    def _sub(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if 1 <= n <= max_id:
            return m.group(0)
        dropped.append(n)
        return ""

    def _process_prose(prose: str) -> str:
        cleaned = _CITATION_MARKER_RE.sub(_sub, prose)
        cleaned = _WS_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
        cleaned = _WS_COLLAPSE_RE.sub(" ", cleaned)
        return cleaned

    # Split into prose regions (processed) and code spans (untouched).
    parts: list[str] = []
    last_end = 0
    for m in _CODE_SPAN_RE.finditer(text):
        parts.append(_process_prose(text[last_end : m.start()]))
        parts.append(m.group(0))
        last_end = m.end()
    parts.append(_process_prose(text[last_end:]))

    return "".join(parts), dropped
