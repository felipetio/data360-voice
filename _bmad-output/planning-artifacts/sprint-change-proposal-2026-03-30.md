# Sprint Change Proposal: Add RAG with Document Upload to MVP

**Date:** 2026-03-30
**Triggered by:** Strategic decision to move document upload + RAG from Phase 3 to MVP
**Change Scope:** Moderate
**Status:** Approved

---

## 1. Issue Summary

Users (especially Brazilian journalists and policy analysts) need to combine country-level World Bank quantitative data with sub-national/qualitative data from local sources (CEMADEM, CPTEC, NDCs). The original plan deferred this to Phase 3 assuming API access to these sources. Since no API exists for CEMADEM/CPTEC, document upload + RAG is the only viable path.

This change moves document upload and RAG search from Post-MVP Phase 3 into the MVP scope, enabling cross-referencing of Data360 API data with uploaded document context via vector similarity search (pgvector).

**Evidence:**
- CEMADEM/CPTEC have no public APIs for programmatic access
- Brazilian journalists (Ana persona) are primary users needing sub-national context
- Prototype deadline is May 31, 2026; the tool's differentiation for the Data 360 Global Challenge is stronger with cross-referencing capability
- pgvector already chosen in architecture (PostgreSQL), Chainlit already supports file upload

---

## 2. Impact Analysis

### Epic Impact

