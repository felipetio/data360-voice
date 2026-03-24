# Story 1.5: Get Metadata, List Indicators, and Get Disaggregation MCP Tools

Status: review

## Story

As a user exploring World Bank data,
I want to access indicator metadata, browse available indicators per dataset, and check disaggregation dimensions,
so that I can understand what data is available and how it's structured.

## Acceptance Criteria

1. **Given** the MCP server is running
   **When** a user calls `get_metadata(query="&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'")`
   **Then** the tool calls POST `/data360/metadata` with the OData query
   **And** returns indicator metadata including description, topics, and data sources

2. **Given** the MCP server is running
   **When** a user calls `list_indicators(dataset_id="WB_WDI")`
   **Then** the tool calls GET `/data360/indicators?datasetId=WB_WDI`
   **And** returns all available indicators for that dataset

3. **Given** the MCP server is running
   **When** a user calls `get_disaggregation(dataset_id="WB_WDI", indicator_id="WB_WDI_SP_POP_TOTL")`
   **Then** the tool calls GET `/data360/disaggregation` with the correct parameters
   **And** returns available disaggregation dimensions (SEX, AGE, URBANISATION, etc.)

4. **Given** any of these three tools encounters an API error
   **When** the error is processed
   **Then** the tool returns a structured error response following the standard format
   **And** never raises an exception

## Tasks / Subtasks

- [x] Task 1: Implement `get_metadata` tool in `mcp_server/server.py` (AC: 1, 4)
  - [x] Add `@mcp.tool()` decorated async function with `query: str` parameter
  - [x] Call `client._request("POST", "/data360/metadata", json_body=body)` with OData params
  - [x] Extract `value` array from response, use `@odata.count` for total_count
  - [x] Wrap in try/except returning structured error on failure
- [x] Task 2: Implement `list_indicators` tool in `mcp_server/server.py` (AC: 2, 4)
  - [x] Add `@mcp.tool()` decorated async function with `dataset_id: str` parameter
  - [x] Call `client._request("GET", "/data360/indicators", params={"datasetId": dataset_id})` with camelCase param
  - [x] Handle plain JSON array response (not wrapped in `value` key)
  - [x] Wrap in try/except returning structured error on failure
- [x] Task 3: Implement `get_disaggregation` tool in `mcp_server/server.py` (AC: 3, 4)
  - [x] Add `@mcp.tool()` decorated async function with `dataset_id: str` and `indicator_id: str | None = None`
  - [x] Call `client._request("GET", "/data360/disaggregation", params={...})` with camelCase params
  - [x] Handle plain JSON array response (not wrapped in `value` key)
  - [x] Wrap in try/except returning structured error on failure
- [x] Task 4: Create test fixtures from real API responses (AC: 1, 2, 3)
  - [x] Save trimmed real response from `/data360/metadata` as `tests/mcp_server/fixtures/metadata_response.json`
  - [x] Save trimmed real response from `/data360/indicators` as `tests/mcp_server/fixtures/indicators_response.json`
  - [x] Save trimmed real response from `/data360/disaggregation` as `tests/mcp_server/fixtures/disaggregation_response.json`
- [x] Task 5: Write tests in `tests/mcp_server/test_server.py` (AC: 1, 2, 3, 4)
  - [x] TestGetMetadata: success with fixture data, parameter forwarding, empty results, error passthrough, unexpected exception
  - [x] TestListIndicators: success with fixture data, parameter forwarding, empty results, error passthrough, unexpected exception
  - [x] TestGetDisaggregation: success with fixture data, required + optional params, empty results, error passthrough, unexpected exception

## Dev Notes

### Architecture Compliance

- **Tool registration:** Use `@mcp.tool()` decorator, add to existing `mcp_server/server.py`
- **Client lifecycle:** `async with Data360Client() as client:` (same pattern as existing tools)
- **No exceptions:** Wrap in try/except, return structured error dict on failure
- **Citation integrity:** API field names must pass through unmutated

### Critical: API Parameter Casing

All three endpoints use **camelCase** parameters, NOT UPPERCASE. The `_map_params()` method would break them (uppercases everything). Use `client._request()` directly with pre-built params, same pattern as `search_indicators` after the fix.

| Endpoint | HTTP | Parameters (camelCase) |
|----------|------|----------------------|
| `/data360/metadata` | POST | JSON body with OData: `$filter`, `$top`, `$select`, `$count`, `search` |
| `/data360/indicators` | GET | `datasetId` (required) |
| `/data360/disaggregation` | GET | `datasetId` (required), `indicatorId` (optional) |

### Real API Response Formats (verified 2026-03-24)

**`/data360/indicators?datasetId=WB_WDI`** returns a plain JSON array:
```json
["WB_WDI_AG_LND_EL5M_RU_K2", "WB_WDI_AG_LND_TOTL_RU_K2", ...]
```
- NOT wrapped in `value` key, just a bare array
- Supports `$skip` and `$top` for pagination

**`/data360/disaggregation?datasetId=WB_WDI&indicatorId=WB_WDI_SP_POP_TOTL`** returns a plain JSON array:
```json
[
  {"field_name": "FREQ", "label_name": "FREQ", "field_value": ["A"]},
  {"field_name": "REF_AREA", "label_name": "REF_AREA", "field_value": ["ABW", "AFE", ...]},
  {"field_name": "TIME_PERIOD", "label_name": "TIME_PERIOD", "field_value": ["2015", "2006", ...]}
]
```
- Plain JSON array of dimension objects
- `field_value` is array of possible values for that dimension

