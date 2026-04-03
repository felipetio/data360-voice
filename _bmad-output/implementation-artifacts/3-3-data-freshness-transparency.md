# Story 3.3: Data Freshness Transparency

Status: ready-for-dev

## Story

As a researcher,
I want to see the most recent data year for every data point and be warned about stale data,
So that I understand the recency of the information I'm using.

## Acceptance Criteria

**AC1:** Given Claude generates a response with data, when the response is displayed, then every data point shows the most recent data year available — extracted from `TIME_PERIOD` / `LATEST_DATA` fields in the API response (FR10). The `years` field already computed in `app/citations.py` `deduplicate_references` satisfies this requirement; the system prompt must instruct Claude to surface year ranges inline in prose.

**AC2:** Given data where the most recent year in a response is more than 2 years before the current year (i.e., `max(years) < current_year - 2`), when the response is generated, then Claude includes an explicit staleness warning. The warning distinguishes "this is the latest data available from World Bank" from "more recent data may exist" (FR11).

**AC3:** Given a multi-country comparison where data years differ across `REF_AREA` values, when the response is generated, then each country's data year is shown individually and discrepancies in recency are flagged transparently.

**AC4:** Given the citation registry built in Story 3.2, when year ranges are extracted from tool responses via `app/citations.py`, then the `years` field in each reference entry correctly reflects the actual data range in collapsed format (e.g., "2015-2022"). *(Validation of existing Story 3.2 behavior — ensure it works correctly end-to-end.)*

**AC5:** Given a system prompt update to enforce freshness transparency, when tests run, then `tests/app/test_prompts.py` verifies the new freshness instructions are present in `_BASE_SYSTEM_PROMPT`.

**AC6:** Given the staleness threshold is a configurable value, when `DATA360_STALENESS_THRESHOLD_YEARS` env var is set, then the system prompt injects that threshold dynamically. Default: 2 years.

## Tasks / Subtasks

### Task 1: Add data freshness instructions to system prompt in `app/prompts.py` (AC: #1, #2, #3)

- [ ] In `_BASE_SYSTEM_PROMPT`, add a **DATA FRESHNESS** section after CITATION MARKERS and before STYLE:
  ```
  DATA FRESHNESS:
  - For every data claim, include the year(s) inline in prose. Example: "Brazil emitted 467 kt in 2022 [1]" — the year is already in the narrative.
  - When the most recent year in a dataset is more than {threshold} years before the current year, add an explicit warning. Example: "Note: the most recent World Bank data available for this indicator is from 2019, which is over 2 years old. This is the latest officially published figure."
  - In multi-country comparisons where data years differ, note each country's most recent year individually. Example: "Brazil (latest: 2022), India (latest: 2020 — data may lag)."
  - Never omit data year information. If year is ambiguous or missing from the tool response, say so.
  ```
- [ ] Add `staleness_threshold_years: int = 2` parameter to `get_system_prompt()`.
- [ ] Inject `{threshold}` dynamically: replace placeholder with actual value before returning prompt string.
- [ ] Keep `SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT` alias intact (staleness threshold stays at default 2 for backward compat).

### Task 2: Wire staleness threshold from config in `app/config.py` (AC: #6)

- [ ] Add `staleness_threshold_years: int = Field(2, alias="DATA360_STALENESS_THRESHOLD_YEARS")` to `Settings`.
- [ ] In `app/chat.py`, pass `config.staleness_threshold_years` to `get_system_prompt()` when constructing the system prompt.
- [ ] Update `.env.example` to include `DATA360_STALENESS_THRESHOLD_YEARS=2`.

### Task 3: Verify `app/citations.py` year extraction is correct end-to-end (AC: #4)

- [ ] Review `_collapse_years` and `deduplicate_references` — confirm `TIME_PERIOD` parsing handles all formats seen in Data360 API (e.g., `"2022"`, `"2022Q1"`, `"2015-2022"`) without dropping years.
- [ ] If `TIME_PERIOD` can appear as a range string (e.g., `"2015-2022"`), update `extract_references` to split and add both endpoints to `years_set`.
- [ ] Add/update tests in `tests/app/test_citations.py` to cover these edge cases.

### Task 4: Write/update tests (AC: #5, #6)

- [ ] In `tests/app/test_prompts.py` (create if not exists):
  - Test that `_BASE_SYSTEM_PROMPT` contains the string `"DATA FRESHNESS"`.
  - Test that `get_system_prompt(staleness_threshold_years=3)` contains `"3 years"` (threshold injection).
  - Test that `get_system_prompt()` with default produces `"2 years"` (default threshold).
- [ ] In `tests/app/test_citations.py`, add edge-case tests for `TIME_PERIOD` range parsing (Task 3).
- [ ] Run full test suite: `uv run pytest` — all must pass.

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

## Dev Agent Record

### Agent Model Used

_to be filled by dev agent_

### Debug Log References

### Completion Notes List

### File List


# Story 3.3: Data Freshness Transparency — created 2026-04-03