# Story 2.5: Multi-Turn Conversation Support

**Status:** review
**Epic:** 2 — Conversational Climate Data Interface
**Story Key:** 2-5-multi-turn-conversation-support
**Created:** 2026-03-30

---

## Story

As a user,
I want to ask follow-up questions that build on my previous questions,
so that I can explore data progressively without repeating context.

---

## Acceptance Criteria

**AC1:** Given a user asked "What are CO2 emissions in Brazil?" and received an answer, when the user follows up with "How does that compare to Argentina?", then Claude uses the conversation context to understand "that" refers to CO2 emissions (FR7) and the response provides the comparison without the user needing to re-specify the indicator.

**AC2:** Given a multi-turn conversation, when multiple tool calls are made across turns, then each response maintains coherent context with previous answers.

---

## ⚠️ Critical Context: What Is Already Implemented

**Read this before writing a single line of code.**

The conversation history infrastructure is **completely built** in Stories 2.2 and 2.3. Do NOT recreate it.

### Already working in `app/chat.py`:
- `on_chat_start` → initializes `history = []` in `cl.user_session`
- `on_message` → loads history, appends user turn, trims to `conversation_history_limit`, passes full `history` to `_agentic_loop`
- `_agentic_loop` → sends `messages=history` on every Claude API call; appends tool results to history between rounds
- After response → appends assistant reply to history and saves to `cl.user_session`

### Already tested in `tests/app/test_chat.py`:
- `TestStreamingResponse::test_assistant_reply_appended_to_history` — history grows after each turn
- `TestStreamingResponse::test_history_trimmed_to_limit` — CONVERSATION_HISTORY_LIMIT enforced
- `TestStreamingResponse::test_conversation_history_passed_to_api` — prior turns sent to Claude
- `TestAgenticLoopIntegration` — multi-step tool chain history structure verified

**Conclusion:** Claude already receives the full conversation history. Multi-turn context already works mechanically. What this story adds is:
1. **System prompt enhancement** — explicit instructions for context resolution in follow-up questions
2. **Tests** — a dedicated `TestMultiTurnConversation` class verifying the prompt guidance

---

## Tasks / Subtasks

