# Story 9.1: Citation Registry Rendering in Chat UI

Status: ready-for-dev

## Story

As a journalist,
I want citation markers in the chat response to be interactive and show source details,
So that I can quickly verify and understand the source of each data claim without scrolling.

## Acceptance Criteria

**AC1:** Given a chat response with `[n]` citation markers and a `references` metadata object attached to the Chainlit message,
When the response is rendered in the Chainlit UI,
Then each `[n]` marker is rendered as a clickable/hoverable element.
And hovering/clicking a marker shows a tooltip with: source name, indicator name, indicator code, year range, and database.
And the reference list block at the bottom of the response is styled distinctly from the narrative text (e.g., smaller font, border, or background).
And reference entries in the list are visually numbered to match the `[n]` markers.

**AC2:** Given a response with no citations (clarification, no data found),
When the response is rendered,
Then no reference block or interactive markers are shown.

**AC3:** Given the tooltip content,
When displayed to the user,
Then document-type citations show: filename, upload date, page/chunk.
And API-type citations show: database name, indicator code, indicator name, year range.

## Tasks / Subtasks

- [ ] Task 1: Create `public/` directory and CSS file for citation styling (AC: #1)
  - [ ] Create `public/citations.css` with styles for `.citation-marker` (clickable inline markers), `.citation-ref-block` (styled reference list container), and `.citation-tooltip` (hover tooltip)
  - [ ] Enable custom CSS in `.chainlit/config.toml` by uncommenting/setting `custom_css = "/public/citations.css"`
  - [ ] Style the reference block distinctly: smaller font (0.85em), muted color, left border or background, top margin separator

- [ ] Task 2: Create `public/citations.js` for interactive citation marker behavior (AC: #1, #2, #3)
  - [ ] On DOM mutations (MutationObserver), scan new message content for `[n]` patterns inside narrative text (not inside the references block)
  - [ ] Transform text `[n]` markers into `<span class="citation-marker" data-ref-id="n">[n]</span>` elements
  - [ ] On hover/click of a `.citation-marker`, look up the reference with matching `id` from the message's metadata and show a tooltip
  - [ ] Tooltip content for API type: database name, indicator name, indicator code, year range
  - [ ] Tooltip content for document type: filename, upload date, page/chunk
  - [ ] If no `references` metadata on the message, do nothing (AC2 — no markers shown since no `[n]` text will appear)
  - [ ] Enable custom JS in `.chainlit/config.toml`: `custom_js = "/public/citations.js"`

- [ ] Task 3: Expose `references` metadata to the frontend (AC: #1)
  - [ ] Verify that `msg.metadata = {"references": refs}` in `app/chat.py` (already set in AC7 of Story 3.2) propagates correctly to the Chainlit frontend as message metadata
  - [ ] Inspect Chainlit 2.10.0 message object in the browser to confirm `metadata.references` is accessible from the JS custom script
  - [ ] Document the exact JS path to access message metadata (e.g., via `window.__chainlit__` or DOM data attributes)

- [ ] Task 4: Style the markdown reference list block (AC: #1)
  - [ ] The reference list is already appended as markdown text by `app/citations.py` (format: `**References**\n[1] ...`)
  - [ ] Use CSS to target the rendered markdown of the reference block (e.g., by detecting the `**References**` header or adding a sentinel HTML comment/span)
  - [ ] Alternatively, inject a wrapper `<div class="citation-ref-block">` around the reference block via the JS MutationObserver

- [ ] Task 5: Write tests for the new UI behavior (AC: all)
  - [ ] Add `tests/app/test_citation_ui.py` with unit tests for any Python-side changes (if any)
  - [ ] If no Python changes are needed, document this in the Dev Agent Record
  - [ ] Manual verification checklist (to be done by dev): send a data query → verify markers are interactive → verify tooltip appears → verify reference block is styled → verify no markers/block on a clarification response

- [ ] Task 6: Full validation (AC: all)
  - [ ] Run: `uv run pytest -v` — no regressions
  - [ ] Run: `uv run ruff check . && uv run ruff format .` — clean
  - [ ] Update `sprint-status.yaml`: `9-1-citation-registry-rendering-in-chat-ui: backlog → ready-for-dev` (already done by create-story), then after dev: `→ review`
  - [ ] Commit all changes on branch `story/9-1-citation-registry-rendering-in-chat-ui`

## Dev Notes

### Architecture Context

This story is **pure frontend** — no Python backend changes are needed. The citation data already flows from Epic 3:

```
MCP tool call → app/citations.py → msg.metadata = {"references": refs}
```

The `references` list attached to the Chainlit message metadata is the contract from Story 3.2 (AC7). Story 9.1 consumes it in the UI.

### Reference Object Schema (from `app/citations.py`)

Each entry in `msg.metadata["references"]` has this shape:

**API type:**
```json
{
  "id": 1,
  "type": "api",
  "source": "World Development Indicators",
  "indicator_code": "EN.ATM.CO2E.KT",
  "indicator_name": "CO2 emissions, total (kt)",
  "database_id": "WB_WDI",
  "years": "2015-2022"
}
```

**Document type:**
```json
{
  "id": 2,
  "type": "document",
  "source": "report.pdf (uploaded 2026-04-01), p. 12",
  "filename": "report.pdf",
  "upload_date": "2026-04-01",
  "page": 12
}
```

### Chainlit 2.10.0 Custom JS/CSS Integration

Chainlit 2.10.0 supports `custom_css` and `custom_js` in `.chainlit/config.toml`. Files must live in `public/` at the project root. The config keys (currently commented out):

```toml
[UI]
custom_css = "/public/citations.css"
custom_js = "/public/citations.js"
```

**Key investigation needed:** How does the custom JS access message metadata?
- Option A: Chainlit exposes message data via a global (e.g., `window.__chainlit__`, `window.chainlit`)
- Option B: Message metadata is embedded as `data-*` attributes on DOM elements
- Option C: Subscribe to Chainlit's event bus/socket from the custom JS

Start by inspecting the rendered DOM in DevTools after a response with references is received. Look for any `data-metadata` or similar attribute on message elements. Check `window` globals for Chainlit-provided APIs.

**Fallback approach if metadata is not accessible from JS:** Modify `app/chat.py` to inject a hidden `<div data-citations='[...]'>` into the message text itself, which the JS can then parse from the DOM. This requires setting `unsafe_allow_html = true` in `.chainlit/config.toml` (note: security trade-off to evaluate).

### CSS Approach for Reference Block Styling

The reference block is rendered as markdown with `**References**` as the title. In Chainlit's rendered markdown, this becomes an HTML structure like:

```html
<p><strong>References</strong></p>
<p>[1] "CO2 emissions..." (EN.ATM.CO2E.KT), World Development Indicators (2015-2022).</p>
```

The MutationObserver JS can detect the `**References**` bold text and wrap the subsequent siblings in a `.citation-ref-block` div for CSS targeting.

### Existing Code — What NOT to Change

- `app/citations.py` — already complete from Story 3.2, no changes
- `app/chat.py` — `msg.metadata = {"references": refs}` already set (line ~445), no changes
- `app/prompts.py` — no changes
- `mcp_server/` — no changes
- `tests/app/test_citations.py` — no changes

### Previous Story Intelligence (from 3.2 and 3.3)

1. **`app/citations.py` structure:** `extract_references()` → `deduplicate_references()` → `format_reference_list()`. The `references` list uses `id`, `type`, `source`, `indicator_code`, `indicator_name`, `database_id`, `years` for API; `filename`, `upload_date`, `page` for documents.
2. **`msg.metadata` set in `_agentic_loop()`:** Around line 445 in `app/chat.py`. The key is `"references"` with value `list[dict]`.
3. **Chainlit streaming:** The reference block is streamed as text via `msg.stream_token(ref_block)`. The JS MutationObserver must handle dynamically added content.
4. **Ruff enforcement:** `uv run ruff check . && uv run ruff format .` before commit.
5. **Branch convention:** `story/9-1-citation-registry-rendering-in-chat-ui`
6. **No Python unit tests needed** if the story is pure frontend JS/CSS. Document this explicitly.

### Git Intelligence (Recent Commits)

- `0af731c` — Sprint planning, Epic 9 started
- `1b59fff` — Epics 8 & 3 retrospective
- `26b7a88` — Mark 3-3 done
- `df8516f` — Story 3-3: Data Freshness Transparency (PR #40)
- `b5e2ba7` — Mark 3-2 done

Branch pattern: `story/X-Y-description` → PR → `--reviewer copilot,felipetio`

### Project Structure Notes

**Files to create:**
- `public/citations.css` — citation marker and reference block styles
- `public/citations.js` — MutationObserver for interactive citation markers
- `tests/app/test_citation_ui.py` — placeholder/documentation (if no Python changes)

**Files to modify:**
- `.chainlit/config.toml` — uncomment `custom_css` and `custom_js` under `[UI]`

**Files NOT to touch:**
- `app/citations.py`, `app/chat.py`, `app/prompts.py`, `mcp_server/`

### Branch & Commit Conventions

- Branch: `story/9-1-citation-registry-rendering-in-chat-ui`
- Commits: `feat(9-1): ...` / `style(9-1): ...` / `chore(9-1): ...`
- PR reviewers: `--reviewer copilot,felipetio`

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 9.1`] — acceptance criteria
- [Source: `app/chat.py#L438-L445`] — citation metadata attachment in `_agentic_loop()`
- [Source: `app/citations.py`] — reference object schema (extract, deduplicate, format)
- [Source: `_bmad-output/implementation-artifacts/3-2-citation-registry-pipeline.md`] — upstream contract (AC7 of Story 3.2)
- [Source: `.chainlit/config.toml`] — custom_css and custom_js configuration
- [Source: `_bmad-output/project-context.md#Citation Pipeline Rules`] — architectural contract

## Dev Agent Record

### Agent Model Used

anthropic/claude-sonnet-4-6

### Debug Log References

- Chainlit 2.10.0 metadata is in React/Recoil state — not directly accessible from custom JS. Used DOM sentinel approach instead.
- `_CITATION_DATA_TPL` constant must be placed after imports (ruff E402 fix).
- Removed unused `pytest` import from test file (ruff F401 fix).

### Completion Notes List

- Implemented citation UI via DOM sentinel approach: `app/chat.py` injects hidden `<span data-citations='[...]'>` alongside the streamed reference block.
- `unsafe_allow_html = true` enabled in `.chainlit/config.toml` to render the sentinel.
- `citations.js`: MutationObserver wraps `[n]` text in clickable spans, builds tooltips from sentinel JSON, wraps reference block in styled div.
- `citations.css`: citation marker styling, tooltip, reference block with left border and muted background.
- 12 Python unit tests validate sentinel template, JSON roundtrip (API + document types), encoding edge cases, AC1/AC2 guard.
- 351 tests total, all pass. Ruff clean.

### File List

**Created:**
- `public/citations.css`
- `public/citations.js`
- `tests/app/test_citation_ui.py`

**Modified:**
- `app/chat.py` — added `_CITATION_DATA_TPL` constant and sentinel injection after ref block
- `.chainlit/config.toml` — enabled `unsafe_allow_html`, `custom_css`, `custom_js`
- `_bmad-output/implementation-artifacts/9-1-citation-registry-rendering-in-chat-ui.md` — story status → review
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `9-1` → review


# Story 9.1: Citation Registry Rendering in Chat UI

Story file created at: `_bmad-output/implementation-artifacts/9-1-citation-registry-rendering-in-chat-ui.md`
Sprint status updated: `9-1-citation-registry-rendering-in-chat-ui: ready-for-dev`
