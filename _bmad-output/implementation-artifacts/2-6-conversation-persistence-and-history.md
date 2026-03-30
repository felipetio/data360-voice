# Story 2.6: Conversation Persistence and History

**Status:** review
**Epic:** 2 — Conversational Climate Data Interface
**Story Key:** 2-6-conversation-persistence-and-history
**Created:** 2026-03-30

---

## Story

As a user,
I want my conversations saved so I can return to them later,
so that I don't lose my research progress between sessions.

---

## Acceptance Criteria

**AC1:** Given the Chainlit SQLAlchemy data layer configured with PostgreSQL, when a user has a conversation, then the conversation history is persisted to the database (FR27).

**AC2:** Given a user returns to the application, when they open the interface, then they can start a new conversation (FR28) and access previous conversations from the sidebar (FR29).

**AC3:** Given PostgreSQL is the persistence backend, when the application starts, then it connects using credentials from environment variables (NFR6).

---

## ⚠️ Critical Context: Using Chainlit's SQLAlchemy Community Data Layer

**Read this before touching a single file.**

### Why SQLAlchemy Data Layer (not the native `ChainlitDataLayer`)

This project is a POC — we use the community SQLAlchemy data layer to avoid extra infrastructure costs. It uses the same PostgreSQL already in docker-compose.

**Docs:** https://docs.chainlit.io/data-layers/sqlalchemy

### How It Works

Unlike the native data layer (which auto-activates via `DATABASE_URL` env var), the SQLAlchemy layer requires:
1. **Explicit registration** via `@cl.data_layer` decorator in Python code
2. **Manual schema creation** — SQL DDL must be run against PostgreSQL
3. **`SQLAlchemy` dependency** — must be added to pyproject.toml (asyncpg is already present)

### The Schema (from official docs)

5 tables with **different structure** from the native layer:

```sql
CREATE TABLE users (
    "id" UUID PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" JSONB NOT NULL,
    "createdAt" TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    "id" UUID PRIMARY KEY,
    "createdAt" TEXT,
    "name" TEXT,
    "userId" UUID,
    "userIdentifier" TEXT,
    "tags" TEXT[],
    "metadata" JSONB,
    FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS steps (
    "id" UUID PRIMARY KEY,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "threadId" UUID NOT NULL,
    "parentId" UUID,
    "streaming" BOOLEAN NOT NULL,
    "waitForAnswer" BOOLEAN,
    "isError" BOOLEAN,
    "metadata" JSONB,
    "tags" TEXT[],
    "input" TEXT,
    "output" TEXT,
    "createdAt" TEXT,
    "command" TEXT,
    "start" TEXT,
    "end" TEXT,
    "generation" JSONB,
    "showInput" TEXT,
    "language" TEXT,
    "indent" INT,
    "defaultOpen" BOOLEAN,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS elements (
    "id" UUID PRIMARY KEY,
    "threadId" UUID,
    "type" TEXT,
    "url" TEXT,
    "chainlitKey" TEXT,
    "name" TEXT NOT NULL,
    "display" TEXT,
    "objectKey" TEXT,
    "size" TEXT,
    "page" INT,
    "language" TEXT,
    "forId" UUID,
    "mime" TEXT,
    "props" JSONB,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedbacks (
    "id" UUID PRIMARY KEY,
    "forId" UUID NOT NULL,
    "threadId" UUID NOT NULL,
    "value" INT NOT NULL,
    "comment" TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);
```

### What Chainlit Does Automatically Once Data Layer Is Registered

1. Every new conversation creates a `threads` row
2. Every user message/assistant step creates `steps` rows
3. The **sidebar** shows previous threads automatically (Chainlit UI handles this)
4. Users can click "New Chat" → creates a fresh thread
5. Users can click previous threads in sidebar → Chainlit calls `@cl.on_chat_resume`

### The Missing Piece: `@cl.on_chat_resume`

When a user **resumes** an existing thread, Chainlit calls `@cl.on_chat_resume(thread)` instead of `@cl.on_chat_start`. We must add this handler to restore `history` from the thread's steps so Claude has conversation context.

**Without this handler, resumed conversations will have empty history.**

---

## Tasks / Subtasks

### Task 1: Create DB schema SQL init script and update docker-compose (AC: #3)

- [x] Create `db/` directory at project root
- [x] Create `db/init.sql` with the DDL for all 5 tables (users, threads, steps, elements, feedbacks) — use the **exact schema from the SQLAlchemy data layer docs** shown above
- [x] Update `docker-compose.yml` to mount `db/init.sql` as PostgreSQL init script:
  ```yaml
  volumes:
    - pgdata:/var/lib/postgresql/data
    - ./db:/docker-entrypoint-initdb.d
  ```
- [x] **IMPORTANT:** PostgreSQL only runs init scripts on a **fresh volume**. If `pgdata` already exists, you must `docker compose down -v` first.
- [x] Commit: `feat(db): add chainlit sqlalchemy datalayer schema`

### Task 2: Add SQLAlchemy dependency and register data layer (AC: #1, #3)

