# Story 9.1: Server-side Data Sources Block

Status: review

## Story

As a user,
I want to see exactly where the data in each response came from,
So that I can trust the information and trace it back to its source.

---

## Acceptance Criteria

**AC1:** Given a chat response where tool calls returned data with `CITATION_SOURCE` fields, when the response is rendered in the Chainlit UI, then a "Data Sources" section is appended after the narrative as a bullet-point list.

**AC2:** Given an API source in the Data Sources block, when rendered, then it shows: source name, indicator name (if available), indicator code, year range. Format: `- World Development Indicators, "CO2 emissions, total (kt)" (EN_ATM_CO2E_KT), 2015-2022`

**AC3:** Given a document source in the Data Sources block, when rendered, then it shows: filename, upload date, page/chunk. The `CITATION_SOURCE` field already contains the formatted string (e.g., `report.pdf (uploaded 2026-04-01), p. 12`).

**AC4:** Given the Data Sources section title, when rendered, then it adapts to the conversation language:
- en: "Data Sources"
- pt: "Fontes de Dados"
- es: "Fuentes de Datos"
- fr: "Sources de Donn\u00e9es"
- de: "Datenquellen"

**AC5:** Given a response with no tool calls or where all tool calls returned empty data, when the response is rendered, then no Data Sources section appears.

**AC6:** Given multiple tool calls returning data from the same indicator and database, when the Data Sources block is built, then duplicate sources are merged (deduplicated by database_id + indicator_code). Year ranges are collapsed into compact format (e.g., "2015-2022").

**AC7:** Given the system prompt, when the LLM generates a response, then the prompt does NOT instruct the LLM to place `[n]` markers or generate any reference list. The prompt states that a Data Sources section is appended automatically.

**AC8:** Given the DOCUMENT SEARCH section of the system prompt (when RAG is enabled), when the LLM generates a response, then the section does NOT reference `[n]` markers or numbered citation systems. It states that the system handles citation attribution automatically.

---

## Tasks / Subtasks

### Task 1: Reformat `format_reference_list` in `app/citations.py` to bullet-point Data Sources format (AC: #1, #2, #3, #4, #5, #6)

- [x] Rename `_REFERENCE_TITLES` dict to `_DATA_SOURCES_TITLES` with updated values:
  - `"en": "Data Sources"`, `"pt": "Fontes de Dados"`, `"es": "Fuentes de Datos"`, `"fr": "Sources de Donn\u00e9es"`, `"de": "Datenquellen"`
- [x] Rewrite `format_reference_list` to use bullet-point format instead of `[n]` numbering:
  - API refs: `- {source}, "{indicator_name}" ({indicator_code}), {years}` (omit indicator_name part if empty, omit years if empty)
  - Document refs: `- {source}` (source field already contains the full formatted string from CITATION_SOURCE)
  - Keep the function signature identical: `format_reference_list(references, language="en") -> str`
  - Keep returning empty string for empty references list (AC5 unchanged)

### Task 2: Remove `[n]` marker instructions from `app/prompts.py` (AC: #7, #8)

- [x] Replace the CITATION MARKERS section in `_BASE_SYSTEM_PROMPT` with a DATA PROVENANCE section:
  - State that a "Data Sources" section is appended automatically after the response
  - State: "Do not generate any source list, reference list, or place [n] markers in the text."
  - Keep concise, 2-3 lines maximum
- [x] Update `DOCUMENT_SEARCH_SECTION`:
  - In the CROSS-REFERENCING WORKFLOW, remove step 4 (`"4. Use [n] numbered markers..."`)
  - Replace DOCUMENT CITATION FORMAT subsection: remove all `[n]` marker references, replace with "The system appends a Data Sources section automatically from tool responses. Do not construct citations manually."
  - Keep the GROUNDING BOUNDARY EXTENSION and WHEN NO DOCUMENTS ARE UPLOADED subsections unchanged

