# Story 2.2: Claude API Integration with Streaming

Status: done

## Story

As a user,
I want the chat app to send my messages to Claude and stream back responses token by token,
so that I get fast, real-time AI replies instead of waiting for a full response.

## Acceptance Criteria

1. Given a running app with a valid `ANTHROPIC_API_KEY`, when I send a message, then Claude streams a response token-by-token in the Chainlit UI
2. A grounding system prompt (`SYSTEM_PROMPT` in `app/prompts.py`) constrains Claude to the Data360 / World Bank domain
3. Conversation history is maintained across turns and included in each API call
4. Conversation history is bounded by `conversation_history_limit` (default 10 messages, configurable via `CONVERSATION_HISTORY_LIMIT` env var, must be ≥ 1)
5. If the Claude API call fails, the user sees a generic error message and the exception is logged server-side (no raw exception text exposed to the user)
6. All new behaviour is covered by unit tests; all 92 tests pass

## Tasks / Subtasks

- [ ] Task 1: Replace echo stub with streaming Claude integration (AC: #1, #5)
  - [ ] Use `anthropic.AsyncAnthropic(...).messages.stream()` in `app/chat.py`
  - [ ] Stream tokens with `msg.stream_token(text)`, finalize with `msg.update()`
  - [ ] Show generic error to user on failure; log exception server-side
  - [ ] Commit: `feat(chat): replace echo stub with streaming Claude API calls`

- [ ] Task 2: Add grounding system prompt (AC: #2)
  - [ ] Create `app/prompts.py` with `SYSTEM_PROMPT` constant
  - [ ] Pass `system=SYSTEM_PROMPT` to every API call
  - [ ] Commit: `feat(prompts): add grounded system prompt for World Bank data assistant`

- [ ] Task 3: Add conversation history with bounded limit (AC: #3, #4)
  - [ ] Store history in `cl.user_session`; append user + assistant turns
  - [ ] Trim to last N messages immediately after append (before API call)
  - [ ] Persist trimmed history to session before API call so failures don't grow it unbounded
  - [ ] Add `conversation_history_limit: int = Field(default=10, ge=1)` to `app/config.py`
  - [ ] Document `CONVERSATION_HISTORY_LIMIT` in `.env.example`
  - [ ] Commits: `chore(config): add CONVERSATION_HISTORY_LIMIT setting`

- [ ] Task 4: Unit tests (AC: #6)
  - [ ] Test token-by-token streaming assembly
  - [ ] Test history trimming and persistence
  - [ ] Test system prompt inclusion
  - [ ] Test error surfacing (generic message, no raw exception)
  - [ ] Commit: `test(chat): unit tests for streaming Claude integration`

## Dev Notes

### Streaming Pattern

```python
async with client.messages.stream(
    model="claude-haiku-4-5",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    messages=history,
) as stream:
    async for text in stream.text_stream:
        await msg.stream_token(text)
await msg.update()
```

### History Trimming & Session Safety

Trim and persist history *before* the API call so a failed request doesn't grow the session unbounded:

```python
history = history[-max_msgs:]
cl.user_session.set("history", history)
```

After a successful reply, append the assistant turn and persist again.

### Error Handling

Log the full exception server-side; show only a generic message to the user (no UUIDs, no raw exception text):

```python
except Exception as e:
    logger.exception("Error calling Claude API: %s", e)
    await msg.remove()
    await cl.Message(content="⚠️ Sorry, I couldn't reach the AI service. Please try again.").send()
```

### Dependencies

Builds on Story 2.1 app scaffold. MCP integration (Story 2.3) will extend `on_message` to call the MCP server before / after Claude.

## Test Cases

| # | Scenario | Steps | Expected Result |
|---|----------|-------|----------------|
| TC1 | Tokens stream to UI | Send a message | Tokens appear incrementally, final message assembled correctly |
| TC2 | System prompt included | Inspect API call | `system=SYSTEM_PROMPT` passed in every request |
| TC3 | History appended each turn | Send multiple messages | Each API call includes prior turns |
| TC4 | History trimmed at limit | Send > 10 messages | Only last N messages sent to API |
| TC5 | Trim persisted before API call | API call fails mid-turn | Next turn's history is still bounded |
| TC6 | Generic error on failure | Simulate API error | User sees generic message; raw exception not shown |
| TC7 | All tests pass | `uv run pytest tests/` | 92 tests green |

## Dev Agent Record

### Agent Model Used

anthropic/claude-sonnet-4-6 (via OpenClaw subagent)

### Completion Notes List

**Phase 1 — Claude API Streaming (PR #12, merged 2026-03-27):**
- All streaming tasks implemented and merged via PR #12.
- Copilot review (7 comments) addressed in two follow-up commits on the PR branch before merge.
- Key fixes post-review: removed UUID correlation ID from error handler (cleaner UX); added `Field(ge=1)` to `conversation_history_limit`; fixed unstable `AuthenticationError.__new__()` in tests; tightened assertion to `startswith("⚠️")`.
- 92/92 tests pass. Ruff lint and format clean.

**Phase 2 — MCP Client Integration (PR #13, 2026-03-27):**
- Extended `app/chat.py` with `@cl.on_mcp_connect` / `@cl.on_mcp_disconnect` handlers using Chainlit's native MCP client support.
- Implemented agentic tool-use loop: Claude receives MCP tools → returns `tool_use` blocks → tools executed via `ClientSession.call_tool()` → results fed back → loop until `stop_reason != "tool_use"`.
- Enabled `[features.mcp] enabled = true` in `.chainlit/config.toml`.
- Tool calls shown as intermediate steps via `cl.Step` in the Chainlit UI.
- If MCP server is unavailable (session=None), error message is passed to Claude as a tool result so Claude can narrate the failure gracefully (NFR9).
- MCP tool errors (isError=True) are also surfaced as error strings to Claude rather than raising exceptions.
- Streaming preserved: final text response is streamed token-by-token; tool call steps are non-streaming.
- 11 new unit tests cover the MCP integration path; 103/103 total tests pass.
- Ruff lint and format clean.

### File List

- `app/chat.py` — full MCP agentic loop + streaming; `@cl.on_mcp_connect`/`@cl.on_mcp_disconnect` handlers; helper functions `_mcp_tools_to_anthropic` and `_extract_tool_result_text`
- `app/prompts.py` — `SYSTEM_PROMPT` grounding constant (unchanged)
- `app/config.py` — `mcp_server_url` setting already present (no changes needed)
- `.chainlit/config.toml` — `[features.mcp] enabled = true`
- `tests/app/test_chat.py` — 11 new `TestMcpToolUse` tests; existing 8 tests updated with `FakeStream.get_final_message()` support

### Change Log

- 2026-03-26: Phase 1 — streaming implementation, opened PR #12 against main.
- 2026-03-26: Copilot review — 7 comments. All addressed in commit `8a07c61`.
- 2026-03-27: Follow-up fix — removed UUID from error handler. Commit `626bf00`.
- 2026-03-27: PR #12 approved by @felipetio and merged to main.
- 2026-03-27: Phase 2 — MCP client integration, opened PR #13 against main (branch: story/2.2-mcp-client-integration).
