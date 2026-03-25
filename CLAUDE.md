# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A conversational AI tool that enables querying World Bank climate and development data with verified citations. Built using FastMCP and httpx, it supports dual transport modes: stdio for Claude Desktop integration and HTTP for Chainlit web UI.

This project was developed using the BMAD methodology.


## Commands

```bash
# Run all tests
uv run python -m pytest

# Run a single test file
uv run python -m pytest tests/mcp_server/test_project_setup.py -v

# Run MCP server in dev mode
uv run fastmcp dev mcp_server/server.py

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Lint check
uv run ruff check .

# Format check
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check --fix .

# Auto-format
uv run ruff format .

# Install pre-commit hooks (first time setup)
uv run pre-commit install

# Run pre-commit on all files
uv run pre-commit run --all-files
```

## Code Quality Rules

This project enforces code quality via ruff (linter + formatter) and pre-commit hooks. All code must pass these checks before committing.

- **Always run `uv run ruff check .` and `uv run ruff format --check .` before considering work complete.**
- **Never disable or skip ruff rules** without explicit approval. Do not add `# noqa` comments or `# fmt: off` blocks.
- **Ruff is configured in `pyproject.toml`** with rules: E (pycodestyle errors), F (pyflakes), W (pycodestyle warnings), I (isort). Line length is 120 characters.
- **Pre-commit hooks run automatically on every commit** — ruff check (with auto-fix) and ruff format. If a commit fails due to formatting, the files are auto-fixed; re-stage and commit again.
- **Import ordering follows isort conventions** (stdlib, third-party, local) enforced by the `I` rule set.
- **Excluded directories**: `.claude` and `_bmad` are excluded from ruff checks (tooling scaffolding, not project code).

## Architecture

```
mcp_server/
  config.py          # ENV-based config with defaults (DATA360_* vars)
  data360_client.py  # Async httpx client: param mapping, pagination, retry
  server.py          # FastMCP server instance + tool definitions
```

**Data flow:** World Bank Data360 API -> Data360Client -> MCP tools -> Claude/Chainlit

**Key design decisions:**
- Citation integrity: `DATA_SOURCE` flows unmutated from API response to output (trust core)
- All config via environment variables with sensible defaults, no hardcoded values
- Auto-pagination (1000/page, 5000 cap per tool call)
- Retry with exponential backoff on transient failures
- "No data found" must be explicit, never silently empty

## BMAD Artifacts

Architecture decisions, PRD, epics, and research reports live in `_bmad-output/`. Reference these for the "why" behind design choices.