### Task 3: Update `app/chat.py` comments (AC: none, cleanup only)

- [x] Update the comment on the citation pipeline block in `_agentic_loop()`:
  - Change `# Build deterministic citation registry from collected tool outputs (AC1/AC3/AC7/AC8)` to reference Story 9.1 context
  - Change `# Attach structured references to message metadata for Epic 9 UI (AC7)` to reflect that metadata is for Story 9.2/9.3

### Task 4: Update `tests/app/test_citations.py` format assertions (AC: #1, #2, #3, #4)

- [x] Update `TestFormatReferenceList`:
  - `test_api_reference_format`: assert bullet format (`"- "` prefix), no `[1]` bracket. Assert source name, indicator name, code, years are present in the bullet line.
  - `test_document_reference_format`: assert bullet format, no `[1]` bracket.
  - `test_language_title_english`: change assertion from `"**References**"` to `"**Data Sources**"`
  - `test_language_title_portuguese`: change assertion from `"**Refer\u00eancias**"` to `"**Fontes de Dados**"`
  - `test_language_title_spanish`: change assertion from `"**Referencias**"` to `"**Fuentes de Datos**"`
  - `test_language_title_fallback`: change assertion from `"**References**"` to `"**Data Sources**"`
  - `test_multiple_references`: change assertion from `[1]`/`[2]` to verifying two bullet lines exist (two `"- "` prefixed lines)

### Task 5: Update `tests/app/test_prompts.py` for removed marker instructions (AC: #7, #8)

- [x] Update `TestGroundingBoundary`:
  - `test_base_prompt_contains_citation_marker_instructions`: rewrite to verify markers are NOT present (assert `"[1]"` NOT in prompt, assert `"marker"` NOT in prompt). Rename to `test_base_prompt_does_not_contain_citation_markers`.
  - `test_base_prompt_includes_reference_list_instructions`: update to assert `"Data Sources"` is mentioned and `"appended automatically"` is present. Update docstring.
  - `test_marker_reuse_instruction`: remove this test entirely (marker reuse is no longer applicable).
  - `test_rag_document_section_uses_numbered_markers`: rewrite to assert `"[n]"` is NOT in prompt when RAG enabled, and "Do not construct citations manually" is still present. Rename to `test_rag_document_section_does_not_use_numbered_markers`.
- [x] Update `TestDataFreshnessTransparency`:
  - `test_system_appends_reference_list_instruction_present`: update assertions from "reference list" to "Data Sources" and from "appended automatically by the system" to match new wording.

### Task 6: Full validation (AC: all)

- [x] Run: `uv run pytest -v` -- no regressions across the full suite
- [x] Run: `uv run ruff check . && uv run ruff format .` -- clean
- [x] Verify the pipeline end-to-end: `extract_references` -> `deduplicate_references` -> `format_reference_list` produces the expected bullet-point output with a realistic multi-tool-call fixture

---

## Dev Notes

### What This Story Does (and Does NOT Do)

This story reformats the existing citation pipeline output. The pipeline itself (`extract_references`, `deduplicate_references`) is already working and battle-tested from Story 3.2. This story changes:

1. **Output format** of `format_reference_list`: `[n]` numbered lines -> bullet-point list
2. **Section title**: "References" -> "Data Sources" (5 languages)
3. **System prompt**: removes `[n]` marker instructions, tells LLM that Data Sources is automatic
4. **Tests**: format assertions only

This story does NOT change:
- `extract_references` logic (parsing tool outputs)
- `deduplicate_references` logic (grouping by database_id + indicator_code)
- `_agentic_loop` flow in `app/chat.py` (pipeline integration stays identical)
- `msg.metadata = {"references": refs}` (structured data for Stories 9.2/9.3)
- The `id` field in deduplicated refs (kept for ordering, just not rendered as `[n]`)

### Why This Redesign (Retrospective Context)

