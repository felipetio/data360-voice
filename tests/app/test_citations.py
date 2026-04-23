"""Tests for the citation registry pipeline (Story 3.2)."""

import json

from app.citations import (
    _collapse_years,
    _parse_time_period_year,
    _parse_time_period_years,
    deduplicate_references,
    detect_narrative_language,
    extract_references,
    format_reference_list,
    strip_llm_ref_tail,
)


class TestCollapseYears:
    """Unit tests for year range collapsing."""

    def test_consecutive_years(self):
        assert _collapse_years([2015, 2016, 2017]) == "2015-2017"

    def test_single_year(self):
        assert _collapse_years([2022]) == "2022"

    def test_empty_list(self):
        assert _collapse_years([]) == ""

    def test_mixed_ranges_and_singles(self):
        assert _collapse_years([2015, 2016, 2017, 2020, 2022]) == "2015-2017, 2020, 2022"

    def test_all_separate(self):
        assert _collapse_years([2010, 2015, 2020]) == "2010, 2015, 2020"

    def test_duplicates_removed(self):
        assert _collapse_years([2020, 2020, 2021]) == "2020-2021"

    def test_unsorted_input(self):
        assert _collapse_years([2022, 2020, 2021]) == "2020-2022"


class TestExtractReferences:
    """AC1: Extract citation data from tool result strings."""

    def _make_tool_output(self, data: list | None = None, success: bool = True) -> str:
        result: dict = {"success": success}
        if data is not None:
            result["data"] = data
            result["total_count"] = len(data)
            result["returned_count"] = len(data)
            result["truncated"] = False
        return json.dumps(result)

    def test_extracts_api_refs_from_valid_data(self):
        """AC1: Extracts references from get_data results."""
        data = [
            {
                "OBS_VALUE": "467000",
                "INDICATOR": "WB_WDI_EN_ATM_CO2E_KT",
                "DATABASE_ID": "WB_WDI",
                "TIME_PERIOD": "2022",
                "CITATION_SOURCE": "World Development Indicators",
                "REF_AREA": "BRA",
                "COMMENT_TS": "CO2 emissions, total (kt)",
            }
        ]
        output = self._make_tool_output(data)
        refs = extract_references([output])
        assert len(refs) == 1
        assert refs[0]["source"] == "World Development Indicators"
        assert refs[0]["indicator_code"] == "EN_ATM_CO2E_KT"
        assert refs[0]["database_id"] == "WB_WDI"
        assert refs[0]["year"] == 2022
        assert refs[0]["type"] == "api"

    def test_strips_database_prefix_from_indicator(self):
        """Indicator code WB_WDI_EN_ATM_CO2E_KT → EN_ATM_CO2E_KT."""
        data = [
            {
                "INDICATOR": "WB_WDI_EN_ATM_CO2E_KT",
                "DATABASE_ID": "WB_WDI",
                "TIME_PERIOD": "2020",
                "CITATION_SOURCE": "WDI",
            }
        ]
        refs = extract_references([self._make_tool_output(data)])
        assert refs[0]["indicator_code"] == "EN_ATM_CO2E_KT"

    def test_returns_empty_for_error_response(self):
        """Error responses produce no references."""
        output = self._make_tool_output(success=False)
        refs = extract_references([output])
        assert refs == []

    def test_returns_empty_for_non_json(self):
        """Non-JSON strings produce no references."""
        refs = extract_references(["not json at all"])
        assert refs == []

    def test_returns_empty_for_empty_data(self):
        """Empty data array produces no references."""
        output = self._make_tool_output(data=[])
        refs = extract_references([output])
        assert refs == []

    def test_skips_records_without_citation_source(self):
        """Records missing CITATION_SOURCE are ignored."""
        data = [{"OBS_VALUE": "100", "INDICATOR": "X", "DATABASE_ID": "Y"}]
        refs = extract_references([self._make_tool_output(data)])
        assert refs == []

    def test_extracts_document_refs(self):
        """Document-type results with page_number are detected."""
        data = [
            {
                "content": "some text",
                "source": "report.pdf",
                "page_number": 12,
                "similarity_score": 0.85,
                "CITATION_SOURCE": "report.pdf (uploaded 2026-04-01), p. 12",
            }
        ]
        refs = extract_references([self._make_tool_output(data)])
        assert len(refs) == 1
        assert refs[0]["type"] == "document"
        assert refs[0]["filename"] == "report.pdf"
        assert refs[0]["page"] == 12

    def test_multiple_tool_outputs(self):
        """References extracted from multiple tool outputs."""
        output1 = self._make_tool_output(
            [{"INDICATOR": "WB_WDI_A", "DATABASE_ID": "WB_WDI", "TIME_PERIOD": "2020", "CITATION_SOURCE": "WDI"}]
        )
        output2 = self._make_tool_output(
            [{"INDICATOR": "WB_HNP_B", "DATABASE_ID": "WB_HNP", "TIME_PERIOD": "2021", "CITATION_SOURCE": "HNP"}]
        )
        refs = extract_references([output1, output2])
        assert len(refs) == 2

    def test_handles_none_in_list(self):
        """None values in tool_outputs don't crash."""
        refs = extract_references([None])  # type: ignore[list-item]
        assert refs == []


