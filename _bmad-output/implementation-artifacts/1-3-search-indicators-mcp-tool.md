# Story 1.3: Search Indicators MCP Tool

Status: done

## Story

As a user querying World Bank data,
I want to search for relevant indicators using natural language,
so that I can find the right data indicators for my climate or development questions.

## Acceptance Criteria

1. **Given** the MCP server is running
   **When** a user calls `search_indicators(query="drought Brazil")`
   **Then** the tool calls POST `/data360/searchv2` with `{"search": "drought Brazil", "top": 10, "skip": 0}`
   **And** returns `{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": False}`
   **And** each result includes indicator ID, name, database_id, and description

2. **Given** a search with optional parameters
   **When** calling `search_indicators(query="CO2 emissions", top=5, filter="...")`
   **Then** the tool passes all parameters correctly to the API

3. **Given** a search that returns no results
   **When** the tool processes the empty response
   **Then** it returns `{"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}`

4. **Given** the Data360 API is unavailable
   **When** the tool is called
   **Then** it returns `{"success": False, "error": "<descriptive message>", "error_type": "api_error"}`

## Tasks / Subtasks

- [x] Task 1: Define `search_indicators` tool in `mcp_server/server.py` (AC: 1, 2)
  - [x] Add `@mcp.tool()` decorated async function
  - [x] Define parameters: `query` (required str), `top` (optional int, default 10), `skip` (optional int, default 0), `filter` (optional str)
  - [x] Instantiate `Data360Client` and call `client.post("/data360/searchv2", search=query, top=top, skip=skip, filter=filter)`
  - [x] Transform raw API response into standard tool response format
- [x] Task 2: Handle success response shaping (AC: 1, 3)
  - [x] Extract `results` list from API response (see fixture format below)
  - [x] Build return dict: `{"success": True, "data": results, "total_count": len, "returned_count": len, "truncated": False}`
  - [x] Handle empty results: return `{"success": True, "data": [], "total_count": 0, "returned_count": 0, "truncated": False}`
- [x] Task 3: Handle error responses (AC: 4)
  - [x] If `client.post()` returns `{"success": False, ...}`, pass it through directly
  - [x] Never raise exceptions from the tool function
- [x] Task 4: Write tests in `tests/mcp_server/test_server.py` (AC: 1, 2, 3, 4)
  - [x] Test successful search returns correct format
  - [x] Test optional parameters are forwarded
  - [x] Test empty results handling
  - [x] Test API error passthrough
  - [x] Test parameter defaults (top=10, skip=0)

## Dev Notes

### Architecture Compliance

- **Tool registration:** Use `@mcp.tool()` decorator from FastMCP. The `mcp` instance is already created in `server.py`.
- **Client lifecycle:** Create `Data360Client` inside the tool function using `async with Data360Client() as client:` for proper cleanup. The client is lightweight (lazy httpx init behind lock).
- **No exceptions:** Tool must return a dict, never raise. The `Data360Client` already handles this, just pass through its return values.
- **Parameter naming:** Tool signature uses snake_case (`query`, `top`, `skip`, `filter`). The `client.post()` method handles mapping to UPPERCASE for the API.

### API Endpoint Details

- **Endpoint:** POST `/data360/searchv2`
- **Request body (JSON):** `{"SEARCH": "query text", "TOP": 10, "SKIP": 0}`
  - `client.post()` handles the snake_case -> UPPERCASE mapping automatically
- **Response format** (from `tests/mcp_server/fixtures/searchv2_response.json`):
  ```json
  {
    "results": [
      {
        "indicatorId": "WB_WDI_EN_ATM_CO2E_KT",
        "name": "CO2 emissions (kt)",
        "description": "Carbon dioxide emissions...",
        "topics": ["Climate Change"],
        "datasetName": "World Development Indicators"
      }
    ]
  }
  ```
- **Note:** The `client.post()` wraps the raw API response in `{"success": True, "data": <raw>}`. The raw response has a `results` key, so tool must extract `response["data"]["results"]` to build the final output.

### Response Format Contract

All MCP tools MUST return this consistent structure:

```python
# Success
{"success": True, "data": [...], "total_count": N, "returned_count": M, "truncated": False}

# Error
{"success": False, "error": "message", "error_type": "api_error|timeout"}
```

### Existing Code to Reuse

- `mcp_server/server.py` - Add tool here (do NOT create a new file)
- `mcp_server/data360_client.py` - Use `Data360Client.post()` method
- `mcp_server/config.py` - Config already loaded by client, no changes needed
- `tests/mcp_server/fixtures/searchv2_response.json` - Use this fixture in tests

### Testing Standards

- **Framework:** pytest + pytest-asyncio
- **File:** Create `tests/mcp_server/test_server.py` (new file for MCP tool tests)
- **Mocking:** Mock `Data360Client.post()` return values, not the HTTP layer. Test tool logic, not client internals (client is already tested in `test_data360_client.py`).
- **Pattern:** Follow `test_data360_client.py` conventions: class-based test organization, `@pytest.mark.asyncio`, `unittest.mock.AsyncMock`
- **Import the tool function directly** from `mcp_server.server` and call it, or use FastMCP's test utilities if available

### Project Structure Notes

- Tool goes in `mcp_server/server.py` (add to existing file, do NOT create separate tool files)
- Tests go in `tests/mcp_server/test_server.py` (new file, mirrors source structure)
- No new dependencies needed
- No changes to `config.py` or `data360_client.py`

### Previous Story Learnings

- **From Story 1.2:** The `_map_params` static method converts snake_case to UPPERCASE and filters None values. When calling `client.post(endpoint, search=query, top=top)`, the client will send `{"SEARCH": "...", "TOP": 10}` to the API.
- **From Story 1.2:** `client.post()` returns `{"success": True, "data": <raw_api_json>}` on success. The raw API JSON for searchv2 has a `results` key, so the actual results list is at `response["data"]["results"]`.
- **From Story 1.1 review:** Use module-level `logger = logging.getLogger(__name__)` (already exists in server.py). No print statements.
- **Code review fix pattern:** Previous stories had review fixes applied. Write clean code first time to avoid rework.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3] - Acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns] - Response format, error handling, naming conventions
- [Source: mcp_server/data360_client.py] - Client interface (post method signature)
- [Source: tests/mcp_server/fixtures/searchv2_response.json] - API response fixture

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented `search_indicators` tool in `mcp_server/server.py` using `@mcp.tool()` decorator
- Tool uses `async with Data360Client()` for proper lifecycle management
- Optional `filter` param only forwarded when not None (avoids sending FILTER=None to API)
- Response extracts `results` from nested `response["data"]["results"]` path
- 8 tests covering all 4 ACs: success, defaults, optional params, empty results, error passthrough, timeout, multiple results
- Full regression suite: 65 tests pass, 0 failures

### File List

- mcp_server/server.py (modified: added search_indicators tool + Data360Client import)
- tests/mcp_server/test_server.py (new: 8 tests for search_indicators tool)
