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
        """SYSTEM_PROMPT constant still importable and equals base prompt with default threshold."""
        from app.prompts import SYSTEM_PROMPT as sp

        assert sp == get_system_prompt(rag_enabled=False, staleness_threshold_years=2)


class TestGroundingBoundary:
    """Story 3.1: grounding boundary reinforcement and citation marker instructions."""

    def test_base_prompt_contains_citation_marker_instructions(self):
        """AC5: Citation marker [n] instructions present in base prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "[1]" in result
        assert "[2]" in result
        assert "marker" in result.lower()

    def test_base_prompt_includes_reference_list_instructions(self):
        """AC6: LLM is told about the reference list (system appends it automatically)."""
        result = get_system_prompt(rag_enabled=False)
        assert "reference list" in result.lower()
        # Since story 3.2, the system appends the reference list; the prompt tells Claude not to generate one
        assert "appended automatically by the system" in result

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


class TestDataFreshnessTransparency:
    """Story 3.3: Data freshness transparency instructions in system prompt."""

    def test_base_prompt_contains_data_freshness_section(self):
        """AC5: DATA FRESHNESS section present in base prompt."""
        result = get_system_prompt()
        assert "DATA FRESHNESS" in result

    def test_default_staleness_threshold_is_two_years(self):
        """AC6: Default staleness threshold is 2 years."""
        result = get_system_prompt()
        assert "2 years" in result

    def test_custom_staleness_threshold_injected(self):
        """AC6: Custom threshold is injected correctly."""
        result = get_system_prompt(staleness_threshold_years=3)
        assert "3 years" in result
        assert "{staleness_threshold}" not in result

    def test_no_placeholder_in_default_prompt(self):
        """Ensure placeholder is always resolved, never left raw."""
        result = get_system_prompt()
        assert "{staleness_threshold}" not in result

    def test_system_prompt_alias_resolves_placeholder(self):
        """SYSTEM_PROMPT alias must have resolved placeholder."""
        assert "{staleness_threshold}" not in SYSTEM_PROMPT
        assert "2 years" in SYSTEM_PROMPT

    def test_freshness_includes_inline_year_instruction(self):
        """AC1: Prompt instructs Claude to include year inline in prose."""
        result = get_system_prompt()
        assert "inline" in result.lower()

    def test_freshness_includes_staleness_warning_instruction(self):
        """AC2: Prompt instructs Claude to warn about stale data."""
        result = get_system_prompt()
        assert "staleness" in result.lower() or "stale" in result.lower() or "warning" in result.lower()

    def test_freshness_includes_multi_country_recency_instruction(self):
        """AC3: Prompt instructs Claude to show each country's data year in comparisons."""
        result = get_system_prompt()
        assert "multi-country" in result.lower() or "each country" in result.lower()

    def test_rag_prompt_also_has_data_freshness(self):
        """DATA FRESHNESS section present even when RAG is enabled."""
        result = get_system_prompt(rag_enabled=True)
        assert "DATA FRESHNESS" in result

    def test_system_appends_reference_list_instruction_present(self):
        """AC5: Prompt tells Claude that reference list is appended automatically."""
        result = get_system_prompt()
        assert "appended automatically by the system" in result
        assert "Do not generate a reference list yourself" in result