- [x] **Task 1: Add minimal ambiguity-handling guidance to system prompt** (AC: #1, #2)
  - [x] Open `app/prompts.py` — the **only** production file to modify in this story
  - [x] Append a small `MULTI-TURN CONTEXT` section to `SYSTEM_PROMPT` with ONLY these two instructions:
    - If context is genuinely ambiguous in a follow-up (multiple possible referents), briefly state the assumption (e.g., "Assuming you mean CO2 emissions as discussed above...")
    - Do not ask for clarification when the referent is obvious from conversation history
  - [x] NOTE: Claude already receives full conversation history and handles pronoun resolution naturally — do NOT over-instruct. This is a minimal UX polish, not a behavior overhaul.
  - [x] Keep all existing sections intact (grounding constraints, narrative guidelines, citation format, style)
  - [x] Commit: `feat(prompts): add multi-turn ambiguity handling guidance`

- [x] **Task 2: Add multi-turn conversation tests** (AC: #1, #2)
  - [x] Add `TestMultiTurnConversation` class in `tests/app/test_chat.py`
  - [x] Test 1: System prompt includes ambiguity/assumption handling instruction
  - [x] Test 2: System prompt instructs not asking for unnecessary clarification
  - [x] Test 3: Verify `_agentic_loop` passes multi-turn history to Claude (reuse existing mock pattern, assert 2+ turn history is in `messages`)
  - [x] All 160+ existing tests still pass (no regressions)
  - [x] Commit: `test(prompts): multi-turn conversation tests`

---

## Dev Notes

### Files to Modify

| File | Change |
|------|--------|
| `app/prompts.py` | Append `MULTI-TURN CONTEXT RESOLUTION` section to `SYSTEM_PROMPT` |
| `tests/app/test_chat.py` | Add `TestMultiTurnConversation` class |

**DO NOT modify:** `app/chat.py`, `app/config.py`, `app/main.py`, any MCP server files.

### How to Add the Prompt Section

`SYSTEM_PROMPT` in `app/prompts.py` is a multi-line string built with concatenation. Append a new section at the end, before the closing parenthesis:

```python
SYSTEM_PROMPT = (
    # ... existing content ...
    "\n"
    "MULTI-TURN CONTEXT RESOLUTION:\n"
    "- When a follow-up uses pronouns ('that', 'it', 'those') or omits the indicator name, "
    "infer the referent from the previous conversation turn.\n"
    "- If the topic is unambiguous from context, proceed with tool calls using the inferred indicator "
    "and country — do NOT ask for clarification.\n"
    "- If context is genuinely ambiguous, briefly state your assumption "
    "(e.g., 'Assuming you mean CO2 emissions as discussed above...').\n"
    "- When asked to compare to a new country in a follow-up, reuse the same indicator from the "
    "previous turn unless explicitly told otherwise.\n"
    "- Reference previous data naturally in follow-up responses to maintain conversational coherence.\n"
)
```

### How to Write the Tests

Tests assert on `SYSTEM_PROMPT` string content — no real API calls. Follow the exact pattern of `TestNarrativeGeneration` (already in the file):

```python
class TestMultiTurnConversation:
    """AC1/AC2: System prompt instructs multi-turn context resolution."""

    def test_system_prompt_instructs_coreference_resolution(self):
        """AC1: Prompt must instruct resolving pronouns from previous turn context."""
        from app.prompts import SYSTEM_PROMPT
        assert any(
            phrase in SYSTEM_PROMPT.lower()
            for phrase in ["follow-up", "pronoun", "previous", "context", "infer"]
        )

    def test_system_prompt_instructs_no_unnecessary_clarification(self):
        """AC1: When context is unambiguous, Claude must not ask for clarification."""
        from app.prompts import SYSTEM_PROMPT
        assert "clarif" in SYSTEM_PROMPT.lower() or "unambiguous" in SYSTEM_PROMPT.lower()

    def test_system_prompt_instructs_indicator_reuse_on_comparison(self):
        """AC1: On country comparison follow-up, reuse the same indicator."""
        from app.prompts import SYSTEM_PROMPT
        assert any(
            phrase in SYSTEM_PROMPT.lower()
            for phrase in ["reuse", "same indicator", "previous turn", "comparison"]
        )

    async def test_multi_turn_history_passed_to_claude(self, reload_chat):
        """AC2: Full conversation history (2+ turns) is sent to Claude on follow-up."""
        tokens = ["Here is the comparison."]
        msg_mock = _make_fake_cl_message()
        captured_messages = []

        def fake_stream(**kwargs):
            import copy
            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        existing_history = [
            {"role": "user", "content": "What are CO2 emissions in Brazil?"},
            {"role": "assistant", "content": "Brazil's CO2 emissions are 500Mt. (Source: WDI, 2022)"},
        ]

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            session_mock.get.return_value = existing_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "How does that compare to Argentina?"

            await reload_chat.on_message(incoming)

        # History must include prior turns plus the new follow-up user message
        assert len(captured_messages) >= 3
        assert captured_messages[-1]["content"] == "How does that compare to Argentina?"
        # Prior assistant turn must be included
        roles = [m["role"] for m in captured_messages]
        assert "assistant" in roles
```

### Key Patterns From Prior Stories

- Ruff enforces double quotes and line length 120 — run `uv run ruff check . && uv run ruff format .` before committing
- `SYSTEM_PROMPT` is imported directly: `from app.prompts import SYSTEM_PROMPT`
- Tests use `string.lower()` for case-insensitive assertions on prompt text
- `patch("app.chat.cl.user_session")` for mocking session state
- `reload_chat` fixture must be used for async tests (not `app.chat` directly)
- Branch naming: `story/2-5-multi-turn-conversation-support`
- Commit format: `feat(story-key): description`

### Testing Standards

- All assertions on `SYSTEM_PROMPT` use `in` checks (string contains), not exact match
- Use the existing `_make_fake_cl_message()`, `FakeStream`, `_make_session_mock_with_history()` helpers already in the file
- No real API calls in tests; mock `client.messages.stream`
- `asyncio_mode = "auto"` in pyproject.toml — `@pytest.mark.asyncio` is redundant but acceptable
- All tests deterministic; no randomness

### Why NOT Modify `chat.py`

`app/chat.py` already handles everything:
- `history` accumulates across turns in `cl.user_session`
- Full `history` is passed to `_agentic_loop` → sent as `messages=history` to Claude
- History trimming at `conversation_history_limit` (default: 10) prevents unbounded growth

The only gap is that `SYSTEM_PROMPT` doesn't yet explicitly instruct Claude to use coreference resolution. That's the one thing this story adds.

### Configuration Note

`CONVERSATION_HISTORY_LIMIT = 10` (from `app/config.py`) means the last 10 messages are kept. For multi-turn conversations, this means ~5 back-and-forth exchanges are in context. This is intentional and was established in Story 2.2. Do NOT change this default.

### Anti-Patterns

- **DON'T** modify `app/chat.py` — history management is complete and tested
- **DON'T** add any new config settings — nothing new needed
- **DON'T** add a "clear context" command — that's deferred or not in scope
- **DON'T** add persistence to the DB — that is Story 2.6
- **DON'T** write tests that make real API calls to Claude

---

## Project Structure Reference

```
app/
├── prompts.py     ← ONLY file changed in this story
tests/
└── app/
    └── test_chat.py  ← add TestMultiTurnConversation class here
```

---

## References

- [Source: epics.md#Story 2.5] — FR7, acceptance criteria definitions
- [Source: epics.md#Epic 2] — Conversational Climate Data Interface scope
- [Source: 2-4-narrative-response-generation.md] — pattern for prompt-only story; test class structure to follow
- [Source: app/chat.py] — history accumulation and agentic loop; no changes needed
- [Source: app/prompts.py] — SYSTEM_PROMPT to extend
- [Source: tests/app/test_chat.py] — TestNarrativeGeneration pattern; _make_fake_cl_message, FakeStream helpers
- [Source: project-context.md] — anti-patterns, code style rules

---

## Dev Agent Record

_To be filled in by the implementing agent._

### Agent Model Used

claude-sonnet-4-6

### Completion Notes

- Task 1: Appended `MULTI-TURN CONTEXT RESOLUTION` section to `SYSTEM_PROMPT` in `app/prompts.py` with 5 bullet-point instructions covering: pronoun/referent inference from prior turn, no-clarification when unambiguous, state assumption when genuinely ambiguous, reuse same indicator on country-comparison follow-ups, and reference previous data naturally.
- Task 2: Added `TestMultiTurnConversation` class (4 tests) in `tests/app/test_chat.py`:
  - `test_system_prompt_instructs_coreference_resolution` — asserts prompt contains context/infer/previous guidance
  - `test_system_prompt_instructs_no_unnecessary_clarification` — asserts "clarif" or "unambiguous" in prompt
  - `test_system_prompt_instructs_indicator_reuse_on_comparison` — asserts "reuse"/"same indicator"/"comparison" in prompt
  - `test_multi_turn_history_passed_to_claude` — asserts 2+ prior turns in messages sent to Claude
- All 164 tests pass (was 160 prior to this story; 4 new tests added). No regressions.
- Ran ruff check + format; pre-commit passed.
- Committed as: `feat(2-5): add multi-turn ambiguity handling guidance to system prompt and tests`

### File List

- app/prompts.py (modified)
- tests/app/test_chat.py (modified)