- [x] Add `SQLAlchemy` and `greenlet` to `pyproject.toml` dependencies (asyncpg is already present)
- [x] Run `uv lock` to update lock file
- [x] Create `app/data.py` (new file) with the data layer registration:
  ```python
  """Chainlit SQLAlchemy data layer configuration."""

  import chainlit as cl
  from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

  from app.config import settings


  @cl.data_layer
  def get_data_layer():
      """Register SQLAlchemy data layer for conversation persistence."""
      conninfo = settings.database_url
      # SQLAlchemy requires +asyncpg in the protocol for async support
      if conninfo and "postgresql://" in conninfo and "+asyncpg" not in conninfo:
          conninfo = conninfo.replace("postgresql://", "postgresql+asyncpg://")
      return SQLAlchemyDataLayer(conninfo=conninfo)
  ```
- [x] Import `app.data` in `app/main.py` so the `@cl.data_layer` decorator is registered at startup:
  ```python
  import app.data  # noqa: F401  # registers Chainlit data layer
  ```
- [x] **DO NOT** modify `app/config.py` — `database_url` is already defined there
- [x] Commit: `feat(data): register chainlit sqlalchemy data layer`

### Task 3: Add `@cl.on_chat_resume` handler to `app/chat.py` (AC: #2, #1)

- [x] Add `@cl.on_chat_resume` handler that reconstructs `history` from the thread's steps:
  ```python
  @cl.on_chat_resume
  async def on_chat_resume(thread: dict) -> None:
      """Restore conversation history when a user resumes a previous thread."""
      history: list[dict[str, Any]] = []
      steps = thread.get("steps", [])
      for step in steps:
          step_type = step.get("type", "")
          output = step.get("output", "")
          if not output:
              continue
          if step_type == "user_message":
              history.append({"role": "user", "content": output})
          elif step_type == "assistant_message":
              history.append({"role": "assistant", "content": output})
      # Trim to the configured history limit
      max_msgs = settings.conversation_history_limit
      history = history[-max_msgs:]
      cl.user_session.set("history", history)
  ```
- [x] After restoring history, re-connect the MCP session (same pattern as `on_chat_start`):
  - Set MCP session keys to None initially
  - Create `AsyncExitStack`, connect via `streamablehttp_client`
  - Initialize `ClientSession`, list tools, convert to Anthropic format
  - Store in `cl.user_session`
  - Wrap in try/except — if MCP reconnect fails, log warning and continue without tools
- [x] **DO NOT modify** `on_chat_start`, `on_message`, or `_agentic_loop`
- [x] Commit: `feat(chat): add on_chat_resume handler for conversation restoration`

### Task 4: Write tests (AC: #1, #2)

- [x] Add `TestConversationResume` class in `tests/app/test_chat.py`:
  - Test 1: `on_chat_resume` restores user/assistant history from thread steps
  - Test 2: `on_chat_resume` filters out steps with no output (tool steps, empty steps)
  - Test 3: `on_chat_resume` trims history to `CONVERSATION_HISTORY_LIMIT`
  - Test 4: `on_chat_resume` with empty steps results in empty history
  - Test 5: `on_chat_resume` reconnects MCP session (or handles failure gracefully)
- [x] Add `TestDataLayerRegistration` class in `tests/app/test_data.py` (new file):
  - Test 1: `get_data_layer()` returns a `SQLAlchemyDataLayer` instance
  - Test 2: conninfo has `+asyncpg` protocol added when plain `postgresql://` is provided
- [x] All 131 existing tests still pass (no regressions — 141 total with new tests)
- [x] Commit: `test(2-6): conversation persistence and resume tests`

### Task 5: Update docs (AC: #3)

- [x] Update `.env.example` — ensure `DATABASE_URL` line has a comment explaining it activates persistence
- [x] Add `docs/persistence.md` setup guide:
  - Step 1: `docker compose down -v && docker compose up -d` (fresh DB with schema)
  - Step 2: Set `DATABASE_URL` in `.env`
  - Step 3: Restart app — persistence activates automatically
  - Note the `+asyncpg` protocol conversion is handled automatically
- [x] Commit: `docs(2-6): add conversation persistence setup guide`

---

## Dev Notes

### Files to Modify

| File | Change |
|------|--------|
| `db/init.sql` | **NEW** — SQLAlchemy datalayer schema DDL |
| `docker-compose.yml` | Mount `db/` as init script volume |
| `app/data.py` | **NEW** — `@cl.data_layer` registration with SQLAlchemyDataLayer |
| `app/main.py` | Add `import app.data` to register the data layer |
| `app/chat.py` | Add `@cl.on_chat_resume` handler only |
| `tests/app/test_chat.py` | Add `TestConversationResume` class |
| `tests/app/test_data.py` | **NEW** — data layer registration tests |
| `docs/persistence.md` | **NEW** — setup guide |
| `pyproject.toml` | Add `SQLAlchemy` and `greenlet` dependencies |

**DO NOT modify:** `app/config.py`, `app/prompts.py`, `mcp_server/`, any existing test code.

### Key Difference: SQLAlchemy vs Native Data Layer

