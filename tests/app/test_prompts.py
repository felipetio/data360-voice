"""Tests for system prompt: conditional RAG section (8.5) and grounding boundary + citation markers (3.1)."""

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
        assert "CITATION MARKERS" in result
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


class TestGroundingBoundary:
    """Story 3.1: grounding boundary reinforcement and citation marker instructions."""

    def test_base_prompt_contains_citation_marker_instructions(self):
        """AC5: Citation marker [n] instructions present in base prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "[1]" in result
        assert "[2]" in result
        assert "marker" in result.lower()

    def test_base_prompt_includes_reference_list_instructions(self):
        """AC6: LLM is told to append a numbered reference list."""
        result = get_system_prompt(rag_enabled=False)
        assert "reference list" in result.lower()
        assert "CITATION_SOURCE" in result

    def test_base_prompt_grounding_boundary_causation(self):
        """AC3: Causation constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "causation" in result.lower()

    def test_base_prompt_grounding_boundary_no_opinions(self):
        """AC4: No-opinions constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "opinions" in result.lower()

    def test_marker_reuse_instruction(self):
        """AC7: Instruction to reuse marker for same source is present."""
        result = get_system_prompt(rag_enabled=False)
        assert "reuse" in result.lower()
        assert "same" in result.lower()

    def test_no_old_inline_citation_format(self):
        """AC5: Old citation instruction 'Example: (Source: ...)' removed from prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert 'Example: "(Source:' not in result

    def test_rag_document_section_uses_numbered_markers(self):
        """AC8: Document search section aligns with [n] marker system."""
        result = get_system_prompt(rag_enabled=True)
        # The document section should reference [n] markers
        assert "[n]" in result
        assert "Do not construct citations manually" in result