The original Epic 9 attempted `[n]` markers with interactive UI. It failed because:
1. **Dangling markers**: LLM emits `[2]`, `[3]` but dedup collapses them into one ref entry
2. **LLM wrote its own reference section** despite prompt instructions not to
3. **Client-side MutationObserver** fought React re-renders in Chainlit

Full retrospective: `_bmad-output/implementation-artifacts/epic-9-retrospective-pre-redesign.md`

The redesigned approach eliminates ALL these problems:
- No markers = no dangling references
- Server-side bullet list = no LLM citation formatting involvement
- No custom JS/CSS = no React conflicts

### Current Code State (Verified 2026-04-23)

**`app/citations.py`** (281 lines):
- `_REFERENCE_TITLES`: dict with "References", "Refer\u00eancias", "Referencias", "R\u00e9f\u00e9rences", "Referenzen"
- `format_reference_list(references, language)`: builds `[n]` numbered lines
- `extract_references(tool_outputs)`: parses tool result JSON, extracts CITATION_SOURCE records
- `deduplicate_references(raw_refs)`: groups by (database_id, indicator_code), merges years

**`app/prompts.py`** (122 lines):
- `_BASE_SYSTEM_PROMPT`: contains CITATION MARKERS section (lines 37-44) with `[n]` instructions
- `DOCUMENT_SEARCH_SECTION`: contains `[n]` marker references in CROSS-REFERENCING WORKFLOW step 4 and DOCUMENT CITATION FORMAT subsection

**`app/chat.py`** (498 lines):
- `_agentic_loop()` (line 384): collects `all_tool_outputs`, calls citation pipeline at line 438-445
- Pipeline integration point: `ref_block = "\n\n" + format_reference_list(refs)` then streams it

### Exact Changes Per File

#### `app/citations.py`
1. Rename `_REFERENCE_TITLES` -> `_DATA_SOURCES_TITLES`, update values
2. Rewrite the loop inside `format_reference_list`:
   - Remove `ref_id = ref["id"]` usage in formatting
   - API: `f'- {source}, "{indicator_name}" ({indicator_code}), {years}'` (with conditional parts)
   - Doc: `f"- {source}"` (source already has full CITATION_SOURCE string)
   - Title: `f"**{title}**\n"` stays the same pattern, just different title values

#### `app/prompts.py`
1. In `_BASE_SYSTEM_PROMPT`, replace lines 37-44 (CITATION MARKERS section):
```python
"DATA PROVENANCE:\n"
"- A 'Data Sources' section listing all sources used is appended automatically "
"after your response. Do not generate any source list, reference list, "
"or place [n] markers in the text.\n\n"
```
2. In `DOCUMENT_SEARCH_SECTION`, update CROSS-REFERENCING WORKFLOW:
   - Remove step 4 about `[n]` markers, renumber remaining steps
3. In `DOCUMENT_SEARCH_SECTION`, replace DOCUMENT CITATION FORMAT subsection:
```python
"DOCUMENT CITATION FORMAT:\n"
"- The system appends a Data Sources section automatically from tool responses.\n"
"- Do not construct citations manually.\n\n"
```

#### `app/chat.py`
1. Update comment at line ~437 to reference Story 9.1 instead of old AC numbers
2. Update comment at line ~445 to say "for Story 9.2/9.3" instead of "for Epic 9 UI"

### Project Structure Notes

**Files to modify:**
- `app/citations.py` -- reformat output, rename title dict
- `app/prompts.py` -- remove marker instructions, add Data Sources provenance note
- `app/chat.py` -- comment-only changes
- `tests/app/test_citations.py` -- format assertion updates
- `tests/app/test_prompts.py` -- marker instruction assertion updates

**Files NOT to touch:**
- `mcp_server/` -- no changes
- `app/config.py` -- no new settings
- `app/chat.py` logic -- pipeline already works, only comments change
- `db/` -- no schema changes

### Architecture Compliance

