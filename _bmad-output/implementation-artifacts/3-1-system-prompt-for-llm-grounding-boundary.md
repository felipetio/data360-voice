# Story 3.1: System Prompt for LLM Grounding Boundary

**Status:** done
**Epic:** 3 — Trust, Citations & LLM Grounding
**Story Key:** 3-1-system-prompt-for-llm-grounding-boundary
**Created:** 2026-04-02

---

## Story

As a product owner,
I want the LLM strictly constrained to narrate only data returned by the API and to place numbered citation markers in prose,
So that users can trust every claim is backed by official World Bank data and that the server-side citation pipeline (Story 3.2) can match markers to structured references.

---

## Acceptance Criteria

**AC1:** Given the system prompt in `app/prompts.py`, when Claude receives data from MCP tools, then it narrates only the data values, trends, and comparisons present in the tool results (FR18).

**AC2:** Given the system prompt, when Claude generates a response, then it never adds causal explanations not present in the API data (FR19), never generates predictions or forecasts (FR20), and never adds external knowledge or editorial judgment (FR21).

**AC3:** Given a user asks "Why did CO2 emissions increase in Brazil?", when Claude processes the question, then it responds that it can report what the World Bank indicators show but cannot explain causation beyond what the data contains (FR22).

**AC4:** Given a user pushes for opinions or predictions, when Claude processes the follow-up, then it maintains the grounding boundary and redirects to what the data shows.

**AC5:** Given the system prompt citation instructions, when Claude formats a data-bearing response, then it uses IEEE-style numbered markers `[1]`, `[2]`, etc. in prose next to data claims.

**AC6:** Given the citation marker instructions, when Claude writes a response, then it does NOT generate the reference list itself (the server appends it via `app/citations.py` in Story 3.2).

**AC7:** Given multiple data claims in a response, when Claude assigns markers, then markers are assigned in order of first appearance, and the same source (database + indicator combination) reuses its original number.

**AC8:** Given `DATA360_RAG_ENABLED=true`, when the system prompt is generated, then the DOCUMENT SEARCH section remains appended (backward compatibility with Story 8.5) and its citation instructions are aligned with the new `[n]` marker format.

**AC9:** Given `DATA360_RAG_ENABLED=false`, when the system prompt is generated, then the DOCUMENT SEARCH section is NOT included (existing behaviour preserved).

**AC10:** Given a test file `tests/app/test_prompts.py`, when running `uv run pytest tests/app/test_prompts.py`, then all existing tests pass and new grounding/citation tests pass.

---

## Tasks / Subtasks

### Task 1: Update `_BASE_SYSTEM_PROMPT` in `app/prompts.py` — grounding reinforcement and citation markers (AC: #1-7)

- [x] Open `app/prompts.py`.
- [x] In the `_BASE_SYSTEM_PROMPT` constant, replace the existing `CITATION FORMAT` section with a new `CITATION MARKERS` section that instructs Claude to:
  - Place IEEE-style numbered markers `[1]`, `[2]`, etc. in prose immediately after each data claim.
  - Assign markers in order of first appearance.
  - Reuse the same marker number when the same source (database + indicator) is cited again.
  - **NOT** generate a reference list at the end — state explicitly: "A reference list will be appended automatically. Do not generate one yourself."
- [x] Strengthen the STRICT CONSTRAINTS section:
  - Add explicit constraint: "When asked 'why' something happened, state that you can only report what the indicators show, not explain causation."
  - Add explicit constraint: "Do not provide opinions, editorial commentary, or subjective assessments."
- [x] Keep all other sections unchanged: NARRATIVE RESPONSE GUIDELINES, MULTI-TURN CONTEXT RESOLUTION, STYLE, etc.
- [x] Ensure `SYSTEM_PROMPT` backward-compatible alias still points to `_BASE_SYSTEM_PROMPT`.

### Task 2: Update `DOCUMENT_SEARCH_SECTION` citation format to align with `[n]` markers (AC: #8)

- [x] In `app/prompts.py`, update the `DOCUMENT CITATION FORMAT` subsection within `DOCUMENT_SEARCH_SECTION` to reference numbered markers:
  - Change from inline citation format to: "Use `[n]` markers for document-sourced claims just like API-sourced claims. The server assigns marker numbers."
  - Keep the filename/page/chunk format descriptions (these inform `CITATION_SOURCE` field content, not the marker format).
