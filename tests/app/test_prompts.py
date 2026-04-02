"""Tests for conditional system prompt generation (Story 8.5)."""

from app.prompts import SYSTEM_PROMPT, get_system_prompt


class TestGetSystemPrompt:
    def test_rag_disabled_returns_base_prompt(self):
        """When rag_enabled=False, get_system_prompt returns the base prompt unchanged."""
        result = get_system_prompt(rag_enabled=False)
        assert result == SYSTEM_PROMPT

    def test_rag_enabled_includes_document_search_section(self):
        """When rag_enabled=True, get_system_prompt appends DOCUMENT SEARCH section."""
        result = get_system_prompt(rag_enabled=True)
        assert "DOCUMENT SEARCH" in result

    def test_rag_enabled_contains_base_prompt(self):
        """When rag_enabled=True, the base prompt content is preserved."""
        result = get_system_prompt(rag_enabled=True)
        # Key phrases from the base prompt must still be present
        assert "STRICT CONSTRAINTS" in result
        assert "CITATION FORMAT" in result
        assert "MULTI-TURN CONTEXT RESOLUTION" in result

    def test_rag_disabled_excludes_document_search_section(self):
        """When rag_enabled=False, DOCUMENT SEARCH section is NOT in the prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "DOCUMENT SEARCH" not in result

    def test_rag_enabled_includes_search_documents_tool_hint(self):
        """Prompt instructs Claude to use search_documents tool."""
        result = get_system_prompt(rag_enabled=True)
        assert "search_documents" in result

    def test_rag_enabled_includes_cross_referencing_instructions(self):
        """Prompt includes cross-referencing workflow instructions."""
        result = get_system_prompt(rag_enabled=True)
        assert "CROSS-REFERENCING" in result

    def test_rag_enabled_includes_citation_format_for_documents(self):
        """Prompt includes document-specific citation format instructions."""
        result = get_system_prompt(rag_enabled=True)
        assert "CITATION_SOURCE" in result
        assert "uploaded" in result

    def test_rag_enabled_includes_grounding_boundary_extension(self):
        """Prompt extends the grounding boundary to document content."""
        result = get_system_prompt(rag_enabled=True)
        assert "user-provided context" in result

    def test_default_parameter_is_rag_disabled(self):
        """Default call (no args) returns base prompt — safe when RAG is off."""
        result = get_system_prompt()
        assert result == SYSTEM_PROMPT

    def test_system_prompt_backward_compat_alias(self):
        """SYSTEM_PROMPT constant still importable and equals the base prompt."""
        from app.prompts import SYSTEM_PROMPT as sp

        assert sp == get_system_prompt(rag_enabled=False)
