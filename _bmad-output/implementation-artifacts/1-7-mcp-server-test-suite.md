# Story 1.7: MCP Server Test Suite

Status: ready-for-dev

## Story

As a developer,
I want automated tests for the MCP server and API client,
so that I can verify correctness and catch regressions.

## Acceptance Criteria

1. **Given** the test suite in `tests/mcp_server/`, **When** running `uv run pytest tests/mcp_server/`, **Then** all tests pass.

2. **Given** `tests/mcp_server/fixtures/` with sample API responses, **When** `test_data360_client.py` runs, **Then** it tests parameter mapping (snake_case to UPPERCASE), auto-pagination logic, retry behavior on 429/5xx errors, no-retry on 4xx errors, and structured error response format.

3. **Given** `test_server.py`, **When** MCP tool integration tests run, **Then** each of the 5 tools is tested with mocked API responses, tests verify the consistent response format (success/error structure), and tests verify API field names are preserved (DATA_SOURCE, COMMENT_TS, etc.).

## Current State (Pre-Implementation Audit)

**75 tests already pass.** Tests were written organically during Stories 1.2–1.5. All ACs are substantially satisfied. Your job is to audit, fill any gaps, and close this story.

```
tests/
├── __init__.py
├── mcp_server/
│   ├── __init__.py
│   ├── test_project_setup.py       # project structure/config tests (Story 1.1)
│   ├── test_data360_client.py      # API client unit tests (Stories 1.2, 1.5)
│   ├── test_server.py              # MCP tool integration tests (Stories 1.3–1.5)
│   └── fixtures/
│       ├── searchv2_response.json
│       ├── data_response.json
│       ├── metadata_response.json
│       ├── indicators_response.json
│       └── disaggregation_response.json
```

### AC Coverage Map

| AC | Covered By | Status |
|----|-----------|--------|
| AC1: All tests pass | `uv run pytest tests/mcp_server/` | ✓ 75 passing |
| AC2: param mapping snake_case→UPPERCASE | `TestParameterMapping` in test_data360_client.py | ✓ |
| AC2: auto-pagination logic | `TestPaginatedGet` in test_data360_client.py | ✓ |
| AC2: retry on 429/5xx | `TestRequest::test_retry_on_429`, `test_retry_on_503` | ✓ |
| AC2: no-retry on 4xx | `TestRequest::test_no_retry_on_400`, `test_no_retry_on_404` | ✓ |
| AC2: structured error format | All `*_returns_error` tests in TestRequest | ✓ |
| AC3: all 5 tools tested | `TestSearchIndicators`, `TestGetData`, `TestGetMetadata`, `TestListIndicators`, `TestGetDisaggregation` | ✓ |
| AC3: success/error format verified | Every tool has `test_successful_*` and `test_api_error_passthrough` and `test_unexpected_exception_returns_error` | ✓ |
| AC3: API field names preserved | `TestGetData::test_successful_data_retrieval` asserts OBS_VALUE, DATABASE_ID, TIME_PERIOD, INDICATOR, LATEST_DATA | ✓ |

## Tasks / Subtasks

