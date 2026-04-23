# Epic 9 — Retrospective before redesign

**Status:** Epic 9 reverted on main. Pre-redesign retrospective to inform the next attempt.
**Date:** 2026-04-23
**PR with revert:** `revert/epic-9`
**Original attempts:** PR #42 (merged then reverted), PR #43 (abandoned)

## Goal of Epic 9 (original PRD)

> Citation UI & Journalist Export — make `[n]` markers interactive, render a
> styled reference block at the bottom of each assistant message, and enable
> copying / exporting narratives with their citations preserved.

Stories:
- **9.1** Citation Registry Rendering in Chat UI
- **9.2** Copy with Citations
- **9.3** Source Verification Links

Only 9.1 was attempted. It is what we are rethinking.

## What was shipped in PR #42 (now reverted)

**Minimal approach** — CSS-styled badge + streamed markdown ref list.

### Files

- `public/citations.js` (69 lines) — `MutationObserver` wrapping every `[n]` text
  pattern in a `<span class="citation-marker">` for badge styling
- `public/citations.css` (17 lines) — pill-shaped superscript for the span
- `app/chat.py` (+4 lines) — stream the ref block markdown at end of turn
- `app/prompts.py` (+9 lines) — instruct the LLM on marker reuse
- `.chainlit/config.toml` — enable `custom_css` / `custom_js`
- `tests/app/test_citation_ui.py` — asserts the markdown format only

### Why it "worked" enough to merge

- Tests asserted the citation pipeline builds a registry deterministically
- The manual test queries used simple single-indicator prompts where the LLM
  emitted one marker `[1]` matching one registry entry
- No multi-tool-call scenario was exercised in CI

## What broke in production testing

Every failure mode uncovered in a single session of real use:

### 1. Dangling markers (`[2]`, `[3]` in text, only `[1]` in registry)
**Root cause:** LLM emits sequential markers per tool call, but
`deduplicate_references` collapses same-indicator tool calls into one registry
entry. Markers reference an id that doesn't exist.

**Why the prompt doesn't prevent it:** LLM can't know in advance that its two
tool calls for the same indicator will collapse.

