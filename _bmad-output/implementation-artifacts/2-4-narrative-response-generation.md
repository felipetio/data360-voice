# Story 2.4: Narrative Response Generation

Status: done

## Story

As a journalist or researcher,
I want data presented as contextual narratives describing values, trends, and comparisons,
so that I can understand and use the data without interpreting raw numbers myself.

## Acceptance Criteria

1. **Given** a user asks "How has drought increased in Brazil in the last decade?", **when** Claude receives data from MCP tools, **then** the response describes data values in human-readable narrative form (FR13) and includes trend descriptions (rising, falling, stable, accelerating) when time-series data is available (FR15).

2. **Given** a user asks "Compare CO2 emissions between Brazil and India", **when** Claude processes multi-country data, **then** the response compares data across the requested countries in a single narrative (FR14).

3. **Given** data has missing years or gaps, **when** Claude generates the response, **then** it flags the gaps transparently (e.g., "Data not available for 2021–2022") (FR16).

4. **Given** no matching indicator exists for the query, **when** Claude processes the empty result, **then** it responds clearly with "No relevant data found" and suggests alternative queries if appropriate (FR17).

## Tasks / Subtasks

- [x] **Task 1: Upgrade system prompt for narrative generation** (AC: #1, #2, #3, #4)
  - [x] Rewrite `SYSTEM_PROMPT` in `app/prompts.py` to include explicit narrative instructions:
    - Describe values in plain language (avoid raw tables by default)
    - Identify and verbally describe trend direction (rising/falling/stable/accelerating/decelerating) from time-series `TIME_PERIOD` + `OBS_VALUE` sequences
    - Compare multiple countries in a single flowing narrative when multi-country data is returned
    - Flag missing years explicitly when gaps are detected in the `TIME_PERIOD` sequence
    - Respond with "No relevant data found" + suggestions when tools return empty `data: []`
  - [x] Keep all existing grounding constraints intact (no causal claims, no forecasts, no external knowledge)
  - [x] Update citation instruction: always include `CITATION_SOURCE` field value and data year range
  - [x] Commit: `feat(prompts): upgrade system prompt for narrative response generation`

- [x] **Task 2: Add narrative-focused integration tests** (AC: #1, #2, #3, #4)
  - [x] Add `TestNarrativeGeneration` class in `tests/app/test_chat.py`
  - [x] Test: single-country time-series query → system prompt instructs trend narration
  - [x] Test: multi-country query → system prompt instructs comparison narration
  - [x] Test: tool returns empty `data: []` → system prompt instructs "no data found" response
  - [x] Test: system prompt includes all grounding constraints (no causal claims, no forecasts)
  - [x] Test: system prompt instructs citation with `CITATION_SOURCE` and year range
  - [x] All 154+ tests pass
  - [x] Commit: `test(prompts): narrative generation system prompt tests`

## Dev Notes

### What Exists Already (Do NOT Recreate)

The agentic loop, tool-use, and streaming are **fully implemented** in `app/chat.py`. This story is **prompt engineering only** — no changes to `chat.py`, `config.py`, `main.py`, or MCP server code.

Current `SYSTEM_PROMPT` in `app/prompts.py` already has:
- Domain grounding constraints (no invented data, no causal claims, no forecasts)
- Basic style guidance (concise, plain language)
- Citation instruction (dataset name + year range)

**This story extends the prompt** to explicitly instruct narrative generation, trend analysis, multi-country comparison, gap flagging, and "no data found" handling.

### Prompt Engineering Approach

The upgraded prompt must instruct Claude to:

1. **Trend narration** — when `TIME_PERIOD` + `OBS_VALUE` pairs span multiple years, describe the direction and character of change in plain language. Examples: "rose steadily from X in 2010 to Y in 2022", "fell sharply between 2015 and 2018, then stabilised", "remained roughly flat throughout the period".

2. **Multi-country comparison** — when data for multiple `REF_AREA` values is returned, weave them into a single comparative paragraph rather than listing them separately. Example: "Brazil's CO2 emissions (X kt in 2022) were roughly twice those of India (Y kt), though India's have grown faster, rising Z% since 2010."

3. **Gap flagging** — if years are missing from an otherwise continuous `TIME_PERIOD` sequence, note this explicitly. Example: "Data is not available for 2019–2020, likely due to reporting delays."

4. **No data found** — when all tool calls return `"data": []`, respond with a clear "No relevant data found for [topic]" statement and, if possible, suggest what alternative queries or indicators might help.

5. **Citation format** — every narrative paragraph that references a specific figure must end with a source note citing `CITATION_SOURCE` and the year(s) of data used. Example: "(Source: World Development Indicators, 2022)"

### Files to Modify

| File | Change |
|------|--------|
| `app/prompts.py` | Rewrite `SYSTEM_PROMPT` to add narrative, trend, comparison, gap, and no-data instructions |
| `tests/app/test_chat.py` | Add `TestNarrativeGeneration` class |

**DO NOT modify:** `app/chat.py`, `app/config.py`, `app/main.py`, any MCP server files.

### Testing Standards

- Tests assert on `SYSTEM_PROMPT` content (string contains checks), not on live Claude output
- Follow existing test class pattern: `class TestNarrativeGeneration:` with docstring referencing AC numbers
- Use `unittest.mock` where needed; no real API calls in tests
- All tests must be deterministic

### Project Structure Alignment

```
app/
├── prompts.py     ← ONLY file changed in this story
tests/
└── app/
    └── test_chat.py  ← add TestNarrativeGeneration class here
```

### Prior Story Learnings (from 2.2 + 2.3)

- Ruff enforces double quotes and line length 120 — run `uv run ruff check . && uv run ruff format .` before committing
- Pre-commit hook runs ruff automatically on staged files
- `SYSTEM_PROMPT` is a module-level string constant in `app/prompts.py` — tests import it directly: `from app.prompts import SYSTEM_PROMPT`
- Story branch naming: `story/2.4-narrative-response-generation` (already created)
- Commit format: `feat(story-key): description`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4] — AC definitions (FR13, FR14, FR15, FR16, FR17)
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 2] — Conversational Climate Data Interface goals
- [Source: _bmad-output/project-context.md#Citation Integrity Rules] — CITATION_SOURCE usage
- [Source: _bmad-output/project-context.md#Critical Anti-Patterns] — what NOT to do
- [Source: _bmad-output/implementation-artifacts/story-2.2.md#Dev Notes] — SYSTEM_PROMPT location and streaming pattern
- [Source: app/prompts.py] — current SYSTEM_PROMPT to extend (not replace from scratch)
- [Source: app/chat.py] — agentic loop context; no changes needed here

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

_none_

### Completion Notes List

- Task 1: Extended SYSTEM_PROMPT in app/prompts.py with narrative generation instructions. Added sections for: trend narration (TIME_PERIOD/OBS_VALUE sequences), multi-country comparison (REF_AREA), gap flagging (missing years), no-data-found response, and CITATION_SOURCE citation format. All existing grounding constraints preserved.
- Task 2: Added TestNarrativeGeneration class in tests/app/test_chat.py with 6 tests covering all ACs. All 160 tests pass (no regressions).
- Code review: clean, no patch findings.

### File List

- app/prompts.py (modified)
- tests/app/test_chat.py (modified)
