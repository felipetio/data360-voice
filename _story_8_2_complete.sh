#!/bin/bash
# Story 8.2 — Complete setup, validation, commits, and PR
set -e
cd /home/felipe/projects/data360-voice

LOG=/tmp/story_8_2_output.txt
exec > >(tee "$LOG") 2>&1

echo "============================================"
echo " Story 8.2: Document Processing Pipeline"
echo "============================================"
echo ""

# ── Branch setup ───────────────────────────────
echo "=== [Branch] ==="
CURRENT=$(git branch --show-current)
echo "Current branch: $CURRENT"

if [ "$CURRENT" != "story/8-2-document-processing-pipeline" ]; then
    if git show-ref --verify --quiet refs/heads/story/8-2-document-processing-pipeline; then
        echo "Switching to existing local branch..."
        git checkout story/8-2-document-processing-pipeline
    else
        echo "Creating new branch..."
        git checkout -b story/8-2-document-processing-pipeline
    fi
fi
echo "On branch: $(git branch --show-current)"
echo ""

# ── Verify files exist ─────────────────────────
echo "=== [File Verification] ==="
for f in \
    pyproject.toml \
    mcp_server/config.py \
    mcp_server/rag/__init__.py \
    mcp_server/rag/chunker.py \
    mcp_server/rag/embeddings.py \
    mcp_server/rag/store.py \
    mcp_server/rag/processor.py \
    tests/mcp_server/test_rag/__init__.py \
    tests/mcp_server/test_rag/test_chunker.py \
    tests/mcp_server/test_rag/test_embeddings.py \
    tests/mcp_server/test_rag/test_processor.py \
    tests/mcp_server/fixtures/documents/sample.txt \
    tests/mcp_server/fixtures/documents/sample.md \
    tests/mcp_server/fixtures/documents/sample.csv; do
    if [ -f "$f" ]; then
        echo "  ✓ $f"
    else
        echo "  ✗ MISSING: $f"
        exit 1
    fi
done
echo ""

# ── Ruff lint + format ─────────────────────────
echo "=== [Ruff Lint] ==="
uv run ruff check mcp_server/rag/ tests/mcp_server/test_rag/ || {
    echo "Lint errors found — attempting auto-fix..."
    uv run ruff check --fix mcp_server/rag/ tests/mcp_server/test_rag/
}

echo ""
echo "=== [Ruff Format] ==="
uv run ruff format mcp_server/rag/ tests/mcp_server/test_rag/
echo "Format OK"
echo ""

# ── Run RAG tests ──────────────────────────────
echo "=== [RAG Tests] ==="
uv run pytest tests/mcp_server/test_rag/ -v --timeout=120
echo ""

# ── Run full test suite ────────────────────────
echo "=== [Full Test Suite] ==="
uv run pytest -v --timeout=120
echo ""

# ── Git commits ────────────────────────────────
echo "=== [Git Commits] ==="
git config user.email "amelia@data360-voice" 2>/dev/null || true
git config user.name "Amelia (Story 8.2)" 2>/dev/null || true

# Task 1: dependencies (already in pyproject.toml from uv add done earlier)
echo "--- Commit 1: dependencies ---"
git add pyproject.toml uv.lock
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add pymupdf4llm and sentence-transformers dependencies"

# Task 2: config
echo "--- Commit 2: config ---"
git add mcp_server/config.py .env.example 2>/dev/null || git add mcp_server/config.py
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add RAG chunk config to mcp_server/config.py"

# Task 3: chunker
echo "--- Commit 3: chunker ---"
git add mcp_server/rag/__init__.py mcp_server/rag/chunker.py
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add mcp_server/rag/chunker.py"

# Task 4: embeddings
echo "--- Commit 4: embeddings ---"
git add mcp_server/rag/embeddings.py
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add mcp_server/rag/embeddings.py"

# Task 5: store
echo "--- Commit 5: store ---"
git add mcp_server/rag/store.py
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add mcp_server/rag/store.py"

# Task 6: processor
echo "--- Commit 6: processor ---"
git add mcp_server/rag/processor.py
git diff --cached --quiet && echo "(already committed)" || git commit -m "feat(8-2): add mcp_server/rag/processor.py"

# Task 7: tests
echo "--- Commit 7: tests ---"
git add tests/mcp_server/test_rag/ tests/mcp_server/fixtures/documents/
git diff --cached --quiet && echo "(already committed)" || git commit -m "test(8-2): add RAG pipeline unit tests and fixture documents"

# Task 8: final validation commit
echo "--- Commit 8: final validation ---"
git add -A
git diff --cached --quiet && echo "(nothing to commit)" || git commit -m "chore(8-2): final validation — all tests pass, ruff clean"

echo ""
echo "=== [Git Log] ==="
git log --oneline -10
echo ""

# ── Push branch ────────────────────────────────
echo "=== [Push Branch] ==="
git push -u origin story/8-2-document-processing-pipeline
echo ""

# ── Create PR ─────────────────────────────────
echo "=== [Create PR] ==="
gh pr create \
    --title "feat(8-2): document processing pipeline" \
    --body "Implements Story 8.2 — RAG document processing pipeline (chunker, embeddings, store, processor) with full test suite.

## Changes
- \`mcp_server/rag/chunker.py\` — text extraction + chunking (PDF, TXT, MD, CSV)
- \`mcp_server/rag/embeddings.py\` — sentence-transformers/all-MiniLM-L6-v2 singleton
- \`mcp_server/rag/store.py\` — asyncpg pgvector insert + cosine similarity search
- \`mcp_server/rag/processor.py\` — full pipeline orchestrator
- Tests in \`tests/mcp_server/test_rag/\` with fixture documents
- \`mcp_server/config.py\` updated with RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP
- \`pymupdf4llm\` and \`sentence-transformers\` added as dependencies

## Story
Closes: Story 8.2 (data360-voice Epic 8 — Document Upload & RAG Search)" \
    --reviewer copilot,felipetio 2>&1 || \
gh pr create \
    --title "feat(8-2): document processing pipeline" \
    --body "Implements Story 8.2 — RAG document processing pipeline (chunker, embeddings, store, processor) with full test suite." \
    --reviewer felipetio 2>&1

echo ""
echo "============================================"
echo " Story 8.2 COMPLETE"
echo "============================================"
echo "Log saved to: $LOG"