Per `project-context.md` > Citation Pipeline Rules:
- Citations remain pipeline-guaranteed via `app/citations.py`
- The LLM now has ZERO citation responsibility (no markers, no ref list)
- `extract_references` and `deduplicate_references` are unchanged
- `references: list[dict]` still attached to `msg.metadata` for Stories 9.2/9.3

Per retrospective key lesson #4:
> LLM cannot be trusted to follow prompt for marker rules or suppressing its own ref list.
> Design the pipeline so that both are enforced server-side with deterministic code.

This story fully implements that lesson by removing ALL LLM citation involvement.

### Testing Strategy

- **Unit tests**: Update existing `TestFormatReferenceList` assertions for bullet format
- **Prompt tests**: Update `TestGroundingBoundary` to verify markers are removed
- **No new test files needed** -- existing test classes cover all the changed behavior
- **Regression check**: Full `uv run pytest -v` must pass with zero failures

### Anti-Patterns

- **DON'T** change `extract_references` or `deduplicate_references` -- they work correctly
- **DON'T** change `_agentic_loop` logic in `app/chat.py` -- only comments
- **DON'T** add any client-side JS or CSS -- this is server-side only
- **DON'T** re-introduce `[n]` markers anywhere in the prompt
- **DON'T** remove the `id` field from `deduplicate_references` output -- Stories 9.2/9.3 may use it
- **DON'T** remove `msg.metadata = {"references": refs}` -- needed for Stories 9.2/9.3
- **DON'T** use `Optional[X]` -- use `X | None`
- **DON'T** add `# noqa` without approval

### References

- [Source: `app/citations.py`] -- citation pipeline (format_reference_list target)
- [Source: `app/prompts.py`] -- system prompt with current [n] marker instructions
- [Source: `app/chat.py#_agentic_loop`] -- pipeline integration point (comments only)
- [Source: `_bmad-output/implementation-artifacts/epic-9-retrospective-pre-redesign.md`] -- failure analysis informing this redesign
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 9.1`] -- acceptance criteria
- [Source: `_bmad-output/implementation-artifacts/3-2-citation-registry-pipeline.md`] -- prerequisite story
- [Source: `_bmad-output/project-context.md#Citation Pipeline Rules`] -- architectural contract

---

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
- test_chat.py had an additional test (`test_system_prompt_instructs_citation_markers`) asserting `[1]` in SYSTEM_PROMPT, not listed in story tasks. Updated to verify Data Sources provenance instead.
- Prompt wording adjusted to avoid `[n]` and "marker" even in prohibition context (prevents LLM priming per retrospective lesson).

### Completion Notes List
- Renamed `_REFERENCE_TITLES` -> `_DATA_SOURCES_TITLES` with 5 localized titles
- Rewrote `format_reference_list` to bullet-point format (no `[n]` numbering)
- Replaced CITATION MARKERS section with DATA PROVENANCE in system prompt
- Updated DOCUMENT_SEARCH_SECTION: removed step 4 from cross-referencing workflow, simplified DOCUMENT CITATION FORMAT
- Updated chat.py comments to reference Story 9.1 and 9.2/9.3
- Updated all test assertions in test_citations.py, test_prompts.py, and test_chat.py
- Full suite: 338 passed, 0 failed; ruff clean

### File List
- `app/citations.py` (modified) - renamed title dict, rewrote format function
- `app/prompts.py` (modified) - replaced CITATION MARKERS with DATA PROVENANCE, updated DOCUMENT_SEARCH_SECTION
- `app/chat.py` (modified) - comment-only changes
- `tests/app/test_citations.py` (modified) - format assertion updates
- `tests/app/test_prompts.py` (modified) - marker instruction assertion updates
- `tests/app/test_chat.py` (modified) - updated citation marker test to data provenance

### Change Log
- Story 9.1 implementation: reformat citations from [n] numbered to bullet-point Data Sources (2026-04-23)
