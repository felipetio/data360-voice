# Story 3.2: Citation Registry Pipeline

**Status:** ready-for-dev
**Epic:** 3 — Trust, Citations & LLM Grounding
**Story Key:** 3-2-citation-registry-pipeline
**Created:** 2026-04-02

---

## Story

As a journalist,
I want every data point to include its World Bank source attribution built from the data pipeline (not LLM-generated),
So that I can cite it in my publications with absolute confidence in accuracy.

---

## Acceptance Criteria

**AC1:** Given Claude calls MCP tools that return data records with `CITATION_SOURCE` fields, when the agentic loop in `app/chat.py` completes, then a new module `app/citations.py` builds a `references: list[dict]` from all tool responses containing `CITATION_SOURCE` (FR8).

**AC2:** Given the citation registry is built, when deduplication is applied, then one reference per unique combination of database + indicator (FR12). Different countries or years under the same indicator share one reference number. Different indicators from the same database get separate reference numbers.

**AC3:** Given the structured citation registry, when the response is rendered, then a fallback markdown reference list is appended to the response text. Format: `[1] World Bank, "CO2 emissions, total (kt)," World Development Indicators (EN.ATM.CO2E.KT), 2015-2022.`

**AC4:** Given document-type citations, when formatting, then they follow: `[3] "Relatório de Riscos," CEMADEM (uploaded 2026-04-01), p. 12.`

**AC5:** Given a response that contains no data points (clarification questions, "no data found"), when the citation registry is evaluated, then no reference list is appended.

**AC6:** Given the reference list title, when rendered, then it adapts to conversation language ("References", "Referências", "Referencias", etc.) (FR9).

**AC7:** Given the structured `references` list, when the response is complete, then it is attached to the Chainlit message metadata for Epic 9 UI consumption.

**AC8:** Given the `_agentic_loop()` in `app/chat.py`, when tool results are collected, then `app/citations.py` intercepts them to build the registry before the final response.

**AC9:** Given the system prompt (Story 3.1), when the citation pipeline is active, then the LLM-generated reference list instruction in the prompt is replaced with "Do not generate a reference list yourself" since the server now appends it.

**AC10:** Given a test suite `tests/app/test_citations.py`, when running `uv run pytest tests/app/test_citations.py`, then all tests pass.

---

## Tasks / Subtasks

### Task 1: Create `app/citations.py` — citation extraction and deduplication (AC: #1, #2)

- [ ] Create `app/citations.py` with the following functions:
  - `extract_references(tool_results: list[dict]) -> list[dict]` — scans tool result strings for JSON data containing `CITATION_SOURCE`, `INDICATOR`, `DATABASE_ID`, `TIME_PERIOD` fields. Parses each tool result text as JSON, iterates over `data` arrays, and collects citation info.
  - `deduplicate_references(raw_refs: list[dict]) -> list[dict]` — groups by `(database_id, indicator_code)` pair. Merges year ranges. Assigns sequential `id` starting from 1.
- [ ] Each reference entry contains: `id` (int), `source` (str from CITATION_SOURCE), `indicator_code` (str), `indicator_name` (str from INDICATOR or indicator field), `database_id` (str), `years` (str, collapsed range e.g. "2015-2022"), `type` ("api" | "document").
- [ ] Document references additionally contain: `filename`, `upload_date`, `page`/`chunk` fields.
- [ ] Handle edge cases: tool results that are error responses (no `data` key), tool results that are not JSON, empty data arrays.

### Task 2: Create reference list formatting in `app/citations.py` (AC: #3, #4, #6)

- [ ] Add `format_reference_list(references: list[dict], language: str = "en") -> str` function.
- [ ] API citation format: `[n] World Bank, "Indicator Name" (INDICATOR_CODE), Source Name, YEAR(s).`
- [ ] Document citation format: `[n] "Filename," Source (uploaded DATE), p. PAGE.`
- [ ] Language-adaptive title: `{"en": "References", "pt": "Referências", "es": "Referencias", "fr": "Références"}` with fallback to "References".
- [ ] Return empty string if references list is empty (AC5).

### Task 3: Integrate citation pipeline into `app/chat.py` agentic loop (AC: #7, #8)

- [ ] In `app/chat.py`, import from `app/citations.py`: `extract_references`, `deduplicate_references`, `format_reference_list`.
- [ ] In `_agentic_loop()`, collect all `tool_output` strings into a list as tools are called (alongside existing logic).
- [ ] After the loop completes (stop_reason != "tool_use"), call citation pipeline:
  ```python
  refs = deduplicate_references(extract_references(collected_tool_outputs))
  ref_text = format_reference_list(refs)
  ```
- [ ] If `ref_text` is not empty, append `"\n\n" + ref_text` to the final assembled text.
- [ ] Attach `references` list to `msg.metadata` for Epic 9: `msg.metadata = {"references": refs}`.
- [ ] Return the combined text (narrative + references) from `_agentic_loop()`.

### Task 4: Update system prompt to remove LLM-generated reference list (AC: #9)

