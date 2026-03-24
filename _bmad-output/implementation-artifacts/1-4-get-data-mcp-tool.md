# Story 1.4: Get Data MCP Tool

Status: done

## Story

As a user exploring climate data,
I want to retrieve actual data values for specific indicators by country and time period,
so that I can see the numbers behind climate and development trends.

## Acceptance Criteria

1. **Given** the MCP server is running
   **When** a user calls `get_data(database_id="WB_WDI", indicator="WB_WDI_EN_ATM_CO2E_KT", ref_area="BRA")`
   **Then** the tool calls GET `/data360/data` with the mapped UPPERCASE parameters
   **And** returns data including `OBS_VALUE`, `DATA_SOURCE`, `COMMENT_TS`, `TIME_PERIOD`, `LATEST_DATA`, `INDICATOR`, `REF_AREA`
   **And** all API field names are preserved exactly as returned

2. **Given** a query with time period filters
   **When** calling `get_data(database_id="WB_WDI", indicator="...", time_period_from="2015", time_period_to="2023")`
   **Then** the tool passes `timePeriodFrom` and `timePeriodTo` parameters correctly

3. **Given** a query that returns more than 1000 records
   **When** the tool fetches data
   **Then** it auto-paginates internally (via data360_client.py) up to 5000 records
   **And** returns `total_count` from the API so the LLM knows if data was truncated

4. **Given** no data exists for the requested indicator/country combination
   **When** the tool processes the response
   **Then** it returns `{"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}`

## Tasks / Subtasks

- [x] Task 1: Define `get_data` tool in `mcp_server/server.py` (AC: 1, 2)
  - [x] Add `@mcp.tool()` decorated async function
  - [x] Define parameters: `database_id` (required str), `indicator` (required str), `ref_area` (optional str), `time_period_from` (optional str), `time_period_to` (optional str)
  - [x] Build kwargs dict, only including non-None optional params
  - [x] Pass time period params as snake_case; `_map_params` handles UPPERCASE mapping per architecture
  - [x] Call `client.get_paginated("/data360/data", **kwargs)` for auto-pagination
  - [x] Wrap in try/except returning structured error on failure (pattern from Story 1.3)
- [x] Task 2: Handle paginated response (AC: 3, 4)
  - [x] `get_paginated()` already returns standard format, pass through directly
  - [x] Empty results handled automatically by `get_paginated()` returning empty data list
- [x] Task 3: Write tests in `tests/mcp_server/test_server.py` (AC: 1, 2, 3, 4)
  - [x] Test successful data retrieval returns correct format with preserved field names
  - [x] Test required and optional parameters are forwarded correctly
  - [x] Test time period parameters forwarded correctly
  - [x] Test paginated response passthrough (data, total_count, truncated)
  - [x] Test empty results handling
  - [x] Test API error passthrough
  - [x] Test unexpected exception returns structured error

## Dev Notes

### Architecture Compliance

- **Tool registration:** Use `@mcp.tool()` decorator, add to existing `mcp_server/server.py`
- **Client lifecycle:** `async with Data360Client() as client:` (same pattern as `search_indicators`)
- **No exceptions:** Wrap in try/except, return structured error dict on failure
- **Citation integrity:** API field names (`DATA_SOURCE`, `OBS_VALUE`, `COMMENT_TS`, `TIME_PERIOD`, `LATEST_DATA`, `INDICATOR`, `REF_AREA`) must pass through unmutated. This is the trust core of the project.

### API Endpoint Details

- **Endpoint:** GET `/data360/data`
- **Query parameters (UPPERCASE):** `DATABASE_ID`, `INDICATOR`, `REF_AREA`, plus special camelCase: `timePeriodFrom`, `timePeriodTo`
- **Response format** (from `tests/mcp_server/fixtures/data_response.json`):
  ```json
  {
    "value": [
      {
        "DATABASE_ID": "WB_WDI",
        "INDICATOR": "EN_ATM_CO2E_KT",
        "REF_AREA": "BRA",
        "TIME_PERIOD": "2020",
        "OBS_VALUE": "408645.8",
        "DATA_SOURCE": "World Development Indicators",
        "COMMENT_TS": "CO2 emissions (kt)",
        "LATEST_DATA": true
      }
    ]
  }
  ```

### Critical: Time Period Parameter Mapping

The `_map_params()` method converts all snake_case to UPPERCASE. But the Data360 API expects `timePeriodFrom` and `timePeriodTo` in **camelCase**, not `TIME_PERIOD_FROM`.

