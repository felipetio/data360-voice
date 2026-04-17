"""Tests for Citation UI Python-side changes (Story 9.1).

The citation UI styles [n] markers via CSS and renders the reference block as
streamed markdown. The Python side strips LLM-generated reference tails to
avoid duplication with the system-appended reference block.

AC1: Reference block is streamed and persisted in message content.
AC2: No reference block when no citations (guard in _agentic_loop).
"""

from app.chat import _strip_llm_ref_tail


class TestStripLlmRefTail:
    """_strip_llm_ref_tail removes LLM-generated reference sections."""

    def test_strips_hr_followed_by_ref_lines(self):
        text = "Brazil emitted X [1].\n\n---\n[1] CO2 and GHG Emissions, 2023."
        result = _strip_llm_ref_tail(text)
        assert result == "Brazil emitted X [1]."

    def test_strips_multiline_ref_block(self):
        text = "Narrative [1] and [2].\n\n---\n[1] Source A.\n[2] Source B."
        result = _strip_llm_ref_tail(text)
        assert result == "Narrative [1] and [2]."

    def test_noop_when_no_ref_tail(self):
        text = "Brazil emitted X [1]."
        assert _strip_llm_ref_tail(text) == text

    def test_noop_for_hr_not_followed_by_ref(self):
        text = "Some text.\n\n---\n\nMore text."
        assert _strip_llm_ref_tail(text) == text

    def test_strips_single_newline_before_hr(self):
        text = "Narrative [1].\n---\n[1] Source."
        assert _strip_llm_ref_tail(text) == "Narrative [1]."

    def test_result_has_no_trailing_whitespace(self):
        text = "Narrative [1].\n\n---\n[1] Source.\n\n"
        result = _strip_llm_ref_tail(text)
        assert result == "Narrative [1]."
        assert not result.endswith(("\n", " "))
