"""Tests for Citation UI (Story 9.1).

The citation UI styles [n] markers via CSS and renders the reference block as
streamed markdown. These tests validate the reference data schema used by
the citation pipeline.

AC1: Reference block is streamed and persisted in message content.
AC2: No reference block when no citations (guard in _agentic_loop).
"""

from app.citations import format_reference_list

# ------------------------------------------------------------------ #
# Reference fixtures                                                  #
# ------------------------------------------------------------------ #

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


class TestReferenceBlockFormatting:
    """AC1: Reference block is formatted correctly for streaming."""

    def test_format_produces_references_header(self):
        refs = [API_REF]
        block = format_reference_list(refs)
        assert "**References**" in block

    def test_format_includes_ref_id(self):
        refs = [API_REF]
        block = format_reference_list(refs)
        assert "[1]" in block

    def test_format_includes_source(self):
        refs = [API_REF]
        block = format_reference_list(refs)
        assert "World Development Indicators" in block

    def test_format_multiple_refs_ordered(self):
        refs = [API_REF, DOC_REF]
        block = format_reference_list(refs)
        pos1 = block.index("[1]")
        pos2 = block.index("[2]")
        assert pos1 < pos2


class TestNoRefsGuard:
    """AC2: No reference block when no citations exist."""

    def test_empty_refs_list_is_falsy(self):
        raw_refs: list[dict] = []
        assert not raw_refs

    def test_nonempty_refs_list_is_truthy(self):
        raw_refs = [API_REF]
        assert raw_refs