class TestDeduplicateReferences:
    """AC2: Deduplication by (database_id, indicator_code) for API refs."""

    def test_merges_same_indicator_different_years(self):
        """Same db+indicator with different years → one ref with merged years."""
        raw = [
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "Ind A",
                "database_id": "WB_WDI",
                "year": 2020,
                "type": "api",
            },
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "Ind A",
                "database_id": "WB_WDI",
                "year": 2021,
                "type": "api",
            },
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "Ind A",
                "database_id": "WB_WDI",
                "year": 2022,
                "type": "api",
            },
        ]
        result = deduplicate_references(raw)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["years"] == "2020-2022"

    def test_different_indicators_same_db_separate_refs(self):
        """Different indicators from same DB get separate refs."""
        raw = [
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "",
                "database_id": "WB_WDI",
                "year": 2020,
                "type": "api",
            },
            {
                "source": "WDI",
                "indicator_code": "B",
                "indicator_name": "",
                "database_id": "WB_WDI",
                "year": 2020,
                "type": "api",
            },
        ]
        result = deduplicate_references(raw)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_sequential_ids(self):
        """IDs are assigned sequentially starting from 1."""
        raw = [
            {
                "source": "S1",
                "indicator_code": "A",
                "indicator_name": "",
                "database_id": "D1",
                "year": 2020,
                "type": "api",
            },
            {
                "source": "S2",
                "indicator_code": "B",
                "indicator_name": "",
                "database_id": "D2",
                "year": 2021,
                "type": "api",
            },
            {
                "source": "S3",
                "indicator_code": "C",
                "indicator_name": "",
                "database_id": "D3",
                "year": 2022,
                "type": "api",
            },
        ]
        result = deduplicate_references(raw)
        assert [r["id"] for r in result] == [1, 2, 3]

    def test_document_refs_kept_separate(self):
        """Document refs are deduplicated by (filename, page)."""
        raw = [
            {
                "source": "report.pdf, p. 5",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "year": None,
                "type": "document",
                "filename": "report.pdf",
                "upload_date": "",
                "page": 5,
                "chunk": None,
            },
            {
                "source": "report.pdf, p. 5",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "year": None,
                "type": "document",
                "filename": "report.pdf",
                "upload_date": "",
                "page": 5,
                "chunk": None,
            },
        ]
        result = deduplicate_references(raw)
        assert len(result) == 1

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert deduplicate_references([]) == []

    def test_uses_first_nonempty_indicator_name(self):
        """If first record has no name but second does, use the second."""
        raw = [
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "",
                "database_id": "WB_WDI",
                "year": 2020,
                "type": "api",
            },
            {
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "CO2 emissions",
                "database_id": "WB_WDI",
                "year": 2021,
                "type": "api",
            },
        ]
        result = deduplicate_references(raw)
        assert result[0]["indicator_name"] == "CO2 emissions"


