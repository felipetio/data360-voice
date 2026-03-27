# Story 2.3: MCP Client Integration with Claude Tool Use

Status: review

## Story

As a user,
I want my natural language questions to be processed by Claude using the MCP server tools,
so that my questions are answered with real World Bank data.

## Acceptance Criteria

1. **Given** the Chainlit app is running with MCP client connected to the MCP server, **when** a user types "What are CO2 emissions in Brazil?", **then** Chainlit sends the message to Claude API with MCP tools available, Claude selects appropriate tools (search_indicators, then get_data), tool calls are displayed as intermediate steps in the Chainlit UI, and the final response contains data from the World Bank Data360 API
2. **Given** the MCP server is connected via HTTP Streamable transport, **when** tool calls are made, **then** the MCP client (Chainlit native handlers: `@cl.on_mcp_connect`, `@cl.on_mcp_disconnect`) manages the connection, and tool results flow back to Claude for response generation
3. **Given** the Data360 API is unavailable, **when** a tool call fails, **then** the structured error response is passed to Claude, and Claude narrates the failure transparently to the user (NFR9)

## Implementation Status: Already Complete

All 3 ACs were implemented in Story 2.2 Phase 2 (commit `bb183e6`, PR #13, branch `story/2.2-mcp-client-integration`). The implementation includes:

- `@cl.on_mcp_connect` / `@cl.on_mcp_disconnect` handlers in `app/chat.py`
- `_agentic_loop()`: Claude messages.stream() with MCP tools -> handle tool_use blocks -> call MCP via `ClientSession.call_tool()` -> feed results back -> repeat until `stop_reason != "tool_use"`
- `cl.Step` intermediate steps shown in UI for each tool call
- Error handling: MCP unavailable (session=None) surfaces error string to Claude; MCP tool errors (isError=True) also surfaced as text
- Streaming preserved for final text response
- `[features.mcp] enabled = true` in `.chainlit/config.toml` with SSE, streamable-http, and stdio all enabled
- 11 unit tests in `TestMcpToolUse` class; 103/103 total tests pass

## Tasks / Subtasks

- [x] Task 1: Validate existing implementation against ACs (AC: #1, #2, #3)
  - [x] Verify `_agentic_loop()` correctly handles multi-step tool chains (search_indicators -> get_data)
  - [x] Verify tool call intermediate steps render in Chainlit UI
  - [x] Verify error path when MCP server is disconnected
  - [x] Verify error path when MCP tool returns `isError=True`
  - [x] Run full test suite: `uv run python -m pytest` (expect 103+ pass)

- [x] Task 2: Make Claude model configurable (improvement)
  - [x] Add `claude_model: str = "claude-haiku-4-5"` to `app/config.py` Settings
  - [x] Add `CLAUDE_MODEL` to `.env.example`
  - [x] Replace hardcoded `"claude-haiku-4-5"` in `_agentic_loop()` with `settings.claude_model`
  - [x] Update existing tests if they assert on model name

- [x] Task 3: Make max_tokens configurable (improvement)
  - [x] Add `claude_max_tokens: int = Field(default=4096, ge=1)` to `app/config.py` Settings
  - [x] Add `CLAUDE_MAX_TOKENS` to `.env.example`
  - [x] Replace hardcoded `4096` in `_agentic_loop()` with `settings.claude_max_tokens`

- [x] Task 4: Add integration-level verification tests (AC: #1, #2)
  - [x] Test that a full agentic loop with multiple tool calls produces correct history structure
  - [x] Test that tool results are correctly formatted for Claude's tool_result content blocks
  - [x] Verify history includes both text and tool_use content blocks after multi-step chains

## Dev Notes

### What's Already Implemented (from Story 2.2 Phase 2)

All core MCP client integration is in `app/chat.py:139-233`. Key patterns:

**Agentic Loop** (`_agentic_loop`):
```python
while True:
    async with client.messages.stream(**call_kwargs) as stream:
        # collect text tokens, get final message
    if stop_reason != "tool_use":
        return streamed_text
    # process tool_use blocks via MCP ClientSession.call_tool()
    # append tool_results to history, loop again
```

**MCP Tool Conversion** (`_mcp_tools_to_anthropic`):
Converts MCP `Tool` objects to Anthropic API format: `{name, description, input_schema}`.

**Error Handling**:
- MCP session=None: returns error string as tool result (no crash)
- MCP tool isError=True: prefixes with "Error:" and passes to Claude
- MCP call exception: catches, logs, returns error string

### Remaining Work: Configuration Hardcoding

Two values are hardcoded in `_agentic_loop()` that should be configurable:
- `model="claude-haiku-4-5"` at `app/chat.py:155` -> use `settings.claude_model`
- `max_tokens=4096` at `app/chat.py:156` -> use `settings.claude_max_tokens`

These follow the existing pattern in `app/config.py` where all config uses `pydantic_settings.BaseSettings` with env var loading.

### MCP Connection Model

The MCP connection is **user-initiated** via the Chainlit UI. Users add the MCP server URL (default `http://localhost:8001`) through the UI's MCP panel. This triggers `@cl.on_mcp_connect` which lists tools and stores the session + tools in `cl.user_session`.

`app/config.py` has `mcp_server_url: str = "http://localhost:8001"` but this is not used programmatically yet. The Chainlit UI is the connection point, which matches the AC requirement for "Chainlit native handlers".

### Files to Modify

| File | Change |
|------|--------|
| `app/config.py` | Add `claude_model` and `claude_max_tokens` settings |
| `app/chat.py` | Replace hardcoded model/max_tokens with settings |
| `.env.example` | Document `CLAUDE_MODEL` and `CLAUDE_MAX_TOKENS` |
| `tests/app/test_chat.py` | Update any tests that assert on model name |

### Project Structure Notes

- `app/chat.py` is the single file handling Chainlit events and Claude API calls, aligned with architecture
- `app/config.py` uses pydantic-settings for all env var config, aligned with project pattern
- `tests/app/test_chat.py` mirrors source structure, aligned with testing conventions
- MCP server runs as a separate process (not imported), clean architectural boundary preserved

### Testing Standards

- Tests use `unittest.mock.patch` to mock `app.chat.client` (Anthropic client)
- `FakeStream` helper class simulates streaming responses with `text_stream` and `get_final_message()`
- MCP `ClientSession` is mocked via `AsyncMock`
- `cl.user_session` is mocked to return test values for history, mcp_session, mcp_tools
- Group tests in classes with docstrings referencing AC numbers

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3] - AC definitions
- [Source: _bmad-output/planning-artifacts/architecture.md#Boundary 3] - Web App <-> MCP Server boundary
- [Source: _bmad-output/implementation-artifacts/story-2.2.md#Phase 2] - Implementation details
- [Source: _bmad-output/project-context.md#Framework-Specific Rules] - FastMCP patterns
- [Source: _bmad-output/project-context.md#Testing Rules] - Test conventions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None required.

### Completion Notes List

- Task 1: Validated all 3 ACs against existing implementation. All code paths verified (agentic loop, MCP connect/disconnect, error handling). 136/136 tests pass.
- Task 2: Added `claude_model` setting to `app/config.py`, replaced hardcoded model in `_agentic_loop()`, documented in `.env.example`. 3 new tests.
- Task 3: Added `claude_max_tokens` setting to `app/config.py`, replaced hardcoded 4096 in `_agentic_loop()`, documented in `.env.example`. 3 new tests.
- Task 4: Added 3 integration tests in `TestAgenticLoopIntegration`: multi-tool chain history structure, tool_result formatting, mixed text+tool_use content blocks.

### Change Log

- Made Claude model configurable via `CLAUDE_MODEL` env var (Date: 2026-03-27)
- Made max_tokens configurable via `CLAUDE_MAX_TOKENS` env var (Date: 2026-03-27)
- Added integration-level tests for agentic loop history structure (Date: 2026-03-27)

### File List

- `app/config.py` (modified) - Added `claude_model` and `claude_max_tokens` settings
- `app/chat.py` (modified) - Replaced hardcoded model and max_tokens with settings
- `.env.example` (modified) - Documented `CLAUDE_MODEL` and `CLAUDE_MAX_TOKENS`
- `tests/app/test_chat.py` (modified) - Added 9 new tests (config, API call, integration)