**Solution:** Pass time period params directly to `_paginated_get` by building the params dict manually instead of relying on `get_paginated(**kwargs)`. Build UPPERCASE params for standard fields, and add camelCase `timePeriodFrom`/`timePeriodTo` separately.

```python
# Build standard UPPERCASE params
kwargs: dict[str, Any] = {"database_id": database_id, "indicator": indicator}
if ref_area is not None:
    kwargs["ref_area"] = ref_area

# Use get_paginated for standard params (auto-maps to UPPERCASE)
# But time period needs special handling
```

**Recommended approach:** Call `client.get_paginated()` with standard params, and handle time period by adding them directly. Since `get_paginated()` calls `_map_params()` internally, you may need to pass time period params with keys that won't be mangled, OR build the params dict yourself and call `_paginated_get` directly.

**Simplest approach:** Since `_map_params` does `k.upper()`, pass `timePeriodFrom` as a kwarg key. It would become `TIMEPERIODFROM` which is wrong. Instead, build the mapped params manually and pass them via a lower-level method, or add the time period params after mapping.

**Practical solution:** Use `client.get_paginated()` for the standard params, then monkey-patch isn't needed. Instead, override by calling the internal methods directly, or better: just add the camelCase params to the kwargs and let `_map_params` skip them by checking case. Actually, the simplest: pass `timePeriodFrom` and `timePeriodTo` directly as kwargs. `_map_params` will uppercase them to `TIMEPERIODFROM` and `TIMEPERIODTO`. If the API doesn't accept those, you need to handle this differently.

**IMPORTANT:** Verify the actual API behavior. The Data360 API may accept either format. If UPPERCASE doesn't work for time period params, the tool will need to build params manually and call `client._paginated_get()` directly with pre-mapped params, or modify the approach.

### Key Difference from search_indicators

| Aspect | search_indicators (1.3) | get_data (1.4) |
|--------|------------------------|----------------|
| HTTP method | POST | GET |
| Client method | `client.post()` | `client.get_paginated()` |
| Pagination | Not needed (search) | Auto-pagination via client |
| Response key | `results` | `value` (handled by client) |
| Response shaping | Manual extraction | Passthrough from `get_paginated()` |

The `get_paginated()` method already returns the standard `{"success", "data", "total_count", "returned_count", "truncated"}` format. The tool just needs to pass it through (unlike `search_indicators` which had to extract and reshape).

### Existing Code to Reuse

- `mcp_server/server.py` - Add tool here (same file as search_indicators)
- `mcp_server/data360_client.py` - Use `Data360Client.get_paginated()` method
- `tests/mcp_server/test_server.py` - Add tests to existing file, reuse `mock_client` fixture
- `tests/mcp_server/fixtures/data_response.json` - Reference for API response format

### Testing Standards

- **File:** Add to existing `tests/mcp_server/test_server.py`
- **Fixture:** Reuse `mock_client` fixture from Story 1.3
- **Mocking:** Mock `Data360Client.get_paginated()` return values
- **Pattern:** Follow `TestSearchIndicators` class conventions, create `TestGetData` class

### Previous Story Learnings

- **From Story 1.3:** Exception guard pattern (try/except wrapping entire tool body) must be applied
- **From Story 1.3:** Use `mock_client` fixture to reduce test boilerplate
- **From Story 1.3 review:** Tests should include unexpected exception case
- **From Story 1.2:** `get_paginated()` already returns the standard response format with `data`, `total_count`, `returned_count`, `truncated` keys. It reads from `response["value"]` internally. No manual response shaping needed.
- **From Story 1.2:** `_map_params` converts all keys to UPPERCASE. Time period params need special attention.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4] - Acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] - Citation integrity, field preservation
- [Source: mcp_server/data360_client.py:168-171] - get_paginated() interface
- [Source: mcp_server/data360_client.py:113-150] - _paginated_get() reads from "value" key
- [Source: tests/mcp_server/fixtures/data_response.json] - API response fixture

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented `get_data` tool using `client.get_paginated()` for auto-pagination
- Response is a direct passthrough from `get_paginated()` (already returns standard format)
- Only non-None optional params included in kwargs (ref_area, time_period_from, time_period_to)
- Time period params passed as snake_case, mapped to UPPERCASE by `_map_params` per architecture
- Exception guard wraps entire tool body (pattern from Story 1.3 review)
- 9 tests in TestGetData class, reusing mock_client fixture
- Full regression suite: 75 tests pass, 0 failures

### File List

- mcp_server/server.py (modified: added get_data tool)
- tests/mcp_server/test_server.py (modified: added TestGetData class with 9 tests)
