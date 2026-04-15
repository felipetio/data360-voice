"""Tests for Citation UI Python-side changes (Story 9.1).

The UI story is primarily frontend (JS/CSS). The only Python-side change is the
injection of a hidden <span class="citation-data" data-citations='...'> sentinel
into the message text when citations are present. This module tests that sentinel.

AC1: Sentinel is present when citations exist → JS can read it.
AC2: Sentinel is NOT present when no citations → no interactive markers possible.
"""

import json
import re

from app.chat import _CITATION_DATA_TPL

# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

SENTINEL_RE = re.compile(r'<span class="citation-data" data-citations=\'(?P<json>[^\']+)\' aria-hidden="true"></span>')


def make_sentinel(refs: list[dict]) -> str:
    """Produce the sentinel string as app/chat.py would."""
    refs_json = json.dumps(refs, ensure_ascii=False)
    return "\n" + _CITATION_DATA_TPL.format(refs_json)


def extract_refs_from_sentinel(sentinel: str) -> list[dict] | None:
    """Parse the citation JSON from a sentinel string (mirrors what JS does)."""
    m = SENTINEL_RE.search(sentinel)
    if not m:
        return None
    return json.loads(m.group("json"))


# ------------------------------------------------------------------ #
# Tests for the sentinel template constant                            #
# ------------------------------------------------------------------ #


class TestCitationSentinelTemplate:
    """AC1: Sentinel is embedded in message text when citations exist."""

    def test_template_contains_class_name(self):
        """The sentinel must use class 'citation-data' for JS targeting."""
        assert "citation-data" in _CITATION_DATA_TPL

    def test_template_contains_data_citations_attr(self):
        """The sentinel must have 'data-citations' attribute for JSON storage."""
        assert "data-citations" in _CITATION_DATA_TPL

    def test_template_has_aria_hidden(self):
        """The sentinel must be hidden from screen readers."""
        assert 'aria-hidden="true"' in _CITATION_DATA_TPL

    def test_template_is_span_element(self):
        """Must be a <span> so it doesn't break markdown paragraph flow."""
        assert _CITATION_DATA_TPL.strip().startswith("<span")
        assert "</span>" in _CITATION_DATA_TPL


class TestSentinelGeneration:
    """AC1: Sentinel correctly encodes citation data for JS consumption."""

    API_REF = {
        "id": 1,
        "type": "api",
        "source": "World Development Indicators",
        "indicator_code": "EN.ATM.CO2E.KT",
        "indicator_name": "CO2 emissions, total (kt)",
        "database_id": "WB_WDI",
        "years": "2015-2022",
    }

    DOC_REF = {
        "id": 2,
        "type": "document",
        "source": "report.pdf (uploaded 2026-04-01), p. 12",
        "filename": "report.pdf",
        "upload_date": "2026-04-01",
        "page": 12,
    }

    def test_single_api_ref_roundtrip(self):
        """Sentinel JSON must survive a serialise→parse roundtrip."""
        refs = [self.API_REF]
        sentinel = make_sentinel(refs)
        parsed = extract_refs_from_sentinel(sentinel)

        assert parsed is not None
        assert len(parsed) == 1
        assert parsed[0]["id"] == 1
        assert parsed[0]["type"] == "api"
        assert parsed[0]["indicator_code"] == "EN.ATM.CO2E.KT"
        assert parsed[0]["years"] == "2015-2022"

    def test_document_ref_roundtrip(self):
        """Document-type refs preserve filename, upload_date, page."""
        refs = [self.DOC_REF]
        sentinel = make_sentinel(refs)
        parsed = extract_refs_from_sentinel(sentinel)

        assert parsed is not None
        ref = parsed[0]
        assert ref["type"] == "document"
        assert ref["filename"] == "report.pdf"
        assert ref["upload_date"] == "2026-04-01"
        assert ref["page"] == 12

    def test_multiple_refs_preserved_in_order(self):
        """All refs must be preserved in order (JS relies on array index for lookup)."""
        refs = [self.API_REF, self.DOC_REF]
        sentinel = make_sentinel(refs)
        parsed = extract_refs_from_sentinel(sentinel)

        assert parsed is not None
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1
        assert parsed[1]["id"] == 2

    def test_sentinel_starts_with_newline(self):
        """The sentinel is prefixed with \\n so it sits after the ref block."""
        refs = [self.API_REF]
        sentinel = make_sentinel(refs)
        assert sentinel.startswith("\n")

    def test_special_chars_escaped_as_valid_json(self):
        """Refs with special chars (quotes, Unicode) must produce valid JSON."""
        refs = [
            {
                "id": 1,
                "type": "api",
                "source": 'World Bank "Dev" Indicators',
                "indicator_name": "CO₂ emissions",
                "indicator_code": "EN.ATM",
                "database_id": "WB",
                "years": "2020",
            }
        ]
        sentinel = make_sentinel(refs)
        parsed = extract_refs_from_sentinel(sentinel)

        assert parsed is not None
        assert parsed[0]["source"] == 'World Bank "Dev" Indicators'

    def test_unicode_preserved(self):
        """Unicode characters in source names must survive the roundtrip."""
        refs = [
            {
                "id": 1,
                "type": "api",
                "source": "Banco Mundial – Indicadores",
                "indicator_name": "Emisiones de CO₂",
                "indicator_code": "EN.ATM.CO2E.KT",
                "database_id": "WB_WDI",
                "years": "2022",
            }
        ]
        sentinel = make_sentinel(refs)
        parsed = extract_refs_from_sentinel(sentinel)

        assert parsed is not None
        assert "Banco Mundial" in parsed[0]["source"]
        assert "CO₂" in parsed[0]["indicator_name"]


class TestNoSentinelWhenNoCitations:
    """AC2: When no citations, no sentinel is injected (handled upstream in app/chat.py).

    The guard `if raw_refs:` in _agentic_loop ensures this. We verify the
    sentinel template itself does NOT embed anything meaningful for an empty list,
    so even if called with [] it's clearly empty.
    """

    def test_empty_refs_produces_empty_json_array(self):
        """If sentinel were called with empty refs, JS would get []."""
        sentinel = make_sentinel([])
        parsed = extract_refs_from_sentinel(sentinel)
        assert parsed == []

    def test_sentinel_only_present_in_message_when_refs_exist(self):
        """Simulate the guard logic: sentinel only appended when raw_refs truthy."""
        final_text = "Some clarification answer."
        raw_refs: list[dict] = []  # no citations

        # Simulate guard from _agentic_loop
        if raw_refs:
            refs = raw_refs  # would call deduplicate_references in real code
            final_text += "\n" + make_sentinel(refs)

        # AC2: no sentinel in text
        assert "citation-data" not in final_text
        assert SENTINEL_RE.search(final_text) is None
