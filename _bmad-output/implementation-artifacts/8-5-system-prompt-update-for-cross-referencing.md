# Story 8.5: System Prompt Update for Cross-Referencing

**Status:** review
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-5-system-prompt-update-for-cross-referencing
**Created:** 2026-04-02

---

## Story

As a product owner,
I want Claude to know how to use both API tools and document search tools together,
So that responses can cross-reference quantitative World Bank data with qualitative document context.

---

## Acceptance Criteria

**AC1:** Given the system prompt in `app/prompts.py`, when `DATA360_RAG_ENABLED=true`, then the `get_system_prompt()` function (or equivalent) includes a DOCUMENT SEARCH section instructing Claude to use `search_documents` when the user mentions uploaded reports, sub-national data, or local sources.

**AC2:** Given `DATA360_RAG_ENABLED=true`, when the system prompt is generated, then it instructs Claude to cross-reference Data360 API data (quantitative) with document context (qualitative) when both are relevant to a user query.

**AC3:** Given `DATA360_RAG_ENABLED=true`, when the system prompt is generated, then it includes the document citation format: `"{filename} (uploaded {date}), p. {page}"` for PDF documents, and `"..., chunk {chunk_index}"` for TXT/MD, and `"..., rows {start}-{end}"` for CSV.

**AC4:** Given `DATA360_RAG_ENABLED=true`, when the system prompt is generated, then it instructs Claude to treat document content as user-provided context (not LLM knowledge), maintaining the grounding boundary (i.e., Claude should not add external knowledge about the document topic).

**AC5:** Given `DATA360_RAG_ENABLED=true`, when the system prompt is generated, then it instructs Claude to clearly distinguish between API-sourced data and document-sourced context in responses.

**AC6:** Given `DATA360_RAG_ENABLED=false`, when the system prompt is generated, then the DOCUMENT SEARCH section is NOT included and existing prompt behavior is unchanged.

**AC7:** Given the `app/chat.py` handler, when the system prompt is built, then it calls the prompt-generation function (passing `rag_enabled=settings.rag_enabled`) and the correct conditional prompt is used in the Anthropic API call.

**AC8:** Given the full prompt assembly, when `DATA360_RAG_ENABLED=true`, then the DOCUMENT SEARCH section is appended to (not replacing) the existing SYSTEM_PROMPT content — all existing grounding rules, narrative guidelines, citation format, and multi-turn context rules remain intact.

**AC9:** Given a test file `tests/app/test_prompts.py`, when running `uv run pytest tests/app/test_prompts.py`, then all tests pass.

---

## Tasks / Subtasks

### Task 1: Refactor `app/prompts.py` to support conditional RAG section (AC: #1, #6, #8)

- [x] Open `app/prompts.py` and rename the current `SYSTEM_PROMPT` constant to `_BASE_SYSTEM_PROMPT` (keep the value identical — no text changes to existing prompt).
- [x] Add a `DOCUMENT_SEARCH_SECTION` string constant with the DOCUMENT SEARCH instructions (see exact text in Dev Notes below).
- [x] Add a `get_system_prompt(rag_enabled: bool = False) -> str` function:
  ```python
  def get_system_prompt(rag_enabled: bool = False) -> str:
      """Return the full system prompt, optionally including the DOCUMENT SEARCH section."""
      if rag_enabled:
          return _BASE_SYSTEM_PROMPT + "\n\n" + DOCUMENT_SEARCH_SECTION
      return _BASE_SYSTEM_PROMPT
  ```
