# Story 3.3: Data Freshness Transparency

**Status:** review
**Epic:** 3 — Trust, Citations & LLM Grounding
**Story Key:** 3-3-data-freshness-transparency
**Created:** 2026-04-03

---

## Story

As a researcher,
I want to see the most recent data year for every data point and be warned about stale data,
So that I understand the recency of the information I'm using.

---

## Acceptance Criteria

**AC1:** Given Claude generates a response with data, when the response is displayed, then every data point shows the most recent data year available — extracted from `TIME_PERIOD` / `LATEST_DATA` fields in the API response (FR10). The `years` field already computed in `app/citations.py` `deduplicate_references` satisfies this requirement; the system prompt must instruct Claude to surface year ranges inline in prose.

**AC2:** Given data where the most recent year in a response is more than 2 years before the current year (i.e., `max(years) < current_year - 2`), when the response is generated, then Claude includes an explicit staleness warning. The warning distinguishes "this is the latest data available from World Bank" from "more recent data may exist" (FR11).

**AC3:** Given a multi-country comparison where data years differ across `REF_AREA` values, when the response is generated, then each country's data year is shown individually and discrepancies in recency are flagged transparently.

**AC4:** Given the citation registry built in Story 3.2, when year ranges are extracted from tool responses via `app/citations.py`, then the `years` field in each reference entry correctly reflects the actual data range in collapsed format (e.g., "2015-2022"). *(Validation of existing Story 3.2 behavior — ensure it works correctly end-to-end.)*

**AC5:** Given a system prompt update to enforce freshness transparency, when tests run, then `tests/app/test_prompts.py` verifies the new freshness instructions are present in `_BASE_SYSTEM_PROMPT`.

**AC6:** Given the staleness threshold is a configurable value, when `DATA360_STALENESS_THRESHOLD_YEARS` env var is set, then the system prompt injects that threshold dynamically. Default: 2 years.

---

## Tasks / Subtasks

### Task 1: Add data freshness instructions to system prompt in `app/prompts.py` (AC: #1, #2, #3)

- [x] In `_BASE_SYSTEM_PROMPT`, add a **DATA FRESHNESS** section after CITATION MARKERS and before STYLE
- [x] Add `staleness_threshold_years: int = 2` parameter to `get_system_prompt()`.
- [x] Inject `{staleness_threshold}` dynamically: replace placeholder with actual value before returning prompt string.
- [x] Keep `SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT` alias intact (staleness threshold stays at default 2 for backward compat).

### Task 2: Wire staleness threshold from config in `app/config.py` (AC: #6)

- [x] Add `staleness_threshold_years: int = Field(2, alias="DATA360_STALENESS_THRESHOLD_YEARS")` to `Settings`.
- [x] In `app/chat.py`, pass `config.staleness_threshold_years` to `get_system_prompt()` when constructing the system prompt.
- [x] Update `.env.example` to include `DATA360_STALENESS_THRESHOLD_YEARS=2`.

### Task 3: Verify `app/citations.py` year extraction is correct end-to-end (AC: #4)

- [x] Review `_collapse_years` and `deduplicate_references` — confirmed `TIME_PERIOD` parsing handles all formats.
- [x] Added `_parse_time_period_year()` and `_parse_time_period_years()` helpers to handle: simple year (`"2022"`), quarter (`"2022Q1"`), range (`"2015-2022"`).
- [x] Updated `extract_references` to use `_parse_time_period_years()` for all TIME_PERIOD values.

### Task 4: Write/update tests (AC: #5, #6)

- [x] `tests/app/test_prompts.py` — `TestDataFreshnessTransparency` class with 10 tests covering DATA FRESHNESS section presence, threshold injection, default threshold, SYSTEM_PROMPT alias resolution, individual instruction checks.
- [x] `tests/app/test_citations.py` — added `TestParseTimePeriodYear`, `TestParseTimePeriodYears`, `TestExtractReferencesTimePeriod` classes for TIME_PERIOD edge cases.
- [x] Full test suite: `uv run pytest` — 339/339 passing.

---

## Dev Notes

### Why system-prompt approach for freshness (not code-side injection)

Story 3.2 already built a citation registry that captures `years` per reference. The `years` field (e.g., `"2015-2022"`) is passed to the reference list appended server-side. However, the *inline* year display (e.g., "Brazil emitted X in 2022") must come from Claude's narrative — the server cannot retroactively inject years into every prose sentence without rebuilding the full response parser. Therefore, the correct approach is to instruct the LLM via system prompt to always narrate years inline, and to warn when data is stale. This is consistent with how multi-turn context, gap flagging, and citation markers are all handled: instructions in the prompt, deterministic reference list from the server.

### `get_system_prompt()` call sites

