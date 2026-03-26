---
project_name: 'data360-voice'
user_name: 'Felipe'
date: '2026-03-26'
sections_completed:
  ['technology_stack', 'language_rules', 'framework_rules', 'citation_integrity', 'tool_response_contract', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 32
optimized_for_llm: true
---

# Project Context for AI Agents

_Critical rules and patterns AI agents must follow when implementing code in this project. Focused on unobvious details that agents commonly miss._

---

## Technology Stack & Versions

- Python 3.12+
- FastMCP 3.1.1+ — MCP server framework (lifespan, tool registration, transport)
- httpx 0.28.1+ — async HTTP client (AsyncClient, timeout, retry)
- python-dotenv 1.2.2+ — env config via `.env` file
- pytest 9.0.2+ + pytest-asyncio 1.3.0+ — test runner (`asyncio_mode = "auto"`)
- ruff 0.15.7+ — linting (E/F/W/I) + formatting, line-length 120
- pre-commit 4.5.1+ — enforces ruff on commit

## Critical Implementation Rules

### Language-Specific Rules

- Target Python 3.12+; use `X | Y` union syntax — never `Optional[X]` or `Union[X, Y]`
- All I/O methods must be `async`; no blocking calls inside tool handlers
- Type hints required on all function signatures; use `dict[str, Any]` not `Dict`
- Double quotes enforced by ruff; line length 120

### Framework-Specific Rules

- All tools registered via `@mcp.tool()` on the module-level `mcp = FastMCP(...)` instance
- `_client: Data360Client | None` is a **module-level singleton** — never instantiate per-request
  - Required so `_db_name_cache` persists across tool calls for `CITATION_SOURCE` enrichment
- `Data360Client` lifecycle managed by `_lifespan` async context manager — always `await _client.close()` on teardown
- Transport controlled by `MCP_TRANSPORT` env var (`stdio` | `streamable-http`); tools are transport-agnostic
- API param mapping: use `Data360Client._map_params()` for snake_case → UPPERCASE conversion
  - **camelCase exceptions — pass these directly, NOT through `_map_params()`:**
    `timePeriodFrom`, `timePeriodTo`, `datasetId`, `indicatorId`
- Pagination: `_paginated_get()` auto-pages at PAGE_SIZE=1000, caps at MAX_RECORDS=5000

### Citation Integrity Rules

- `DATA_SOURCE` field from API response must **never** be modified or removed
- Always call `await _client.enrich_citation_source(result["data"])` after any `get_data` response
- `CITATION_SOURCE` enrichment logic: `DATA_SOURCE` (if present) → `_db_name_cache[DATABASE_ID]` → `DATABASE_ID` string
- Call `_client.cache_db_names(results)` after `search_indicators` to populate the name cache for future enrichment
- Downstream code (Epic 3+) must use `CITATION_SOURCE`, not `DATA_SOURCE`, for citation display

### Tool Response Contract

All tools MUST return one of exactly two shapes:

**Success:**
```python
{"success": True, "data": [...], "total_count": int, "returned_count": int, "truncated": bool}
```

**Error:**
```python
{"success": False, "error": str, "error_type": "api_error" | "timeout"}
# Only "api_error" and "timeout" are used. Values like "no_data" or "validation_error"
# appear in older planning artifacts but were never implemented — treat them as obsolete.
```

- Never return empty `data` list without explicit "no data found" logging
- `truncated=True` when `total_count > returned_count`

### Testing Rules

- Tests in `tests/mcp_server/` mirror source structure
- `asyncio_mode = "auto"` in pyproject.toml — `@pytest.mark.asyncio` is redundant but acceptable
- Group tests in classes: `class TestToolName:` with docstrings referencing AC numbers (e.g., `"""AC1: ..."""`)
- JSON fixtures in `tests/mcp_server/fixtures/` — load via `_load_fixture("name.json")`
- Mock the module-level singleton by patching `mcp_server.server._client`:
  ```python
  with patch("mcp_server.server._client", instance):
  ```
- Always preserve real `_map_params` on mocks so param mapping assertions work:
  ```python
  instance._map_params = Data360Client._map_params
  ```
- Tests in `test_data360_client.py` mock the httpx client — no real API calls are made

### Code Quality & Style Rules

- Run `uv run ruff check .` and `uv run ruff format .` before every commit (pre-commit enforces)
- Never add `# noqa` or `# fmt: off` without explicit approval
- Ruff excludes `.claude/` and `_bmad/` — do not add rules targeting those paths
- All config via env vars with defaults in `config.py` — no hardcoded URLs, timeouts, or limits in source code

### Development Workflow Rules

- Always run with `uv run` — never call `python` directly
- Branch naming: `story/{{story_key}}` for story work; `feat/`, `fix/`, `chore/` otherwise
- Commit format: `feat(story-key): description` for story branches
- Story branches → PR → GitHub Copilot review → `/bmad-code-review` → merge

### Critical Anti-Patterns (Never Do)

- **DON'T** recreate `Data360Client` per tool call — breaks `_db_name_cache` across calls
- **DON'T** pass `timePeriodFrom`/`timePeriodTo` through `_map_params()` — API rejects `TIMEPERIODFROM`
- **DON'T** mutate `DATA_SOURCE` — always add `CITATION_SOURCE` as a separate field
- **DON'T** return empty `data` silently — always surface "no data found" explicitly
- **DON'T** use `Optional[X]` or `Union[X, Y]` — use `X | None` and `X | Y`
- **DON'T** add `# noqa` without approval
- **DON'T** construct OData filters with unvalidated strings — use `re.fullmatch(r"[A-Za-z0-9_]+", ...)` to prevent injection

---

## Usage Guidelines

**For AI Agents:** Read this file before implementing any code. Follow all rules exactly. When in doubt, prefer the more restrictive option.

**For Humans:** Keep lean and focused. Update when tech stack or patterns change.

Last Updated: 2026-03-26