- [x] Update the `CROSS-REFERENCING WORKFLOW` to mention that both API and document citations use the same `[n]` marker system.
- [x] Ensure `get_system_prompt(rag_enabled=True)` still correctly appends the updated section.

### Task 3: Update existing tests and add new tests in `tests/app/test_prompts.py` (AC: #10)

- [x] Update `test_rag_enabled_includes_citation_format_for_documents` if the assertion text changed.
- [x] Add new test cases:
  - `test_base_prompt_contains_citation_marker_instructions` — asserts `[1]` or `[n]` marker instruction present.
  - `test_base_prompt_no_reference_list_generation` — asserts "Do not generate" reference list instruction present.
  - `test_base_prompt_grounding_boundary_causation` — asserts causation constraint present.
  - `test_base_prompt_grounding_boundary_no_opinions` — asserts no-opinions constraint present.
  - `test_marker_reuse_instruction` — asserts same-source-reuse instruction present.
- [x] Run: `uv run pytest tests/app/test_prompts.py -v` — all pass (17/17).

### Task 4: Update existing test assertions in `tests/app/test_chat.py` if needed (AC: #10)

- [x] Check `tests/app/test_chat.py` for any assertions that compare system prompt text verbatim.
- [x] If any tests assert specific citation format text (e.g., `"(Source: ..."` pattern), update to match the new `[n]` marker instructions.
  - Updated `test_system_prompt_instructs_citation_source` → `test_system_prompt_instructs_citation_markers`
- [x] Run: `uv run pytest tests/app/ -v` — all pass.

### Task 5: Full validation (AC: all)

- [x] Run: `uv run pytest -v` — no regressions across the full suite (285/285 passed).
- [x] Run: `uv run ruff check . && uv run ruff format .` — clean.
- [x] Update `sprint-status.yaml`: `ready-for-dev` → `review`.
- [x] Commit all changes.

---

## Dev Notes

### What This Story Changes (and What It Doesn't)

