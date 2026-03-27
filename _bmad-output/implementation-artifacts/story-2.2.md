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

- All tasks implemented and merged via PR #12.
- Copilot review (7 comments) addressed in two follow-up commits on the PR branch before merge.
- Key fixes post-review: removed UUID correlation ID from error handler (cleaner UX); added `Field(ge=1)` to `conversation_history_limit`; fixed unstable `AuthenticationError.__new__()` in tests; tightened assertion to `startswith("⚠️")`.
- 92/92 tests pass. Ruff lint and format clean.

### File List

- `app/chat.py` — streaming Claude integration, history management, error handling
- `app/prompts.py` — new, `SYSTEM_PROMPT` grounding constant
- `app/config.py` — added `conversation_history_limit` setting with `Field(ge=1)`
- `.env.example` — documented `CONVERSATION_HISTORY_LIMIT`
- `tests/app/test_chat.py` — new, comprehensive unit tests for chat handler

### Change Log

- 2026-03-26: Implemented all tasks, opened PR #12 against main.
- 2026-03-26: Copilot review — 7 comments. All addressed in commit `8a07c61`.
- 2026-03-27: Follow-up fix — removed UUID from error handler, show clean generic message. Commit `626bf00`.
- 2026-03-27: PR approved by @felipetio and merged to main.