**POST `/data360/metadata`** returns OData format (like searchv2):
```json
{
  "@odata.context": "...",
  "@odata.count": 12827,
  "value": [{...metadata items...}],
  "@odata.nextLink": "..."
}
```
- Same OData pattern as searchv2: `@odata.count` + `value` array
- Each item has `series_description` with `idno`, `name`, `database_id`, `database_name`, `definition_short`, `topics`, etc.
- Supports OData `$filter`, `$top`, `$count`, `$select` in POST body
- The `query` tool param maps to the OData body: parse it and pass as JSON body fields

### Handling the `query` Parameter for get_metadata

The AC shows `get_metadata(query="&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'")`. The `query` string contains OData params prefixed with `&$`. The tool should parse this into a JSON body dict for the POST request. Approach:

```python
# Parse query like "&$filter=...&$top=5" into {"$filter": "...", "$top": "5"}
# Then add "$count": True for total_count support
```

Alternatively, keep it simpler: pass the query string as-is to the endpoint URL. Since `_request` supports both `params` and `json_body`, try appending to the URL or passing as query params. Test which approach the API accepts.

**Simplest approach:** Pass OData params as JSON body (POST):
```python
body = {"$count": True}
# Parse user query string into body params
# e.g., "$filter=..." -> body["$filter"] = "..."
```

### Response Format for Each Tool

All tools must return the standard format:
```python
# get_metadata (OData response)
{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": total > returned}

# list_indicators (plain array)
{"success": True, "data": ["IND_1", "IND_2", ...], "total_count": N, "returned_count": N, "truncated": False}

# get_disaggregation (plain array)
{"success": True, "data": [{...dimensions...}], "total_count": N, "returned_count": N, "truncated": False}
```

For `list_indicators` and `get_disaggregation`, the raw API returns a plain array. The tool wraps it in the standard format. Since `_request()` returns raw JSON, when it's a list (not a dict), it won't have `success: False` error format, handle accordingly.

### Handling Plain Array Responses

`client._request()` returns raw API JSON. For `/data360/data` and `/data360/metadata`, this is a dict. But for `/data360/indicators` and `/data360/disaggregation`, it's a **plain list**. The error check `response.get("success") is False` will fail on lists. Handle this:

```python
response = await client._request("GET", "/data360/indicators", params=params)
# If _request returns a dict with success=False, it's an error
if isinstance(response, dict) and response.get("success") is False:
    return response
# Otherwise, response is the data (could be list or dict)
results = response if isinstance(response, list) else response.get("value", [])
```

### Existing Code to Reuse

- `mcp_server/server.py` - Add 3 tools here (same file as search_indicators, get_data)
- `mcp_server/data360_client.py` - Use `client._request()` directly (bypass `_map_params`)
- `tests/mcp_server/test_server.py` - Add tests to existing file, reuse `mock_client` fixture
- Test fixture pattern: load real API responses via `_load_fixture()` helper (already exists)

### Testing Standards

- **File:** Add to existing `tests/mcp_server/test_server.py`
- **Fixture:** Reuse `mock_client` fixture from existing tests
- **Fixtures:** Create real API response files in `tests/mcp_server/fixtures/`
- **Mocking:** Mock `client._request` return values (same as search_indicators tests)
- **Pattern:** Create `TestGetMetadata`, `TestListIndicators`, `TestGetDisaggregation` classes
- **Coverage per tool:** success, params, empty, error passthrough, unexpected exception (minimum 5 tests each)

### Previous Story Learnings

- **From Story 1.3 fix:** searchv2 API expects lowercase params, not UPPERCASE. `_map_params` breaks it. Use `client._request()` directly with correct casing.
- **From Story 1.4:** Time period params need camelCase. Built params manually and called `_paginated_get` directly. Same pattern applies here.
- **From Story 1.3/1.4:** Always create fixtures from real API responses, not fabricated data. Fabricated fixtures led to bugs (wrong response key, wrong field names).
- **From Story 1.4 review:** Test mock fixture must preserve `_map_params` via `MockClient._map_params = Data360Client._map_params` (already in shared fixture).
- **From all stories:** Exception guard (try/except) wraps entire tool body. Never raise from tools.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5] - Acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] - Tool signatures, response format
- [Source: _bmad-output/planning-artifacts/prd.md#FR4,FR33] - Metadata retrieval requirements
- [Source: mcp_server/data360_client.py] - Client interface (_request method)
- [Source: mcp_server/server.py] - Existing tool patterns (search_indicators, get_data)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented 3 MCP tools: get_metadata, list_indicators, get_disaggregation
- All use `client._request()` directly with camelCase params (bypassing `_map_params` UPPERCASE)
- get_metadata passes `query` string as JSON body `{"query": "..."}` to POST /data360/metadata
- list_indicators and get_disaggregation handle plain JSON array responses (not wrapped in `value`)
- Fixtures created from real API responses (metadata, indicators, disaggregation)
- 17 new tests across 3 test classes, all passing
- Full regression suite: 93 tests pass, 0 failures

### File List

- mcp_server/server.py (modified: added get_metadata, list_indicators, get_disaggregation tools)
- tests/mcp_server/test_server.py (modified: added TestGetMetadata, TestListIndicators, TestGetDisaggregation)
- tests/mcp_server/fixtures/metadata_response.json (new: real API response)
- tests/mcp_server/fixtures/indicators_response.json (new: real API response)
- tests/mcp_server/fixtures/disaggregation_response.json (new: real API response)