- [ ] In `app/prompts.py`, update the CITATION MARKERS section in `_BASE_SYSTEM_PROMPT`:
  - Replace the current instruction that tells Claude to generate a reference list with: "A reference list will be appended automatically by the system. Do not generate a reference list yourself."
  - Keep the `[n]` marker instructions (place markers, order of first appearance, reuse same number).
- [ ] Update `SYSTEM_PROMPT` alias (it points to `_BASE_SYSTEM_PROMPT`, should auto-update).

### Task 5: Write tests `tests/app/test_citations.py` (AC: #10)

- [ ] Test `extract_references`:
  - Extracts refs from valid tool result JSON with `data` array containing `CITATION_SOURCE`, `INDICATOR`, `DATABASE_ID`, `TIME_PERIOD`.
  - Returns empty list for error responses (`{"success": false, ...}`).
  - Returns empty list for non-JSON tool results.
  - Returns empty list for results with empty `data` array.
  - Handles document-type results with `filename`, `upload_date`, `page` fields.
- [ ] Test `deduplicate_references`:
  - Merges same database+indicator into one ref with combined year range.
  - Different indicators from same database get separate refs.
  - Sequential id assignment starting from 1.
  - Document refs kept separate from API refs.
- [ ] Test `format_reference_list`:
  - API format matches expected IEEE-light pattern.
  - Document format matches expected pattern.
  - Empty references returns empty string.
  - Language-adaptive titles (en, pt, es).
- [ ] Test integration point (mocking `_agentic_loop` internals is complex — test the citation functions in isolation).

### Task 6: Update existing tests (AC: #10)

- [ ] Check `tests/app/test_prompts.py` — update `test_base_prompt_includes_reference_list_instructions` to assert on "Do not generate a reference list" instead of checking for LLM-generated list instructions.
- [ ] Check `tests/app/test_chat.py` for any assertions affected by the reference list being appended to responses.
- [ ] Run: `uv run pytest tests/app/ -v` — all pass.

### Task 7: Full validation (AC: all)

- [ ] Run: `uv run pytest -v` — no regressions across the full suite.
- [ ] Run: `uv run ruff check . && uv run ruff format .` — clean.
- [ ] Update `sprint-status.yaml`: `ready-for-dev` → `review`.
- [ ] Commit all changes.

---

## Dev Notes

### Key Design Decision: Where to Intercept Tool Results

The citation pipeline intercepts tool results **inside `_agentic_loop()`** in `app/chat.py`. This is the only place where all tool outputs are available before the final response. The flow:

```
User question → Claude → tool_use → MCP call → tool_output (collected here)
                       → tool_use → MCP call → tool_output (collected here)
                       → final text response
                       → extract_references(collected_outputs)
                       → deduplicate_references(raw_refs)
                       → format_reference_list(refs)
                       → append to response text
                       → attach refs to msg.metadata
```

### Tool Result Format (What `extract_references` Parses)

Tool results arrive as strings in `_agentic_loop`. For `get_data` results, the string is JSON:
```json
{
  "success": true,
  "data": [
    {
      "OBS_VALUE": "467000",
      "INDICATOR": "WB_WDI_EN_ATM_CO2E_KT",
      "DATABASE_ID": "WB_WDI",
      "TIME_PERIOD": "2022",
      "CITATION_SOURCE": "World Development Indicators",
      "DATA_SOURCE": "World Development Indicators",
      "REF_AREA": "BRA"
    }
  ],
  "total_count": 1,
  "returned_count": 1,
  "truncated": false
}
```

For `search_documents` results (RAG), the format includes document-specific fields:
```json
{
  "success": true,
  "data": [
    {
      "content": "...",
      "source": "report.pdf",
      "page_number": 12,
      "similarity_score": 0.85,
      "CITATION_SOURCE": "report.pdf (uploaded 2026-04-01), p. 12"
    }
  ]
}
```

### Deduplication Logic

Key: `(database_id, indicator_code)` for API refs, `(filename, page)` for document refs.

```python
# API: same indicator across years → one ref with merged years
# Input: 3 records for WB_WDI + EN_ATM_CO2E_KT with years 2020, 2021, 2022
# Output: [{"id": 1, "source": "World Development Indicators", "indicator_code": "EN_ATM_CO2E_KT", 
#           "indicator_name": "CO2 emissions, total (kt)", "database_id": "WB_WDI", 
#           "years": "2020-2022", "type": "api"}]

# Different indicators from same DB → separate refs
# WB_WDI + EN_ATM_CO2E_KT and WB_WDI + SP_POP_TOTL → ref [1] and ref [2]
```

### Year Range Collapsing

```python
def _collapse_years(years: list[int]) -> str:
    """Collapse [2015, 2016, 2017, 2020, 2022] → '2015-2017, 2020, 2022'"""
```

### Integration Point in `_agentic_loop()`

Current code collects tool results in `tool_results` list. Add a parallel `collected_tool_outputs: list[str]` that captures the raw `tool_output` strings:

```python
# In _agentic_loop(), before the while loop:
collected_tool_outputs: list[str] = []

# Inside the tool processing loop, after getting tool_output:
collected_tool_outputs.append(tool_output)

# After the while loop returns final text:
from app.citations import extract_references, deduplicate_references, format_reference_list

refs = deduplicate_references(extract_references(collected_tool_outputs))
ref_text = format_reference_list(refs)
if ref_text:
    final_text = final_text + "\n\n" + ref_text
msg.metadata = {"references": [r for r in refs]}  # for Epic 9
return final_text
```

### System Prompt Update (Task 4)

In `app/prompts.py`, the CITATION MARKERS section currently says:
```
"- After the narrative, append a numbered reference list matching the markers.\n"
"- Format each entry as: '[n] Source Name, \"Indicator Name\" (INDICATOR_CODE), YEAR(s).'\n"
"- Use the CITATION_SOURCE field value as the source name.\n"
"- Example reference list:\n"
"  [1] World Development Indicators, \"CO2 emissions, total (kt)\" (EN.ATM.CO2E.KT), 2015-2022.\n"
"  [2] Health Nutrition and Population Statistics, \"Life expectancy\" (SP.DYN.LE00.IN), 2021.\n\n"
```

Replace with:
```
"- A reference list will be appended automatically by the system. "
"Do not generate a reference list yourself.\n\n"
```

### Existing Code Structure

- `app/chat.py` — imports `get_system_prompt` from `app.prompts`, has `_agentic_loop()` function
- `app/prompts.py` — `_BASE_SYSTEM_PROMPT`, `DOCUMENT_SEARCH_SECTION`, `get_system_prompt()`, `SYSTEM_PROMPT` alias
- `app/config.py` — pydantic-settings with `rag_enabled`, `claude_model`, etc.

### Project Structure Notes

**Files to create:**
- `app/citations.py` — citation registry pipeline (extraction, dedup, formatting)
- `tests/app/test_citations.py` — comprehensive tests

**Files to modify:**
- `app/chat.py` — integrate citation pipeline into `_agentic_loop()`
- `app/prompts.py` — remove LLM-generated reference list instruction
- `tests/app/test_prompts.py` — update assertion for reference list instruction

**Files NOT to touch:**
- `mcp_server/` — no changes
- `app/config.py` — no new settings needed
- `db/` — no schema changes

### Architecture Compliance

Per architecture doc and project-context.md:
> Citation Pipeline Rules (Server-Side Registry):
> - Citations are pipeline-guaranteed: `app/citations.py` builds a structured citation registry from MCP tool responses server-side
> - The LLM's only citation responsibility is placing `[n]` markers in prose — it does NOT generate the reference list
> - `app/citations.py` handles: extraction from tool responses, deduplication, IEEE-light formatting
> - The `references: list[dict]` is attached to Chainlit message metadata for downstream UI consumption (Epic 9)

### Anti-Patterns

- **DON'T** let the LLM generate the reference list — the server appends it via `app/citations.py`.
- **DON'T** modify MCP tool response formats — tools already return `CITATION_SOURCE`.
- **DON'T** import sentence-transformers or RAG modules — this is app-layer only.
- **DON'T** put citation logic in `app/chat.py` directly — keep it in `app/citations.py`.
- **DON'T** use `Optional[X]` — use `X | None`.
- **DON'T** add `# noqa` without explicit approval.
- **DON'T** break the streaming UX — the reference list is appended after streaming completes.

### Previous Story Intelligence (from 3.1)

1. **System prompt structure**: `_BASE_SYSTEM_PROMPT` has CITATION MARKERS section with LLM-generated reference list instructions (temporary from 3.1 fix). This story replaces those with "Do not generate a reference list."
2. **Test pattern**: `TestGroundingBoundary.test_base_prompt_includes_reference_list_instructions` currently asserts `"reference list" in result.lower()` and `"CITATION_SOURCE" in result`. Will need updating.
3. **Ruff enforcement**: Run `uv run ruff check . && uv run ruff format .` before finalizing.
4. **`_agentic_loop()` returns text**: The returned string is used as `msg.content` via streaming. We append the reference list to the streamed content.

### References

- [Source: `app/chat.py#_agentic_loop`] — integration point for citation pipeline
- [Source: `app/prompts.py`] — system prompt with current LLM reference list instructions
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.2`] — acceptance criteria, citation registry design
- [Source: `_bmad-output/project-context.md#Citation Pipeline Rules`] — architectural contract
- [Source: `_bmad-output/implementation-artifacts/3-1-system-prompt-for-llm-grounding-boundary.md`] — previous story learnings

### Branch & Commit Conventions

- Branch: `story/3-2-citation-registry-pipeline`
- Commits: `feat(3-2): ...` / `test(3-2): ...` / `chore(3-2): ...`

### PR Conventions

- Reviewers: `--reviewer felipetio`
- PR description must list all ACs with checkboxes

---

## Dev Agent Record

### Agent Model Used

(to be filled by dev agent)

### Debug Log References

### Completion Notes List

### File List
