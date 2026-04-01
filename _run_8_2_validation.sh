#!/bin/bash
# Story 8.2 validation and git setup script
set -e
cd /home/felipe/projects/data360-voice

echo "=== Current branch ==="
git branch --show-current

echo "=== Git status ==="
git status --short

echo "=== Checking/creating branch ==="
CURRENT=$(git branch --show-current)
if [ "$CURRENT" != "story/8-2-document-processing-pipeline" ]; then
    # Check if branch exists remotely or locally
    if git show-ref --verify --quiet refs/heads/story/8-2-document-processing-pipeline; then
        echo "Switching to existing local branch"
        git checkout story/8-2-document-processing-pipeline
    else
        echo "Creating new branch"
        git checkout -b story/8-2-document-processing-pipeline
    fi
fi

echo "=== On branch: $(git branch --show-current) ==="

echo ""
echo "=== Task 1: Verify dependencies ==="
grep -E "pymupdf4llm|sentence-transformers" pyproject.toml && echo "DEPS OK"

echo ""
echo "=== Task 2: Verify config ==="
grep -E "RAG_ENABLED|RAG_CHUNK" mcp_server/config.py && echo "CONFIG OK"

echo ""
echo "=== Task 3-6: Verify RAG module files ==="
ls -la mcp_server/rag/

echo ""
echo "=== Task 7: Verify test files ==="
ls -la tests/mcp_server/test_rag/
ls -la tests/mcp_server/fixtures/documents/

echo ""
echo "=== Running ruff lint ==="
uv run ruff check mcp_server/rag/ tests/mcp_server/test_rag/ 2>&1 | head -50

echo ""
echo "=== Running ruff format check ==="
uv run ruff format --check mcp_server/rag/ tests/mcp_server/test_rag/ 2>&1 | head -30

echo ""
echo "=== Running test_rag tests ==="
uv run pytest tests/mcp_server/test_rag/ -v --timeout=120 2>&1

echo ""
echo "=== Running full test suite ==="
uv run pytest -v --timeout=120 2>&1

echo "=== ALL DONE ==="