**This story modifies the system prompt only.** It does NOT:
- Build the citation registry pipeline (that's Story 3.2 — `app/citations.py`).
- Append reference lists to responses (that's Story 3.2).
- Change any MCP tool behaviour.
- Change any database schema.
- Modify `app/chat.py` beyond any test fixture updates.

The system prompt changes prepare Claude to emit `[n]` markers that Story 3.2's pipeline will later match to structured references. Until 3.2 is implemented, markers will appear in responses but no reference list will be appended — this is expected and acceptable during development.

### Exact Changes to `_BASE_SYSTEM_PROMPT`

**Replace the existing CITATION FORMAT section:**
```python
# CURRENT (to be replaced):
"CITATION FORMAT:\n"
"- Every narrative paragraph that references a specific figure must end with a source note.\n"
"- Always cite the CITATION_SOURCE field value and the year(s) of data used.\n"
'- Example: "(Source: World Development Indicators, 2022)"\n\n'

# NEW (replacement):
"CITATION MARKERS:\n"
"- Place a numbered marker [1], [2], etc. in prose immediately after each data claim.\n"
"- Assign marker numbers in order of first appearance in your response.\n"
"- Reuse the same marker number when citing the same source "
"(same database + indicator combination) again.\n"
"- Example: 'Brazil emitted 467,000 kt of CO2 in 2022 [1], while India emitted 2,693,000 kt [2].'\n"
"- A reference list will be appended automatically by the system. "
"Do not generate a reference list yourself.\n"
"- Do not use inline citation formats like '(Source: ...)'.\n\n"
```

**Add to STRICT CONSTRAINTS (append as items 6 and 7):**
```python
"6. When asked 'why' something happened, state that you can only report "
"what the indicators show, not explain causation.\n"
"7. Do not provide opinions, editorial commentary, or subjective assessments.\n\n"
```

### Changes to `DOCUMENT_SEARCH_SECTION`

**Update the DOCUMENT CITATION FORMAT subsection:**
```python
# CURRENT (relevant portion):
"DOCUMENT CITATION FORMAT:\n"
"- PDF chunks: `{filename} (uploaded {date}), p. {page}` "
"— use the CITATION_SOURCE field returned by search_documents.\n"
"- TXT/MD chunks: `{filename} (uploaded {date}), chunk {chunk_index}`\n"
"- CSV chunks: `{filename} (uploaded {date}), rows {start}-{end}`\n"
"Always use the CITATION_SOURCE value from the tool response; do not construct citations manually.\n\n"

# NEW (replacement):
"DOCUMENT CITATION FORMAT:\n"
"- Use the same [n] numbered marker system for document-sourced claims.\n"
"- The server assigns marker numbers — do not track document vs API markers separately.\n"
"- The CITATION_SOURCE field in search_documents results provides the source text "
"(e.g., '{filename} (uploaded {date}), p. {page}' for PDFs).\n"
"- Do not construct citations manually — the system builds the reference list from tool responses.\n\n"
```

### Existing `app/prompts.py` Structure (as of 8-5)

```python
_BASE_SYSTEM_PROMPT = (...)   # Main prompt with constraints, narrative guidelines, citation format
DOCUMENT_SEARCH_SECTION = (...) # RAG-specific instructions
SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT  # Backward-compatible alias

def get_system_prompt(rag_enabled: bool = False) -> str:
    if rag_enabled:
        return _BASE_SYSTEM_PROMPT + "\n\n" + DOCUMENT_SEARCH_SECTION
    return _BASE_SYSTEM_PROMPT
```

This structure remains the same. Only the content of `_BASE_SYSTEM_PROMPT` and `DOCUMENT_SEARCH_SECTION` changes.

### Test Updates

**Existing tests that may need assertion updates:**

1. `test_rag_enabled_includes_citation_format_for_documents` — currently asserts `"CITATION_SOURCE" in result` and `"uploaded" in result`. These should still pass since the new text retains both strings.

2. `tests/app/test_chat.py::test_system_prompt_included_in_every_call` — from 8-5 debug notes, this already uses `get_system_prompt(rag_enabled=False)` dynamically. Should pass without changes.

**New tests to add:**

```python
class TestGroundingBoundary:
    def test_base_prompt_contains_citation_marker_instructions(self):
        """Citation marker [n] instructions present in base prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "[1]" in result
        assert "[2]" in result
        assert "marker" in result.lower()

    def test_base_prompt_no_reference_list_generation(self):
        """LLM is told NOT to generate reference list."""
        result = get_system_prompt(rag_enabled=False)
        assert "Do not generate a reference list" in result

    def test_base_prompt_grounding_boundary_causation(self):
        """Causation constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "causation" in result.lower()

    def test_base_prompt_grounding_boundary_no_opinions(self):
        """No-opinions constraint is explicit."""
        result = get_system_prompt(rag_enabled=False)
        assert "opinions" in result.lower()

    def test_marker_reuse_instruction(self):
        """Instruction to reuse marker for same source is present."""
        result = get_system_prompt(rag_enabled=False)
        assert "same" in result.lower() and "reuse" in result.lower()

    def test_no_inline_citation_format(self):
        """Old inline (Source: ...) format is NOT in the prompt."""
        result = get_system_prompt(rag_enabled=False)
        assert "(Source:" not in result
```

### Project Structure Notes

**Files to modify:**
- `app/prompts.py` — update `_BASE_SYSTEM_PROMPT` (citation section + constraints) and `DOCUMENT_SEARCH_SECTION` (citation format alignment)
- `tests/app/test_prompts.py` — add grounding/citation marker tests, update any broken assertions

**Files NOT to touch:**
- `app/chat.py` — no changes needed; already uses `get_system_prompt(rag_enabled=settings.rag_enabled)`
- `app/config.py` — no new settings needed
- `mcp_server/` — no changes
- `app/citations.py` — does not exist yet (created in Story 3.2)
- `db/` — no schema changes

### Architecture Compliance

Per architecture doc:
> | FR Category | Primary Location | Key Files |
> |------------|-----------------|-----------|
> | LLM Grounding & Trust (FR18-22) | `app/` | `chat.py` (system prompt constraints) |
> | Citation & Source Attribution (FR8-12) | `mcp_server/` + `app/` | `app/prompts.py` (LLM marker instructions) |

This story addresses FR18-22 (grounding) and prepares FR8-9 (citation markers for the pipeline in 3.2).

### Anti-Patterns

- **DON'T** create `app/citations.py` in this story — that's Story 3.2.
- **DON'T** modify `app/chat.py` to append reference lists — that's Story 3.2.
- **DON'T** change MCP tool response formats — tools already return `CITATION_SOURCE`.
- **DON'T** remove the `SYSTEM_PROMPT` backward-compatible alias.
- **DON'T** use `Optional[X]` — use `X | None`.
- **DON'T** add `# noqa` without explicit approval.
- **DON'T** put system prompt text in `app/chat.py` — it belongs in `app/prompts.py`.

### Previous Story Intelligence (from 8-5)

1. **`app/prompts.py` structure**: `_BASE_SYSTEM_PROMPT` + `DOCUMENT_SEARCH_SECTION` + `get_system_prompt()` + `SYSTEM_PROMPT` alias. Same structure, only content changes.
2. **`tests/app/test_chat.py` regression**: 8-5 fixed `test_system_prompt_included_in_every_call` to use dynamic `get_system_prompt()`. Should not regress.
3. **Ruff enforcement**: Run `uv run ruff check . && uv run ruff format .` before finalizing.
4. **Test pattern**: Tests call `get_system_prompt()` directly and assert on string content. No mocking needed for prompt tests.

### References

- [Source: `app/prompts.py`] — existing `_BASE_SYSTEM_PROMPT`, `DOCUMENT_SEARCH_SECTION`, `get_system_prompt()`
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.1`] — acceptance criteria, grounding boundary requirements (FR18-22)
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.2`] — citation registry pipeline design (defines `[n]` marker contract)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Citation Integrity Rules`] — CITATION_SOURCE field, pipeline-guaranteed citations
- [Source: `_bmad-output/project-context.md#Citation Pipeline Rules`] — `app/citations.py` contract, `app/prompts.py` responsibilities
- [Source: `_bmad-output/implementation-artifacts/8-5-system-prompt-update-for-cross-referencing.md`] — previous story intelligence, prompts.py structure

### Branch & Commit Conventions

- Branch: `story/3-1-system-prompt-for-llm-grounding-boundary`
- Commits: `feat(3-1): ...` / `test(3-1): ...` / `chore(3-1): ...`

### PR Conventions

- Reviewers: `--reviewer copilot,felipetio`
- PR description must list all ACs with checkboxes

---

## Dev Agent Record

### Agent Model Used

anthropic/claude-opus-4-6

### Debug Log References

- Fixed `test_no_inline_citation_format`: initial assertion `"(Source:" not in result` was too broad — the new prompt mentions `(Source: ...)` as an example of what NOT to do. Changed assertion to check old instructional pattern `'Example: "(Source:'` is absent.
- Updated `test_system_prompt_instructs_citation_source` in `test_chat.py` → renamed to `test_system_prompt_instructs_citation_markers` since `CITATION_SOURCE` is no longer in base prompt.

### Completion Notes List

- AC1: Base prompt constrains Claude to tool-provided data only ✅
- AC2: Constraints 2-4 prevent causal claims, forecasts, external knowledge ✅
- AC3: Constraint 6 explicitly handles "why" questions → report indicators, not causation ✅
- AC4: Constraint 7 prevents opinions/editorial commentary ✅
- AC5: CITATION MARKERS section instructs [1], [2] IEEE-style markers ✅
- AC6: Explicit instruction "Do not generate a reference list yourself" ✅
- AC7: Instructions for marker order (first appearance) and same-source reuse ✅
- AC8: DOCUMENT_SEARCH_SECTION updated to use [n] marker system ✅
- AC9: get_system_prompt(rag_enabled=False) excludes document section ✅
- AC10: 17 prompt tests pass, 285 total tests pass, ruff clean ✅

### Change Log

- 2026-04-02: Story implemented. Status → review.

### File List

- `app/prompts.py` (modified — updated _BASE_SYSTEM_PROMPT and DOCUMENT_SEARCH_SECTION)
- `tests/app/test_prompts.py` (modified — updated assertion, added 7 new tests in TestGroundingBoundary)
- `tests/app/test_chat.py` (modified — renamed test_system_prompt_instructs_citation_source → test_system_prompt_instructs_citation_markers)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/3-1-system-prompt-for-llm-grounding-boundary.md` (modified)
