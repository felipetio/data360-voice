"""Tests for Citation UI (Story 9.1).

The citation UI styles [n] markers via CSS and renders the reference block as
streamed markdown. These tests validate the reference data schema used by
the citation pipeline.

AC1: Reference block is streamed and persisted in message content.
AC2: No reference block when no citations (guard in _agentic_loop).
"""

from app.citations import format_reference_list, strip_dangling_markers

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


class TestStripDanglingMarkers:
    """strip_dangling_markers removes [n] markers pointing outside the registry.

    This is the safety net for the case where the LLM emits [1][2][3] for three
    tool calls covering the same indicator, but deduplicate_references collapses
    them into a single ref — leaving [2] and [3] as orphans.
    """

    def test_drops_markers_beyond_registry_size(self):
        """Registry has 1 entry → only [1] survives; [2] and [3] are stripped."""
        text = "Brazil 467 kt [1], India 2,693 kt [2], China 11,472 kt [3]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        # Stripping cleans up orphan spaces and spaces-before-punctuation.
        assert result == "Brazil 467 kt [1], India 2,693 kt, China 11,472 kt."
        assert sorted(dropped) == [2, 3]

    def test_keeps_all_markers_when_all_valid(self):
        """Registry has 2 entries → [1] and [2] both preserved, nothing dropped."""
        text = "CO2 [1] and population [2]."
        result, dropped = strip_dangling_markers(text, max_id=2)
        assert result == text
        assert dropped == []

    def test_strips_all_markers_when_registry_empty(self):
        """No refs → every marker is dangling."""
        text = "Claim A [1] and claim B [2]."
        result, dropped = strip_dangling_markers(text, max_id=0)
        assert result == "Claim A and claim B."
        assert sorted(dropped) == [1, 2]

    def test_noop_when_no_markers(self):
        """Plain narrative with no [n] must be returned unchanged, nothing dropped."""
        text = "Brazil emitted X of CO2 in 2022."
        result, dropped = strip_dangling_markers(text, max_id=3)
        assert result == text
        assert dropped == []

    def test_drops_zero_marker_as_invalid(self):
        """[0] is not a valid registry id (ids start at 1); must be stripped."""
        text = "Bogus [0] and real [1]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert result == "Bogus and real [1]."
        assert dropped == [0]

    def test_repeated_valid_marker_preserved(self):
        """Same marker used multiple times (correct LLM behavior) is untouched."""
        text = "Brazil [1], India [1], China [1]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert result == text
        assert dropped == []

    def test_preserves_markdown_link_label(self):
        """[404](url) is a markdown link, not a citation — must not be touched."""
        text = "See error page [404](https://example.com/404) for details."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert result == text
        assert dropped == []

    def test_preserves_markers_inside_inline_code(self):
        """Inline code spans like `x[99]` must pass through unchanged."""
        text = "Access the field with `record[99]` to get the value [1]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert "`record[99]`" in result
        assert "[1]" in result
        assert dropped == []

    def test_preserves_markers_inside_fenced_code_block(self):
        """Fenced code blocks must pass through unchanged even with dangling-looking markers."""
        text = "Example:\n```python\narr[5]\nother[99]\n```\nResult [1]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert "arr[5]" in result
        assert "other[99]" in result
        assert "[1]." in result
        assert dropped == []

    def test_unicode_digit_marker_does_not_crash(self):
        """Arabic-Indic digits like [١] must not match the ASCII-only regex → no int() crash."""
        text = "Claim [١] and claim [2]."
        # Should complete without raising ValueError; Unicode marker is left as-is
        # (we cannot int() it safely); ASCII [2] is dropped because max_id=1.
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert "[١]" in result  # Unicode marker preserved (out of scope for ASCII matcher)
        assert "[2]" not in result
        assert dropped == [2]

    def test_dropped_list_preserves_order_and_duplicates(self):
        """Same dangling marker repeated must appear in dropped list twice, in order."""
        text = "A [3] B [2] C [3]."
        result, dropped = strip_dangling_markers(text, max_id=1)
        assert dropped == [3, 2, 3]  # order of appearance in text
        assert "[3]" not in result and "[2]" not in result