- `app/chat.py` — check where `get_system_prompt()` is called and add `staleness_threshold_years=config.staleness_threshold_years`.
- `SYSTEM_PROMPT` alias in `app/prompts.py` — leave as `_BASE_SYSTEM_PROMPT` (no threshold arg needed for the static alias; it's for backward compat with any direct import, default threshold = 2).

### `TIME_PERIOD` formats in Data360 API

From architecture: `TIME_PERIOD` is a parameter and also a field in data records. Values observed in practice:
- Simple year: `"2022"`
- Quarter notation: `"2022Q1"` — parse year as `int("2022Q1"[:4])`
- Range string: `"2015-2022"` — split on `-`, parse first 4 chars of each segment as int

Update `extract_references` in `app/citations.py` to handle all three cases in `year_raw = record.get("TIME_PERIOD")` parsing.

### Project Structure Notes

- `app/prompts.py` — main change (DATA FRESHNESS section + `staleness_threshold_years` param)
- `app/config.py` — add `DATA360_STALENESS_THRESHOLD_YEARS` setting
- `app/chat.py` — pass threshold to `get_system_prompt()`
- `app/citations.py` — defensive TIME_PERIOD parsing (edge cases only)
- `tests/app/test_prompts.py` — new test file
- `tests/app/test_citations.py` — additive tests for TIME_PERIOD parsing

### References

- FR10, FR11: PRD §Functional Requirements (data year display + stale data warning)
- Architecture §Data Freshness: "Every response must show the most recent data year and warn when >2 years old"
- [Source: app/prompts.py] — `_BASE_SYSTEM_PROMPT`, `get_system_prompt()`, `DOCUMENT_SEARCH_SECTION`
- [Source: app/citations.py] — `extract_references`, `_collapse_years`, `deduplicate_references`
- [Source: app/chat.py#_agentic_loop] — where `get_system_prompt()` is called and tool outputs collected
- [Source: app/config.py] — `Settings` with existing `rag_enabled`, `rag_max_upload_mb` fields
- Story 3.2: `_bmad-output/implementation-artifacts/3-2-citation-registry-pipeline.md`

### Branch & Commit Conventions

- Branch: `story/3-3-data-freshness-transparency`
- Commits: `feat(3-3): ...` / `test(3-3): ...` / `chore(3-3): ...`

### PR Conventions

- Reviewers: `--reviewer copilot,felipetio`
- PR description must list all ACs with checkboxes

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (anthropic)

### Debug Log References

- Previous session implemented all tasks (commit f376fd5)
- PR #38 was opened but closed without merge — reopened as new PR
- All 339 tests pass; ruff clean

### Completion Notes List

- ✅ Task 1: Added DATA FRESHNESS section to `_BASE_SYSTEM_PROMPT` with inline year and staleness warning instructions. `get_system_prompt()` now accepts `staleness_threshold_years` param with dynamic `{staleness_threshold}` placeholder injection.
- ✅ Task 2: Added `staleness_threshold_years` field to `Settings` (env: `DATA360_STALENESS_THRESHOLD_YEARS`, default: 2). `app/chat.py` passes value to `get_system_prompt()`.
- ✅ Task 3: Added `_parse_time_period_year()` and `_parse_time_period_years()` helpers in `app/citations.py` to handle plain year, quarter notation (`2022Q1`), and range strings (`2015-2022`). `extract_references` now uses these helpers.
- ✅ Task 4: 22 new tests added — `TestDataFreshnessTransparency` (10 tests in test_prompts.py), `TestParseTimePeriodYear` (4), `TestParseTimePeriodYears` (4), `TestExtractReferencesTimePeriod` (4 in test_citations.py). 339/339 pass.
- ✅ Code review: ruff clean, no lint issues.

### File List

- `.env.example` — added `DATA360_STALENESS_THRESHOLD_YEARS=2` documentation
- `app/chat.py` — pass `staleness_threshold_years=settings.staleness_threshold_years` to `get_system_prompt()`
- `app/citations.py` — added `_parse_time_period_year()`, `_parse_time_period_years()` helpers; updated `extract_references` TIME_PERIOD parsing
- `app/config.py` — added `staleness_threshold_years` setting
- `app/prompts.py` — added DATA FRESHNESS section, updated `get_system_prompt()` signature, updated CITATION MARKERS, added `SYSTEM_PROMPT` alias with resolved placeholder
- `tests/app/test_citations.py` — added `TestParseTimePeriodYear`, `TestParseTimePeriodYears`, `TestExtractReferencesTimePeriod`
- `tests/app/test_chat.py` — updated staleness threshold mock in test
- `tests/app/test_prompts.py` — added `TestDataFreshnessTransparency` class

### Change Log

- 2026-04-03: Implemented data freshness transparency — DATA FRESHNESS system prompt section, configurable staleness threshold, TIME_PERIOD parsing improvements, 22 new tests (339 total passing)