- [x] Keep `SYSTEM_PROMPT` as a backward-compatible alias pointing to the base prompt (so existing `from app.prompts import SYSTEM_PROMPT` references don't break):
  ```python
  SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT  # backward-compatible alias
  ```
- [x] Commit: `feat(8-5): add get_system_prompt() with conditional RAG section to app/prompts.py`

### Task 2: Update `app/chat.py` to use `get_system_prompt()` (AC: #7)

- [x] In `app/chat.py`, update the import:
  ```python
  # Before:
  from app.prompts import SYSTEM_PROMPT
  # After:
  from app.prompts import get_system_prompt
  ```
- [x] Find the place where `SYSTEM_PROMPT` is used in the Anthropic API call (inside `_agentic_loop` or equivalent) and replace with:
  ```python
  system_prompt = get_system_prompt(rag_enabled=settings.rag_enabled)
  ```
  Then pass `system_prompt` to the Anthropic call.
- [x] Commit: `feat(8-5): wire get_system_prompt into chat.py agentic loop`

### Task 3: Write test suite `tests/app/test_prompts.py` (AC: #9)

- [x] Create `tests/app/test_prompts.py` with the test cases in Dev Notes below.
- [x] Run: `uv run pytest tests/app/test_prompts.py -v`
- [x] All tests pass.
- [x] Commit: `test(8-5): add test_prompts.py for conditional RAG system prompt`

### Task 4: Full validation (AC: all)

- [x] Run: `uv run pytest -v` — no regressions across the full suite. (257 passed)
- [x] Run: `uv run ruff check . && uv run ruff format .` — clean.
- [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: `in-progress` → `review`.
- [x] Commit: `chore(8-5): final validation — all tests pass, ruff clean`

---

## Dev Notes

### `DOCUMENT_SEARCH_SECTION` — Exact Text to Add

```python
DOCUMENT_SEARCH_SECTION = (
    "DOCUMENT SEARCH (uploaded documents):\n\n"
    "The user may have uploaded documents (PDFs, reports, CSV files) that are stored locally "
    "and searchable via the `search_documents` tool. Use this tool when:\n"
    "- The user explicitly mentions an uploaded report, document, or file.\n"
    "- The user asks about sub-national, regional, or local data not covered by World Bank API.\n"
    "- The user references a specific organisation, study, or source they have uploaded.\n"
    "- The query contains phrases like 'in the report', 'from the document', 'according to the file'.\n\n"
    "CROSS-REFERENCING WORKFLOW:\n"
    "When a query involves both World Bank quantitative data AND uploaded documents:\n"
    "1. Use `search_indicators` + `get_data` for official World Bank figures.\n"
    "2. Use `search_documents` for relevant context from uploaded files.\n"
    "3. Synthesise both sources in a single coherent narrative response.\n"
    "4. Clearly label each piece of information with its source.\n\n"
    "DOCUMENT CITATION FORMAT:\n"
    "- PDF chunks: `{filename} (uploaded {date}), p. {page}` "
    "— use the CITATION_SOURCE field returned by search_documents.\n"
    "- TXT/MD chunks: `{filename} (uploaded {date}), chunk {chunk_index}`\n"
    "- CSV chunks: `{filename} (uploaded {date}), rows {start}-{end}`\n"
    "Always use the CITATION_SOURCE value from the tool response; do not construct citations manually.\n\n"
    "GROUNDING BOUNDARY EXTENSION:\n"
    "- Treat document content as user-provided context, NOT as your own knowledge.\n"
    "- Do not add information about a document's topic from your training data.\n"
    "- If the document is about CEMADEM, CPTEC, NDC, or any specific organisation, "
    "report only what the document text says — do not supplement with external knowledge.\n"
    "- Distinguish clearly in your response: "
    "'According to the World Bank WDI (2022)...' vs 'According to the uploaded CEMADEM report (p. 4)...'.\n\n"
    "WHEN NO DOCUMENTS ARE UPLOADED:\n"
    "If `list_documents` returns an empty list or `search_documents` returns no results, "
    "do not mention the absence of documents unless the user specifically asked about them. "
    "Proceed with API data alone.\n"
)
```

### Existing `app/prompts.py` Structure

The current file (as of Story 8.4) contains a single module-level constant `SYSTEM_PROMPT`. It covers:
- Strict data constraints (no hallucination, no causation, no forecasts)
- Narrative response guidelines (trend narration, multi-country comparison, gap flagging)
- Citation format (using `CITATION_SOURCE`, `(Source: ..., year)`)
- Style guidelines
- Multi-turn context resolution rules

**Do NOT modify any of this existing content.** Only add the new `DOCUMENT_SEARCH_SECTION` and the `get_system_prompt()` function.

### Existing `app/chat.py` Pattern for System Prompt

From the current codebase (post 8-4), `chat.py` imports `SYSTEM_PROMPT` at the top:
```python
from app.prompts import SYSTEM_PROMPT
```

The system prompt is used inside the agentic loop when calling the Anthropic `messages.create()` or streaming equivalent. Look for the `system=` kwarg in the Anthropic API call. Replace the reference to the static constant with the dynamic call:

```python
system_prompt = get_system_prompt(rag_enabled=settings.rag_enabled)
# Then:
response = await client.messages.create(
    model=settings.claude_model,
    system=system_prompt,
    ...
)
```

Since `settings` is already imported in `app/chat.py`, no new import is needed for settings.

### Test Suite for `tests/app/test_prompts.py`

```python
"""Tests for conditional system prompt generation (Story 8.5)."""

import pytest
from app.prompts import get_system_prompt, SYSTEM_PROMPT, DOCUMENT_SEARCH_SECTION


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
```

### Project Structure Notes

**Files to modify:**
- `app/prompts.py` — add `_BASE_SYSTEM_PROMPT`, `DOCUMENT_SEARCH_SECTION`, `get_system_prompt()`, keep `SYSTEM_PROMPT` alias
- `app/chat.py` — change import and usage of system prompt to use `get_system_prompt()`

**Files to create:**
- `tests/app/test_prompts.py` — new test file

**Files NOT to touch:**
- `mcp_server/` — no changes needed; RAG tools are already registered conditionally in 8-3
- `app/config.py` — `rag_enabled` setting already exists from 8-4
- `db/` — no schema changes
- Any existing test file — only add the new test file

### Architecture Compliance

This story lives entirely in `app/` scope per the architecture document:

> | FR Category | Primary Location | Key Files |
> |------------|-----------------|-----------|
> | LLM Grounding & Trust (FR18-22) | `app/` | `chat.py` (system prompt constraints) |

The system prompt is the correct and only mechanism to extend Claude's grounding boundary. No changes to MCP tools or database schema are needed.

**Feature flag pattern:** `DATA360_RAG_ENABLED` controls the RAG section inclusion. The `settings.rag_enabled` field already exists in `app/config.py` (pydantic-settings, validation_alias `DATA360_RAG_ENABLED`, default `False`).

### Anti-Patterns

- **DON'T** change the base system prompt text — existing behaviour must be preserved exactly.
- **DON'T** hardcode `rag_enabled=True` — always read from `settings.rag_enabled`.
- **DON'T** use string concatenation at import time — use the `get_system_prompt()` function so the flag is evaluated at call time (important for tests that patch settings).
- **DON'T** add new environment variables — `DATA360_RAG_ENABLED` already exists.
- **DON'T** modify `mcp_server/` — prompt changes live in `app/` only.
- **DON'T** remove the `SYSTEM_PROMPT` constant — it must remain as a backward-compatible alias for any code that imports it directly.

### Previous Story Intelligence (from 8-4)

Key learnings from 8-4 that apply here:

1. **`app/config.py` uses pydantic-settings** with `rag_enabled: bool` field aliased to `DATA360_RAG_ENABLED`. Import `settings` from `app.config`.
2. **`app/chat.py` already imports `from app.prompts import SYSTEM_PROMPT`** — this is the only import that needs updating.
3. **`settings` is already imported** in `app/chat.py` via `from app.config import settings` — no new config imports needed.
4. **Test patching pattern:** From 8-4 debug notes, `patch("app.chat.settings")` works; use `patch("app.prompts.settings")` if needed in future, but for 8-5 prompts tests just call `get_system_prompt()` directly without patching.
5. **Ruff is enforced** — run `uv run ruff check . && uv run ruff format .` before finalising.

### References

- [Source: `app/prompts.py`] — existing `SYSTEM_PROMPT` constant (to become `_BASE_SYSTEM_PROMPT`)
- [Source: `app/chat.py`] — import site and Anthropic API call pattern
- [Source: `app/config.py`] — `rag_enabled` pydantic-settings field
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 8.5`] — acceptance criteria origin
- [Source: `_bmad-output/planning-artifacts/architecture.md#Requirements to Structure Mapping`] — confirms prompt changes belong in `app/`
- [Source: `_bmad-output/implementation-artifacts/8-4-chainlit-upload-integration.md#Dev Agent Record`] — pool pattern, import conventions, ruff enforcement

### Branch & Commit Conventions

- Branch: `story/8-5-system-prompt-update-for-cross-referencing`
- Commits: `feat(8-5): ...` / `test(8-5): ...` / `chore(8-5): ...`

### PR Description Format (mandatory)

```
## What This Does
Updates app/prompts.py to support a conditional DOCUMENT SEARCH section
in the system prompt. When DATA360_RAG_ENABLED=true, get_system_prompt()
appends instructions for using search_documents, cross-referencing API data
with document context, applying document citation format, and extending the
grounding boundary to user-uploaded content. When RAG is disabled, the prompt
is identical to the previous SYSTEM_PROMPT constant.

## Key Code to Understand
- `app/prompts.py` → `_BASE_SYSTEM_PROMPT` — unchanged base prompt (was SYSTEM_PROMPT)
- `app/prompts.py` → `DOCUMENT_SEARCH_SECTION` — new RAG instructions constant
- `app/prompts.py` → `get_system_prompt(rag_enabled)` — conditional prompt assembly
- `app/prompts.py` → `SYSTEM_PROMPT` — backward-compatible alias for `_BASE_SYSTEM_PROMPT`
- `app/chat.py` — import updated to use `get_system_prompt(settings.rag_enabled)`

## Acceptance Criteria Covered
- [x] AC1: DOCUMENT SEARCH section present when RAG enabled
- [x] AC2: Cross-referencing workflow instructions included
- [x] AC3: Document citation format for PDF, TXT/MD, CSV
- [x] AC4: Grounding boundary extended to document content
- [x] AC5: Instructions to distinguish API data vs document context
- [x] AC6: DOCUMENT SEARCH section absent when RAG disabled
- [x] AC7: chat.py uses get_system_prompt(settings.rag_enabled)
- [x] AC8: Base prompt content fully preserved when RAG enabled
- [x] AC9: All tests pass

## Files Changed
**Modified:**
- app/prompts.py (_BASE_SYSTEM_PROMPT, DOCUMENT_SEARCH_SECTION, get_system_prompt, SYSTEM_PROMPT alias)
- app/chat.py (import + system prompt usage in agentic loop)
- _bmad-output/implementation-artifacts/sprint-status.yaml

**New:**
- tests/app/test_prompts.py
```

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Fixed `test_chat.py::test_system_prompt_included_in_every_call`: test compared against static `SYSTEM_PROMPT`; updated to patch `settings.rag_enabled=False` and compare against `get_system_prompt(rag_enabled=False)` for determinism.

### Completion Notes List

- AC1: `get_system_prompt(rag_enabled=True)` includes DOCUMENT SEARCH section ✅
- AC2: Cross-referencing workflow instructions in DOCUMENT_SEARCH_SECTION ✅
- AC3: Document citation formats for PDF, TXT/MD, CSV ✅
- AC4: Grounding boundary extension (user-provided context, not LLM knowledge) ✅
- AC5: Instructions to distinguish API data vs document context ✅
- AC6: `get_system_prompt(rag_enabled=False)` excludes DOCUMENT SEARCH section ✅
- AC7: `app/chat.py` uses `get_system_prompt(rag_enabled=settings.rag_enabled)` ✅
- AC8: Base prompt content fully preserved when RAG enabled (appended, not replaced) ✅
- AC9: `tests/app/test_prompts.py` — 10 tests, all pass ✅
- Full suite: 257 passed, 0 failed

### File List

- `app/prompts.py` (modified)
- `app/chat.py` (modified)
- `tests/app/test_prompts.py` (new)
- `tests/app/test_chat.py` (modified — fixed regression in test_system_prompt_included_in_every_call)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/8-5-system-prompt-update-for-cross-referencing.md` (modified)

---

## Change Log

- 2026-04-02: Story created by Bob (SM). Status → ready-for-dev.
- 2026-04-02: Story implemented by Amelia (Dev). Status → review.


# Story 8.5: System Prompt Update for Cross-Referencing

**Status:** ready-for-dev
**Epic:** 8 — Document Upload & RAG Search
**Story Key:** 8-5-system-prompt-update-for-cross-referencing
**Created:** 2026-04-02

Story file created at: `_bmad-output/implementation-artifacts/8-5-system-prompt-update-for-cross-referencing.md`