| Aspect | Native (`ChainlitDataLayer`) | SQLAlchemy (what we use) |
|--------|------------------------------|--------------------------|
| Activation | Auto via `DATABASE_URL` env var | Explicit `@cl.data_layer` decorator |
| Schema | Prisma-managed, PascalCase tables | Manual DDL, lowercase tables |
| Dependencies | asyncpg only | SQLAlchemy + asyncpg + greenlet |
| conninfo | `postgresql://...` | `postgresql+asyncpg://...` |
| Storage | Built-in | Optional `BaseStorageClient` (not needed for POC) |

### The `+asyncpg` Protocol Gotcha

SQLAlchemy requires `postgresql+asyncpg://` in the connection string for async support. Our `.env` has `postgresql://...` (standard format). The `app/data.py` module handles this conversion automatically — the dev should NOT ask users to change their `.env`.

### Anti-Patterns

- **DON'T** use the native `ChainlitDataLayer` — we're using SQLAlchemy community layer
- **DON'T** modify `app/config.py` — `database_url` is already defined
- **DON'T** add a storage client (Azure/S3) — not needed for POC
- **DON'T** manually create thread/step/user records — Chainlit manages these
- **DON'T** forget `docker compose down -v` when changing schema — init scripts only run on fresh volumes
- **DON'T** use `Optional[X]` — use `X | None` per project-context.md
- **DON'T** add `pgvector` — deferred per PRD

### Testing Standards

- Mock `SQLAlchemyDataLayer` — no real DB in unit tests
- Mock `streamablehttp_client` for MCP reconnect tests
- Use `patch("app.chat.cl.user_session")` for session mocking
- Use the `reload_chat` fixture for async handler tests
- Run `uv run ruff check . && uv run ruff format .` before committing
- All tests deterministic

### Prior Story Learnings (from 2-4, 2-5)

- Ruff enforces double quotes and line-length 120
- Pre-commit hook runs ruff automatically
- Branch naming: `story/2-6-conversation-persistence-and-history`
- Commit format: `feat(story-key): description`
- `reload_chat` fixture required for async handler tests
- Existing helpers: `_make_fake_cl_message()`, `FakeStream`, `_make_session_mock_with_history()`

---

## References

- [Source: epics.md#Story 2.6] — FR27, FR28, FR29, acceptance criteria
- [Source: architecture.md] — Boundary 4: Web App ↔ PostgreSQL
- [Source: project-context.md] — anti-patterns, code style, NFR6
- [Source: https://docs.chainlit.io/data-layers/sqlalchemy] — SQLAlchemy data layer setup and schema
- [Source: app/chat.py] — `on_chat_start` pattern to follow in `on_chat_resume`
- [Source: app/config.py] — `database_url` already defined in Settings
- [Source: docker-compose.yml] — existing PostgreSQL service
- [Source: 2-5-multi-turn-conversation-support.md] — dev patterns, test fixtures

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 (anthropic/claude-sonnet-4-6)

### Completion Notes

- **Task 1:** Created `db/init.sql` with the 5-table SQLAlchemy data layer schema (users, threads, steps, elements, feedbacks). Updated `docker-compose.yml` to mount `db/` as PostgreSQL init scripts volume.
- **Task 2:** Added `SQLAlchemy>=2.0.0` and `greenlet>=3.0.0` to `pyproject.toml`. Created `app/data.py` with `@cl.data_layer` decorator registering `SQLAlchemyDataLayer`. Added `import app.data` to `app/main.py` for startup registration. The `+asyncpg` protocol conversion is handled automatically.
- **Task 3:** Added `@cl.on_chat_resume` handler to `app/chat.py`. It restores user/assistant history from thread steps, filters empty outputs, trims to `conversation_history_limit`, and reconnects MCP session. Gracefully handles MCP reconnect failure.
- **Task 4:** Added `TestConversationResume` (6 tests) to `tests/app/test_chat.py` and created new `tests/app/test_data.py` with `TestDataLayerRegistration` (4 tests). All 141 tests pass (131 existing + 10 new).
- **Task 5:** Updated `.env.example` with improved `DATABASE_URL` comment. Created `docs/persistence.md` with full setup guide.
- Code review: clean — no issues found before PR.

### File List

- `db/init.sql` — NEW: SQLAlchemy data layer DDL schema (5 tables)
- `docker-compose.yml` — Updated: mount `db/` as init script volume
- `app/data.py` — NEW: `@cl.data_layer` registration with SQLAlchemyDataLayer
- `app/main.py` — Updated: `import app.data` to register data layer at startup
- `app/chat.py` — Updated: Added `@cl.on_chat_resume` handler
- `tests/app/test_chat.py` — Updated: Added `TestConversationResume` class
- `tests/app/test_data.py` — NEW: `TestDataLayerRegistration` class
- `docs/persistence.md` — NEW: Conversation persistence setup guide
- `pyproject.toml` — Updated: Added `SQLAlchemy>=2.0.0` and `greenlet>=3.0.0`
- `uv.lock` — Updated: Added sqlalchemy 2.0.48 and greenlet 3.3.2
- `.env.example` — Updated: Improved `DATABASE_URL` comment