| Epic | Impact Level | Details |
|------|-------------|---------|
| Epic 1 (done) | None | MCP server complete, unaffected |
| Epic 2 (in-progress) | Minor | Story 2-6 (PR #19 open) PostgreSQL setup continues as-is; docker image swap happens in Epic 8 |
| **Epic 8 (NEW)** | **New epic** | Document Upload & RAG Search (6 stories) |
| Epic 3 (backlog) | Moderate | System prompt and citation formatting must cover both API and document sources |
| Epic 4 (backlog) | Minor | Fact-check verdicts can optionally cross-reference uploaded documents (additive) |
| Epic 5-7 (backlog) | None | Independent features, unaffected |

### Epic Order Change

```
BEFORE: Epic 1 (done) → Epic 2 → Epic 3 → Epic 4 → Epic 5 → Epic 6 → Epic 7
AFTER:  Epic 1 (done) → Epic 2 → Epic 8 (new) → Epic 3 → Epic 4 → Epic 5 → Epic 6 → Epic 7
```

Rationale: Epic 3 (system prompt, citations) should be designed with full knowledge of all data sources (API + documents), avoiding rework.

### Artifact Conflicts

| Artifact | Changes Needed |
|----------|---------------|
| **PRD** | New FRs (FR49-FR56), move RAG from Phase 3 to MVP, new risk entries, new env vars |
| **Architecture** | New `mcp_server/rag/` module, 2 new MCP tools in tool table, docker image swap, updated data flow |
| **Epics** | New Epic 8 (6 stories), updated FR Coverage Map |
| **Sprint Status** | New Epic 8 entries, epic ordering note |
| **project-context.md** | RAG module rules and anti-patterns |
| **docker-compose.yml** | `postgres:16-alpine` → `pgvector/pgvector:pg16` (after PR #19 merges) |
| **System prompt** | DOCUMENT SEARCH section (covered in Story 8.5) |

### Technical Impact

- **New dependencies:** pymupdf4llm, sentence-transformers, pgvector (Python)
- **Docker image:** pgvector/pgvector:pg16 (superset of postgres, no breaking change)
- **Database schema:** 2 new tables (documents, document_chunks with vector column)
- **Model size:** sentence-transformers/all-MiniLM-L6-v2 (~90MB, loaded once at startup)
- **Feature flag:** `DATA360_RAG_ENABLED` (default: false) isolates all RAG functionality

---

## 3. Recommended Approach

**Path: Direct Adjustment** with feature flag safety valve.

All existing work remains valid. RAG is purely additive, isolated behind `DATA360_RAG_ENABLED=false` by default. No rollback needed. No completed stories invalidated.

| Factor | Assessment |
|--------|-----------|
| Effort | Medium (~1 week for 6 stories) |
| Risk | Medium (embedding quality, model startup time) |
| Timeline impact | Adds ~1 week before Epic 3 |
| Descope safety | Feature flag allows RAG to be disabled at any point without touching existing code |

**Risks and mitigations:**
- Embedding quality on climate text → all-MiniLM-L6-v2 is well-tested general-purpose model
- Model startup time (~90MB) → singleton caching, loaded once
- Storage growth → file size limits, chunk deduplication
- CI slowness (model download) → model caching in CI

---

## 4. Detailed Change Proposals

### 4.1 PRD Changes

**Edit 2: New Functional Requirements (FR49-FR56)**

Add after FR48:

```markdown
### Document Upload & RAG Search

- FR49: Users can upload PDF, TXT, MD, and CSV documents via the Chainlit chat interface
- FR50: The system can extract text from uploaded documents and split into chunks for vector search
- FR51: The system can generate embeddings for document chunks and store them in pgvector
- FR52: The MCP server can search uploaded documents via vector similarity (search_documents tool)
- FR53: The MCP server can list all uploaded documents with metadata (list_documents tool)
- FR54: The system can cross-reference Data360 API quantitative data with uploaded document context in a single response
- FR55: Document-sourced citations follow the CITATION_SOURCE pattern (e.g., "CEMADEM Report (uploaded 2026-03-30), p. 12")
- FR56: RAG functionality is gated behind DATA360_RAG_ENABLED env var (default: false)
```

**Edit 3: Move RAG from Phase 3 to MVP**

In Post-MVP Features > Phase 3, replace:
- `Sub-national data integration (CEMADEM, CPTEC for Brazil)`
- `Document upload / RAG (NDCs, national reports)`

With:
- `Sub-national API integration (CEMADEM, CPTEC direct API, if available) [Document upload path moved to MVP via Epic 8]`

**Edit 11: Risk Mitigation Update**

Add to Technical Risks:
- RAG embedding quality mitigated by all-MiniLM-L6-v2 and feature flag
- Model size (~90MB) mitigated by singleton caching at startup
- Storage growth mitigated by file size limits

**Edit 12: Environment Variables**

Add:

| Variable | Default | Purpose |
|---|---|---|
| `DATA360_RAG_ENABLED` | `false` | Enable document upload & RAG search |
| `DATA360_RAG_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `DATA360_RAG_CHUNK_SIZE` | `512` | Chunk size in tokens |
| `DATA360_RAG_CHUNK_OVERLAP` | `64` | Chunk overlap in tokens |
| `DATA360_RAG_MIN_SCORE` | `0.3` | Minimum similarity score (computed as `1 - cosine_distance`) |

### 4.2 Architecture Changes

**Edit 4: Project Structure** - Add `mcp_server/rag/` module (embeddings.py, chunker.py, store.py, processor.py) and `db/` directory with numbered SQL files.

**Edit 5: MCP Tool Table** - Add `search_documents` and `list_documents` tools (local pgvector, not Data360 API).

**Edit 6: Docker Image** - Swap `postgres:16-alpine` → `pgvector/pgvector:pg16`.

**Edit 7: Data Flow** - Add parallel path: `Uploaded Documents → RAG Pipeline → pgvector → MCP tools → Claude`. Citation integrity extended for document sources.

### 4.3 Epic Changes

**Edit 8: New Epic 8 - Document Upload & RAG Search (6 stories)**

| Story | Title | Key Deliverables |
|-------|-------|-----------------|
| 8.1 | pgvector Schema and Database Migration | pgvector image, 002_rag_schema.sql, migration runner |
| 8.2 | Document Processing Pipeline | chunker, embeddings, store, processor modules |
| 8.3 | search_documents and list_documents MCP Tools | 2 new MCP tools, feature-flagged |
| 8.4 | Chainlit Upload Integration | File upload handler, MIME restrictions, status feedback |
| 8.5 | System Prompt Update for Cross-Referencing | DOCUMENT SEARCH section in prompts.py |
| 8.6 | RAG Test Suite | Comprehensive tests for entire pipeline |

**Edit 9: FR Coverage Map** - Add FR49-FR56 → Epic 8 mappings.

### 4.4 Sprint Status Changes

**Edit 10:** Add Epic 8 entries (6 stories, all backlog). Note epic ordering: 2 → 8 → 3 → 4 → 5 → 6 → 7.

### 4.5 project-context.md Changes

**Edit 13:** Add RAG Module Rules and RAG Anti-Patterns sections.

---

## 5. Implementation Handoff

### Change Scope: Moderate

Requires backlog reorganization (new epic, reordered priorities) but no fundamental replan of architecture or PRD goals.

### Handoff Plan

| Role | Responsibility |
|------|---------------|
| **SM (this workflow)** | Update all artifacts per approved edits, update sprint-status.yaml |
| **Dev (Felipe)** | Merge PR #19 (Story 2-6), then implement Epic 8 stories sequentially |
| **PM** | No action needed (MVP scope expanded, not redefined) |
| **Architect** | No action needed (pgvector was already in architecture, RAG is additive) |

### Implementation Order

1. Merge PR #19 (Story 2-6) → Epic 2 complete
2. Story 8.1: pgvector schema (docker image swap + migration)
3. Story 8.2: Processing pipeline (chunker, embeddings, store)
4. Story 8.3: MCP tools (search_documents, list_documents)
5. Story 8.4: Chainlit upload integration
6. Story 8.5: System prompt update
7. Story 8.6: RAG test suite
8. Continue to Epic 3 (Trust, Citations & LLM Grounding)

### Success Criteria

- [ ] All 6 Epic 8 stories completed and tested
- [ ] RAG tools return results with CITATION_SOURCE for document sources
- [ ] Feature flag: `DATA360_RAG_ENABLED=false` leaves existing functionality unchanged
- [ ] Feature flag: `DATA360_RAG_ENABLED=true` enables document upload and search
- [ ] Cross-referencing works: user can ask about Brazilian drought and get both Data360 API data + uploaded CEMADEM report context in one response
- [ ] 141+ existing tests continue passing (zero regressions)

---

## Appendix: New Dependencies

| Package | Purpose | Size |
|---------|---------|------|
| pymupdf4llm | PDF text extraction with layout awareness | ~30MB |
| sentence-transformers | Local embedding generation | ~90MB (with model) |
| pgvector | PostgreSQL vector similarity extension (Python client) | <1MB |