**Attempted mitigation (PR #43 commit `3842319`):** `strip_dangling_markers`
server-side — removes any `[n]` where `n > len(refs)`. Deterministic safety
net. Still deployed correctly, but only hides the symptom.

### 2. Silent records dropped in `extract_references`
**Root cause:** A record without `CITATION_SOURCE` is silently skipped at
`app/citations.py:134`. If an entire tool response lacks the field, its refs
never make it to the registry — but the LLM cites them anyway, producing
orphan markers.

**Attempted mitigation (PR #43 commits `b32fd4f`, `38fb9e4`):** WARNING log
at each early-return path in `extract_references` for observability.

### 3. Blind byte truncation corrupted tool outputs
**Root cause:** `_extract_tool_result_text` in `app/chat.py` capped tool result
to 50 000 chars with `text[:50000] + "[... truncated ...]"`. This cuts
**mid-JSON** — the response becomes unparseable, `json.loads` fails,
`extract_references` silently skips the whole tool output.

Any `search_indicators` response reliably exceeds 50 KB. Multi-country /
multi-year `get_data` calls also exceed it. Result: most tool outputs produced
zero refs.

**Attempted mitigation (PR #43 commit `dea355d`):** removed the truncation
entirely. Server-side pagination (1000/page, 5000 cap per call) already
bounds the size. This was the real root cause of most "references didn't
appear" reports.

### 4. Model regressions: Haiku emitted XML-style fake tool calls
**Root cause:** `claude-haiku-4-5` occasionally emitted
`<function_calls><invoke name=...>...</invoke></function_calls>` as plain text
tokens instead of using the native `tool_use` API. No tools were executed.
The model then fabricated numerical data and emitted `[n]` markers for it.

**Attempted mitigation (PR #43 commit `6075303`):** switched default to
`claude-sonnet-4-5`. Reduces but does not eliminate the failure.

### 5. Sonnet still occasionally skips tools entirely
Even with Sonnet 4.5, some runs resulted in `stop_reason=end_turn` on round 1
with zero tool calls and fabricated data. Cause unclear — possibly
conversation state carryover, prompt ambiguity, or model variance.

### 6. LLM wrote its own reference section despite the prompt
Output contained both `**Referências:**\n[1] ...` (LLM's version) and
`**References**\n[1] ...` (system-generated), producing visible duplicates.

**Attempted mitigation (PR #43 commit `7b68c72`):** `strip_llm_ref_tail`
server-side — strips common header patterns across 5 languages + `---[n]`
fallback. Also added `detect_narrative_language` heuristic and reworked
`format_reference_list` output format.

### 7. Ugly ref block format (`[1] (TOTAL_GHG), Source (years).`)
Starts with dangling `(CODE),` when `indicator_name` is missing — awkward.

**Attempted mitigation (PR #43 commit `7b68c72`):** reformat to
`[n] Source (CODE, years).` or `[n] "Name" — Source (CODE, years).` when
name is present.

### 8. Race condition between `on_chat_start` and `on_mcp_connect`
**Root cause:** Chainlit fires both callbacks on a fresh chat. `on_mcp_connect`
may fire first and set a valid MCP session (7 tools). `on_chat_start` then
blindly resets `user_session[_MCP_SESSION]` to `None` at the top, tries its
own connect against `streamablehttp_client(url="http://localhost:8001")` —
but the URL is missing the `/mcp` path, returns 404, fails, logs warning,
and leaves `tools=0`. `on_message` sees no tools → model has none to call →
fabricates response → orphan markers.

This is intermittent — order-dependent. Sometimes the session survives,
sometimes not.

**Attempted mitigation (unfinished, stashed in `fix/dangling-citation-markers`):**
skip `on_chat_start` auto-connect if `_MCP_SESSION_KEY` already set. Same
guard in `on_chat_resume`. Required test-mock updates.

### 9. Anthropic API overload (HTTP 529) with no retry
**Root cause:** Mid-stream, Anthropic returns `overloaded_error`. We raise
straight to the user as "Sorry, I couldn't reach the AI service."

**Attempted mitigation (unfinished, stashed):** retry with exponential
backoff (2 s, 4 s) up to 3 attempts; clear streamed content between attempts.

### 10. `tool_result_max_chars` in `_extract_tool_result_text` was the ONE underlying cause that produced the most user-visible damage
Points 1, 2, 3 were all observable because truncation killed most tool
outputs silently. Once that was fixed (`dea355d`), the rate of "no refs"
drops sharply — but the system was still fragile enough that subsequent
issues (4, 5, 6, 8, 9) kept one bug at a time visible.

## Assessment

**The scope of Story 9.1 as written ("render [n] interactively + show ref
block") did not reveal the stack of upstream bugs beneath it.** Every fix
in PR #43 was reactive, addressing the next issue surfaced by a test. The
fundamental pipeline (Anthropic ↔ MCP ↔ citation extraction ↔ rendering)
has too many silent-failure points:

- `extract_references` silently drops malformed records
- `_extract_tool_result_text` silently mangled JSON
- `on_chat_start` silently swallowed MCP connect failures
- The LLM silently violated the prompt (writing its own ref list, emitting
  fake XML tool calls)

Each silent failure made the symptom ("no references") look identical, so
each bug took a full round-trip to diagnose.

## Key lessons for the redesign

### Architecture

1. **Frame the story as "citation pipeline reliability," not "UI feature."**
   The UI is the final 5% once the pipeline is trustworthy. Start server-side.

2. **Fail loud, not silent.** Every skip/drop path in `extract_references`
   and `_extract_tool_result_text` must log at WARNING or surface a
   diagnostic marker. The "missing CITATION_SOURCE silent skip" pattern has
   to go; drops should be explicit system errors visible in the response.

3. **The tool-output transport is the weak link.** Byte truncation, multi-
   block concatenation, JSON validity — all issues happen before the pipeline
   even sees the data. Treat tool outputs as a bounded, validated contract:
   either produce a valid JSON blob under size budget, or produce an explicit
   error blob. No silent mangling.

4. **LLM cannot be trusted to follow prompt for marker rules or suppressing
   its own ref list.** Design the pipeline so that both are enforced
   server-side with deterministic code. Prompt should match enforcement but
   not rely on it.

5. **Stop placing fragile UI behavior in Chainlit.** Custom JS + CSS fighting
   MutationObserver + React re-renders was already the mess seen on the
   abandoned `story/9-1-citation-registry-rendering-in-chat-ui` branch
   (c420109, 788d434, 9b34574 — three successive workarounds for React
   wiping DOM). If we need interactive markers, let the server emit the
   final HTML and let Chainlit render it as-is.

### Process

6. **The story's test plan missed the multi-tool-call scenario** (same
   indicator across multiple countries). That's the primary real-world
   query — it should be the first test, not the last.

7. **Manual smoke tests should exercise the full length of a query that
   exercises `search_indicators` + multiple `get_data` + RAG + multi-
   indicator.** Single-indicator queries are not representative.

8. **Epic 9 depends on Epic 3 (citation registry) being robust.** Before
   9.1 can be attempted again, the citation-extraction pipeline needs the
   observability fixes (logging on every skip path) and the transport fix
   (no blind truncation) landed separately — not buried in a UI PR.

## Recommended next steps

Don't reopen Story 9.1 as written. Propose a split:

1. **9.0 (new) — Pipeline hardening.** Fix `_extract_tool_result_text`
   (no blind truncation), add WARNING logs on every silent-skip path in
   `extract_references`, add a prompt-agnostic `strip_llm_ref_tail` +
   `strip_dangling_markers` + renumbering contract. Server-only changes,
   deterministic tests, no UI work. This is the foundation.

2. **9.1 (reframed) — Server-rendered citation HTML.** Instead of a client-
   side `MutationObserver` fighting React, emit the final message content
   as HTML with `<span class="citation-marker">[n]</span>` already in the
   text. Chainlit renders it natively with `unsafe_allow_html`. Keep only
   the tooltip event handlers on the JS side (~50 lines, not 450).

3. **9.2 / 9.3** — unchanged but should follow reframed 9.1.

Also land separately:
- Model default → `claude-sonnet-4-5` (cost vs. reliability trade-off
  confirmed worth it).
- `on_chat_start` / `on_chat_resume` guards against clobbering
  `on_mcp_connect`'s work.
- Anthropic overload retry with exponential backoff.

Each of the above is a small, independently testable change. Putting them
in one Epic-9 PR is what turned this iteration into a 10-commit firefight.

## Reference: PRs involved

| PR | State | Content |
|---|---|---|
| #42 | merged → **reverted here** | Original 9.1 client-side approach |
| #43 | **to be closed** | 10 commits of reactive fixes; work is preserved in branch history for reference |
| *(this)* | open | Revert + this retrospective |

The abandoned branch `story/9-1-citation-registry-rendering-in-chat-ui`
contains three post-merge "fix" commits (c420109, 788d434, 9b34574) that
were never merged — client-side MutationObserver workarounds for React
streaming re-renders. Keep it as a cautionary archive, do not build on it.