- [ ] Task 1: Run and confirm all tests pass (AC #1)
  - [ ] Run `uv run pytest tests/mcp_server/ -v` — all 75 tests must pass
  - [ ] If any test fails, investigate and fix (do NOT modify tests to pass, fix the source)

- [ ] Task 2: Audit AC2 coverage in `test_data360_client.py` (AC #2)
  - [ ] Confirm `TestParameterMapping` covers snake_case→UPPERCASE mapping including None skipping
  - [ ] Confirm `TestPaginatedGet` covers single-page, multi-page, truncation at 5000, and error cases
  - [ ] Confirm `TestRequest` covers retry on 429, retry on 503, exhausted retries, no-retry on 400/404, timeout, network error, invalid JSON
  - [ ] Add any missing edge cases (only if genuinely missing, not duplicating existing tests)

- [ ] Task 3: Audit AC3 coverage in `test_server.py` (AC #3)
  - [ ] Confirm each of the 5 tools has: a success test, an error passthrough test, and an unexpected-exception test
  - [ ] Confirm API field names (DATA_SOURCE, COMMENT_TS, OBS_VALUE, TIME_PERIOD, INDICATOR, REF_AREA, LATEST_DATA) are present in the data_response.json fixture and flow through to test assertions
  - [ ] Confirm `test_calls_enrich_citation_source` and `test_skips_enrich_on_empty_data` / `test_skips_enrich_on_error` exist in TestGetData

- [ ] Task 4: Verify fixtures are accurate (AC #2, #3)
  - [ ] All 5 fixture files exist in `tests/mcp_server/fixtures/`
  - [ ] `data_response.json` contains: OBS_VALUE, DATA_SOURCE, COMMENT_TS, TIME_PERIOD, INDICATOR, REF_AREA, LATEST_DATA, DATABASE_ID
  - [ ] `searchv2_response.json` contains: value[], @odata.count, series_description with database_id/database_name
  - [ ] No new fixtures needed unless Task 2/3 audit reveals a genuine gap

## Dev Notes

### Architecture: Where to Mock

The `_client` is a **module-level singleton** in `mcp_server/server.py`:
```python
_client = Data360Client()
```

All tests mock at this boundary using `unittest.mock.patch`:
```python
@pytest.fixture
def mock_client():
    instance = AsyncMock()
    instance._db_name_cache = {}
    instance.cache_db_names = Data360Client.cache_db_names.__get__(instance)
    instance.enrich_citation_source = AsyncMock()
    instance._map_params = Data360Client._map_params
    with patch("mcp_server.server._client", instance):
        yield instance
```

**This fixture is defined in `test_server.py` directly (NOT in a conftest.py).** Do not move it — doing so would require updating imports in test_server.py with no functional benefit.

### Mock Pattern for test_data360_client.py

`test_data360_client.py` uses a different pattern — it patches `client._client` (the httpx instance) directly:
```python
def _make_mock_client():
    mock = AsyncMock()
    mock.is_closed = False
    return mock

# Usage:
client._client = mock_http
```

### Known Gaps (Non-Blocking)

1. **No `conftest.py`**: The `mock_client` fixture is defined inside `test_server.py`. This is acceptable — pytest discovers fixtures in the file that uses them. Do not create conftest.py unless you have a genuine cross-file fixture sharing need.

2. **`data_response.json` has `DATA_SOURCE: null`**: This models the WB_SSGD case. The WDI case (DATA_SOURCE populated) is covered by `TestEnrichCitationSource::test_uses_data_source_when_present` in `test_data360_client.py`. Client-level coverage is sufficient per architecture — `server.py` calls `enrich_citation_source()` on the client and the result flows through unchanged.

3. **COMMENT_TS/DATA_SOURCE not explicitly asserted in `test_server.py`**: Both are `null` in the fixture. All fixture fields pass through unchanged (no filtering in the tool code). Adding explicit null assertions adds noise. Only add if an assertion prevents a real regression risk.

### Anti-Patterns to Avoid

- **Do NOT** make live HTTP calls in tests — all API calls must be mocked
- **Do NOT** import `_client` directly — always patch via `mcp_server.server._client`
- **Do NOT** create new source files — this story is test-only
- **Do NOT** modify `test_data360_client.py` or `test_server.py` to make failing tests pass — fix the source code instead
- **Do NOT** add a second `mock_client` fixture in conftest.py if one already exists in test_server.py

### Running Tests

```bash
# Run all mcp_server tests (verbose)
uv run pytest tests/mcp_server/ -v

# Run just the client tests
uv run pytest tests/mcp_server/test_data360_client.py -v

# Run just the server integration tests
uv run pytest tests/mcp_server/test_server.py -v

# Run a specific test class
uv run pytest tests/mcp_server/test_server.py::TestGetData -v
```

### Key Imports in test_server.py

```python
from mcp_server.data360_client import Data360Client
from mcp_server.server import search_indicators, get_data, get_metadata, list_indicators, get_disaggregation
```

Tools are imported directly as async functions. Tests call them directly (e.g., `await search_indicators(query="CO2")`), not via MCP protocol.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 1, Story 1.7]
- [Source: _bmad-output/planning-artifacts/architecture.md — "Testing Framework", "Structure Patterns", "tests/ directory"]
- [Source: _bmad-output/implementation-artifacts/1-6-dual-transport-and-claude-desktop-testing.md — "Key Learnings from Story 1.5"]
- [Source: tests/mcp_server/test_data360_client.py — current implementation]
- [Source: tests/mcp_server/test_server.py — current implementation]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