class TestFormatReferenceList:
    """AC3/AC4/AC5/AC6: Reference list formatting."""

    def test_api_reference_format(self):
        """AC3: API citation in IEEE-light format."""
        refs = [
            {
                "id": 1,
                "source": "World Development Indicators",
                "indicator_code": "EN_ATM_CO2E_KT",
                "indicator_name": "CO2 emissions, total (kt)",
                "database_id": "WB_WDI",
                "years": "2015-2022",
                "type": "api",
            }
        ]
        result = format_reference_list(refs)
        assert "[1]" in result
        assert "CO2 emissions, total (kt)" in result
        assert "EN_ATM_CO2E_KT" in result
        assert "World Development Indicators" in result
        assert "2015-2022" in result

    def test_document_reference_format(self):
        """AC4: Document citation format."""
        refs = [
            {
                "id": 1,
                "source": "report.pdf (uploaded 2026-04-01), p. 12",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "document",
                "filename": "report.pdf",
                "upload_date": "2026-04-01",
                "page": 12,
            }
        ]
        result = format_reference_list(refs)
        assert "[1]" in result
        assert "report.pdf" in result

    def test_empty_references_returns_empty_string(self):
        """AC5: No references → empty string."""
        assert format_reference_list([]) == ""

    def test_language_title_english(self):
        """AC6: English title."""
        refs = [
            {
                "id": 1,
                "source": "S",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs, language="en")
        assert "**References**" in result

    def test_language_title_portuguese(self):
        """AC6: Portuguese title."""
        refs = [
            {
                "id": 1,
                "source": "S",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs, language="pt")
        assert "**Referências**" in result

    def test_language_title_spanish(self):
        """AC6: Spanish title."""
        refs = [
            {
                "id": 1,
                "source": "S",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs, language="es")
        assert "**Referencias**" in result

    def test_language_title_fallback(self):
        """AC6: Unknown language falls back to English."""
        refs = [
            {
                "id": 1,
                "source": "S",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs, language="xx")
        assert "**References**" in result

    def test_multiple_references(self):
        """Multiple refs formatted with sequential numbers."""
        refs = [
            {
                "id": 1,
                "source": "WDI",
                "indicator_code": "A",
                "indicator_name": "Ind A",
                "database_id": "D1",
                "years": "2020",
                "type": "api",
            },
            {
                "id": 2,
                "source": "HNP",
                "indicator_code": "B",
                "indicator_name": "Ind B",
                "database_id": "D2",
                "years": "2021",
                "type": "api",
            },
        ]
        result = format_reference_list(refs)
        assert "[1]" in result
        assert "[2]" in result


class TestFormatReferenceListImproved:
    """Format cleanliness — no awkward leading parentheticals, grouped CODE+years."""

    def test_no_indicator_name_produces_clean_source_first_line(self):
        """When indicator_name is empty, ref starts with source — not '(CODE),'."""
        refs = [
            {
                "id": 1,
                "source": "CO2 and Greenhouse Gas Emissions",
                "indicator_code": "TOTAL_GHG",
                "indicator_name": "",
                "database_id": "OWID_CB",
                "years": "2015-2023",
                "type": "api",
            }
        ]
        result = format_reference_list(refs)
        # Expected line shape: [1] Source (CODE, years).
        assert "[1] CO2 and Greenhouse Gas Emissions (TOTAL_GHG, 2015-2023)." in result
        # Must not start with "(CODE)," before source (old buggy format)
        assert "[1] (TOTAL_GHG)," not in result

    def test_with_indicator_name_uses_quoted_name_dash_source(self):
        """When indicator_name present, line is: [n] "Name" — Source (CODE, years)."""
        refs = [
            {
                "id": 1,
                "source": "World Bank WDI",
                "indicator_code": "EN.ATM.CO2E.KT",
                "indicator_name": "CO2 emissions, total (kt)",
                "database_id": "WB_WDI",
                "years": "2015-2022",
                "type": "api",
            }
        ]
        result = format_reference_list(refs)
        assert '[1] "CO2 emissions, total (kt)" — World Bank WDI (EN.ATM.CO2E.KT, 2015-2022).' in result

    def test_no_years_drops_years_from_paren(self):
        """If years missing, only CODE is inside parens."""
        refs = [
            {
                "id": 1,
                "source": "WDI",
                "indicator_code": "X",
                "indicator_name": "",
                "database_id": "D",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs)
        assert "[1] WDI (X)." in result

    def test_no_code_no_years_source_only(self):
        """With no code and no years, just source and period."""
        refs = [
            {
                "id": 1,
                "source": "Some Source",
                "indicator_code": "",
                "indicator_name": "",
                "database_id": "",
                "years": "",
                "type": "api",
            }
        ]
        result = format_reference_list(refs)
        assert "[1] Some Source." in result


class TestStripLlmRefTail:
    """strip_llm_ref_tail removes LLM-generated reference sections before the canonical
    block from format_reference_list is appended."""

    def test_strips_bold_references_header(self):
        """**References**\\n[1]... must be stripped entirely."""
        text = "Narrative claim [1].\n\n**References**\n\n[1] Source A."
        result = strip_llm_ref_tail(text)
        assert result == "Narrative claim [1]."

    def test_strips_portuguese_header_with_colon(self):
        """**Referências:**\\n[1]... must be stripped (i18n + trailing colon)."""
        text = "Narrativa [1].\n\n**Referências:**\n\n[1] Fonte A."
        result = strip_llm_ref_tail(text)
        assert result == "Narrativa [1]."

    def test_strips_spanish_header(self):
        """**Referencias**\\n[1]... (Spanish)."""
        text = "Claim [1].\n\n**Referencias**\n\n[1] Fuente."
        result = strip_llm_ref_tail(text)
        assert result == "Claim [1]."

    def test_strips_french_header(self):
        """**Références**\\n[1]... (French, with accent)."""
        text = "Narrative [1].\n\n**Références**\n[1] Source."
        result = strip_llm_ref_tail(text)
        assert result == "Narrative [1]."

    def test_strips_bibliography_variant(self):
        """**Bibliography** is also a common LLM header."""
        text = "Text [1].\n\n**Bibliography**\n\n[1] Book."
        result = strip_llm_ref_tail(text)
        assert result == "Text [1]."

    def test_strips_hr_followed_by_citations(self):
        """---\\n[1]... (no header, just HR + citations) must be stripped."""
        text = "Narrative [1].\n\n---\n[1] Source."
        result = strip_llm_ref_tail(text)
        assert result == "Narrative [1]."

    def test_strips_hr_then_header_then_citations(self):
        """---\\n**References**\\n[1]... (HR + header + refs) all goes."""
        text = "Narrative [1].\n\n---\n\n**References**\n\n[1] Source."
        result = strip_llm_ref_tail(text)
        assert result == "Narrative [1]."

    def test_preserves_prose_mentioning_references_word(self):
        """'References to X' not followed by [n] citations must NOT trigger stripping."""
        text = "References to colonial history show [1] the impact."
        result = strip_llm_ref_tail(text)
        assert result == "References to colonial history show [1] the impact."

    def test_noop_when_no_ref_section(self):
        """Narrative without any LLM ref section passes through."""
        text = "Brazil emitted X kt [1] in 2022."
        result = strip_llm_ref_tail(text)
        assert result == text

    def test_case_insensitive_header(self):
        """Mixed-case **REFERENCES** or **references** both match."""
        for header in ("**REFERENCES**", "**references**", "**ReFeReNcEs**"):
            text = f"Claim [1].\n\n{header}\n\n[1] S."
            assert strip_llm_ref_tail(text) == "Claim [1]."


class TestDetectNarrativeLanguage:
    """detect_narrative_language picks an ISO 639-1 code based on distinctive markers."""

    def test_portuguese_narrative(self):
        text = "O Brasil está na América Latina e não emite tanto quanto outros países."
        assert detect_narrative_language(text) == "pt"

    def test_english_narrative(self):
        text = "Brazil is the largest emitter in Latin America and leads the region."
        assert detect_narrative_language(text) == "en"

    def test_spanish_narrative(self):
        text = "El país está en América Latina pero tiene menos emisiones que otros países."
        assert detect_narrative_language(text) == "es"

    def test_french_narrative(self):
        text = "Le pays est une grande nation avec beaucoup d'émissions mais sont en déclin dans la région."
        assert detect_narrative_language(text) == "fr"

    def test_german_narrative(self):
        text = "Das Land ist groß und die Emissionen sind mit der Zeit hoch, der Rückgang ist bemerkenswert."
        assert detect_narrative_language(text) == "de"

    def test_empty_defaults_to_english(self):
        assert detect_narrative_language("") == "en"

    def test_ambiguous_defaults_to_english(self):
        assert detect_narrative_language("xyz 123") == "en"


class TestParseTimePeriodYear:
    """Story 3.3 AC4: TIME_PERIOD parsing handles all Data360 API formats."""

    def test_simple_year(self):
        """Plain year string."""
        assert _parse_time_period_year("2022") == 2022

    def test_integer_input(self):
        """Integer year input."""
        assert _parse_time_period_year(2022) == 2022

    def test_quarter_notation(self):
        """Quarter notation: first 4 chars are the year."""
        assert _parse_time_period_year("2022Q1") == 2022
        assert _parse_time_period_year("2019Q3") == 2019

    def test_range_string_returns_start_year(self):
        """Range string: returns start year."""
        assert _parse_time_period_year("2015-2022") == 2015

    def test_none_returns_none(self):
        assert _parse_time_period_year(None) is None

    def test_invalid_returns_none(self):
        assert _parse_time_period_year("invalid") is None
        assert _parse_time_period_year("") is None


class TestParseTimePeriodYears:
    """Story 3.3 AC4: Multi-year extraction from TIME_PERIOD range strings."""

    def test_simple_year_returns_single_element_list(self):
        assert _parse_time_period_years("2022") == [2022]

    def test_quarter_notation_returns_single_year(self):
        assert _parse_time_period_years("2022Q1") == [2022]

    def test_range_string_returns_all_years(self):
        """Range string expands to full year list."""
        result = _parse_time_period_years("2015-2022")
        assert result == list(range(2015, 2023))

    def test_none_returns_empty_list(self):
        assert _parse_time_period_years(None) == []

    def test_invalid_returns_empty_list(self):
        assert _parse_time_period_years("invalid") == []


class TestExtractReferencesTimePeriod:
    """Story 3.3 AC4: TIME_PERIOD edge cases in extract_references."""

    def _make_record(self, time_period: str) -> dict:
        return {
            "OBS_VALUE": "100",
            "INDICATOR": "WB_WDI_A",
            "DATABASE_ID": "WB_WDI",
            "TIME_PERIOD": time_period,
            "CITATION_SOURCE": "World Development Indicators",
            "REF_AREA": "BRA",
            "COMMENT_TS": "Some Indicator",
        }

    def _make_output(self, records: list) -> str:
        import json

        return json.dumps({"success": True, "data": records, "total_count": len(records)})

    def test_quarter_time_period_parsed(self):
        """Quarter notation TIME_PERIOD is parsed correctly."""
        output = self._make_output([self._make_record("2022Q1")])
        refs = extract_references([output])
        assert len(refs) == 1
        assert refs[0]["year"] == 2022

    def test_range_time_period_expands_years(self):
        """Range TIME_PERIOD creates multiple years in the ref."""
        output = self._make_output([self._make_record("2015-2022")])
        refs = extract_references([output])
        assert len(refs) == 1
        # years list should contain all years in range
        assert refs[0]["years"] == list(range(2015, 2023))

    def test_range_time_period_deduplicates_to_collapsed_range(self):
        """After deduplication, range TIME_PERIOD collapses correctly."""
        output = self._make_output([self._make_record("2015-2022")])
        refs = extract_references([output])
        deduped = deduplicate_references(refs)
        assert len(deduped) == 1
        assert deduped[0]["years"] == "2015-2022"
