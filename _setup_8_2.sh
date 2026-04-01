#!/bin/bash
set -e
cd /home/felipe/projects/data360-voice

echo "=== Task 1: Add RAG dependencies ==="
uv add pymupdf4llm sentence-transformers

echo "=== uv sync ==="
uv sync

echo "=== Task 7: Run RAG tests ==="
uv run pytest tests/mcp_server/test_rag/ -v 2>&1

echo "=== Task 8: Full test suite ==="
uv run pytest -v 2>&1 | tail -30

echo "=== Lint check ==="
uv run ruff check . 2>&1
uv run ruff format . 2>&1

echo "=== Verify structure ==="
ls -la mcp_server/rag/
