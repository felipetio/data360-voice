/**
 * Citation UI — Story 9.1
 *
 * Reads citation JSON embedded as a hidden <span class="citation-data" data-citations='...'>
 * injected by app/chat.py. Transforms inline [n] markers to interactive elements
 * and styles the reference block.
 *
 * AC1: [n] markers → hoverable/clickable spans with tooltips
 * AC2: No citations → no markers shown (nothing to transform)
 * AC3: Tooltip shows API or document-type details appropriately
 *
 * Chainlit 2.10 DOM notes:
 *   - Messages render inside <div class="prose lg:prose-xl">
 *   - Paragraphs are <div role="article" class="leading-7 ...">
 *   - Bold text uses <span class="font-bold">, NOT <strong>
 *   - Horizontal rules (---) render as <div data-orientation="horizontal" ...>
 *   - No step-{uuid} id on the prose container
 */

(function () {
  "use strict";

  // ------------------------------------------------------------------ //
  // Tooltip singleton                                                    //
  // ------------------------------------------------------------------ //
  let tooltipEl = null;
  let hideTimeout = null;

  function getTooltip() {
    if (tooltipEl) return tooltipEl;
    tooltipEl = document.createElement("div");
    tooltipEl.className = "citation-tooltip";
    tooltipEl.setAttribute("role", "tooltip");
    document.body.appendChild(tooltipEl);
    return tooltipEl;
  }

  function buildTooltipHTML(ref) {
    if (ref.type === "document") {
      const filename = ref.filename || ref.source || "Unknown";
      const date = ref.upload_date || "";
      const page =
        ref.page != null
          ? `p. ${ref.page}`
          : ref.chunk != null
            ? `chunk ${ref.chunk}`
            : "";
      return `
        <div class="citation-tooltip-title">${escHtml(filename)}</div>
        ${date ? `<div class="citation-tooltip-row"><strong>Uploaded:</strong> ${escHtml(date)}</div>` : ""}
        ${page ? `<div class="citation-tooltip-row"><strong>Location:</strong> ${escHtml(page)}</div>` : ""}
      `;
    } else {
      const source = ref.source || ref.database_id || "World Bank";
      const name = ref.indicator_name || "";
      const code = ref.indicator_code || "";
      const years = ref.years || "";
      return `
        <div class="citation-tooltip-title">${escHtml(source)}</div>
        ${name ? `<div class="citation-tooltip-row"><strong>Indicator:</strong> ${escHtml(name)}</div>` : ""}
        ${code ? `<div class="citation-tooltip-row"><strong>Code:</strong> ${escHtml(code)}</div>` : ""}
        ${years ? `<div class="citation-tooltip-row"><strong>Years:</strong> ${escHtml(years)}</div>` : ""}
      `;
    }
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showTooltip(marker, ref) {
    clearTimeout(hideTimeout);
    const tt = getTooltip();
    tt.innerHTML = buildTooltipHTML(ref);

    const rect = marker.getBoundingClientRect();
    const ttW = 280;
    const ttH = 100;
    let left = rect.left + window.scrollX;
    let top = rect.bottom + window.scrollY + 6;

    if (left + ttW > window.innerWidth - 8) {
      left = window.innerWidth - ttW - 8;
    }
    if (top + ttH > window.scrollY + window.innerHeight) {
      top = rect.top + window.scrollY - ttH - 6;
    }

    tt.style.left = left + "px";
    tt.style.top = top + "px";
    tt.classList.add("visible");
  }

  function hideTooltip() {
    hideTimeout = setTimeout(() => {
      const tt = getTooltip();
      tt.classList.remove("visible");
    }, 120);
  }

  // ------------------------------------------------------------------ //
  // Core transform                                                        //
  // ------------------------------------------------------------------ //

  /**
   * Parse citation JSON from the hidden sentinel span inside a container.
   * Returns null if not found.
   */
  function extractRefs(container) {
    const sentinel = container.querySelector(".citation-data[data-citations]");
    if (!sentinel) return null;
    try {
      return JSON.parse(sentinel.getAttribute("data-citations"));
    } catch (e) {
      return null;
    }
  }

  /**
   * Transform [n] text nodes into interactive citation markers.
   * Skips content inside the reference block and sentinel.
   */
  function transformMarkers(container, refsMap) {
    const refBlock = container.querySelector(".citation-ref-block");
    const citData = container.querySelector(".citation-data");

    const walker = document.createTreeWalker(
      container,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          if (refBlock && refBlock.contains(node)) return NodeFilter.FILTER_REJECT;
          if (citData && citData.contains(node)) return NodeFilter.FILTER_REJECT;
          // Skip hidden LLM ref tail elements
          if (
            node.parentElement &&
            node.parentElement.closest(".citation-hidden-llm-tail")
          ) {
            return NodeFilter.FILTER_REJECT;
          }
          if (
            node.parentElement &&
            node.parentElement.closest(".citation-marker")
          ) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      }
    );

    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    const MARKER_RE = /\[(\d+)\]/g;

    textNodes.forEach((textNode) => {
      const text = textNode.nodeValue;
      if (!MARKER_RE.test(text)) return;
      MARKER_RE.lastIndex = 0;

      const frag = document.createDocumentFragment();
      let lastIndex = 0;
      let match;

      while ((match = MARKER_RE.exec(text)) !== null) {
        const refId = parseInt(match[1], 10);
        const ref = refsMap[refId];

        if (lastIndex < match.index) {
          frag.appendChild(
            document.createTextNode(text.slice(lastIndex, match.index))
          );
        }

        if (ref) {
          const span = document.createElement("span");
          span.className = "citation-marker";
          span.setAttribute("data-ref-id", String(refId));
          span.setAttribute("aria-label", `Citation ${refId}`);
          span.textContent = match[0];

          span.addEventListener("mouseenter", () => showTooltip(span, ref));
          span.addEventListener("mouseleave", hideTooltip);
          span.addEventListener("focus", () => showTooltip(span, ref));
          span.addEventListener("blur", hideTooltip);
          span.setAttribute("tabindex", "0");
          span.setAttribute("role", "button");

          frag.appendChild(span);
        } else {
          frag.appendChild(document.createTextNode(match[0]));
        }

        lastIndex = match.index + match[0].length;
      }

      if (lastIndex < text.length) {
        frag.appendChild(document.createTextNode(text.slice(lastIndex)));
      }

      textNode.parentNode.replaceChild(frag, textNode);
    });
  }

  /**
   * Wrap the rendered reference block in a styled div.
   *
   * Chainlit 2.10 renders markdown inside <div> elements (not <p>), and
   * bold text as <span class="font-bold"> (not <strong>).
   *
   * The reference section starts at one of:
   *   a) A <div data-orientation="horizontal"> (the --- separator the LLM may add)
   *   b) A <span class="font-bold">References</span> (the system-appended header)
   *
   * We use whichever appears first and wrap from there to the end.
   */
  const REF_TITLES = [
    "References",
    "Referências",
    "Referencias",
    "Références",
  ];

  /**
   * Hide the LLM-generated reference tail (--- + [n] lines) that appears
   * before the system-appended **References** block. The Python side strips
   * these from msg.content, but tokens were already streamed to the client.
   */
  function hideLlmRefTail(container) {
    // Find the --- separator
    const hr = container.querySelector('[data-orientation="horizontal"]');
    if (!hr) return;

    // Find the system-appended References header
    const titleCandidates = container.querySelectorAll(
      'strong, b, [class~="font-bold"], [class*="font-semibold"]'
    );
    let refTitleEl = null;
    for (const s of titleCandidates) {
      if (REF_TITLES.some((t) => s.textContent.trim() === t)) {
        refTitleEl = s;
        break;
      }
    }
    if (!refTitleEl) return;

    // The LLM tail is everything between the --- and the References header.
    // Hide these elements (don't remove — they might be streaming-incomplete).
    const refTitleParent = refTitleEl.closest("div, p");
    if (!refTitleParent) return;

    let cur = hr;
    while (cur && cur !== refTitleParent) {
      const next = cur.nextElementSibling;
      cur.style.display = "none";
      cur.classList.add("citation-hidden-llm-tail");
      cur = next;
    }
  }

  function wrapRefBlock(container) {
    if (container.querySelector(".citation-ref-block")) return;

    // First, hide any LLM-generated ref tail
    hideLlmRefTail(container);

    // Find the bold "References" header (system-appended)
    const titleCandidates = container.querySelectorAll(
      'strong, b, [class~="font-bold"], [class*="font-semibold"]'
    );
    let titleEl = null;
    for (const s of titleCandidates) {
      if (REF_TITLES.some((t) => s.textContent.trim() === t)) {
        titleEl = s;
        break;
      }
    }
    if (!titleEl) return;

    // Chainlit uses <div>, not <p> — match both for resilience
    const startEl = titleEl.closest("div, p");
    if (!startEl) return;

    // Collect startEl and all following siblings up to the container boundary
    const siblings = [];
    let cur = startEl;
    while (cur) {
      siblings.push(cur);
      cur = cur.nextElementSibling;
    }

    if (siblings.length === 0) return;

    const wrapper = document.createElement("div");
    wrapper.className = "citation-ref-block";
    startEl.parentNode.insertBefore(wrapper, startEl);
    siblings.forEach((s) => wrapper.appendChild(s));
  }

  // ------------------------------------------------------------------ //
  // Process a single message container                                    //
  // ------------------------------------------------------------------ //

  function processContainer(el) {
    // If interactive markers already exist in the DOM, we've already processed
    // this container and the transforms survived React's render cycle (i.e.,
    // streaming has ended). During streaming, React re-renders on every token
    // and wipes our DOM modifications — so the absence of markers means we
    // need to (re-)process.
    if (el.querySelector(".citation-marker")) return;

    const refs = extractRefs(el);
    if (!refs || refs.length === 0) return;

    const refsMap = {};
    refs.forEach((r) => {
      refsMap[r.id] = r;
    });

    wrapRefBlock(el);
    transformMarkers(el, refsMap);
  }

  // ------------------------------------------------------------------ //
  // Container discovery                                                   //
  // ------------------------------------------------------------------ //

  /**
   * Find message containers and process them.
   * Chainlit renders messages in:
   *   - <div id="step-{uuid}"> (some versions)
   *   - <div class="prose ..."> (2.10+)
   */
  function findAndProcessContainers(root) {
    if (!root || !root.querySelectorAll) return;

    // Collect candidate containers
    const candidates = new Set();

    // Step elements
    root.querySelectorAll('[id^="step-"]').forEach((el) => candidates.add(el));
    // Prose containers
    root.querySelectorAll(".prose").forEach((el) => candidates.add(el));

    // Check root itself
    if (root.id && root.id.startsWith("step-")) candidates.add(root);
    if (root.classList && root.classList.contains("prose")) candidates.add(root);

    candidates.forEach((el) => processContainer(el));
  }

  /**
   * Walk up from an element to find the nearest message container.
   * Used when a child element (like the sentinel) is added inside an
   * already-existing container that wasn't processed yet.
   */
  function findAncestorContainer(el) {
    let cur = el;
    while (cur) {
      if (cur.id && cur.id.startsWith("step-")) return cur;
      if (cur.classList && cur.classList.contains("prose")) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  // ------------------------------------------------------------------ //
  // MutationObserver                                                      //
  // ------------------------------------------------------------------ //

  // Debounce: batch rapid mutations (streaming tokens) into a single scan.
  // During streaming, React re-renders on every token and wipes our DOM changes.
  // A 1s debounce ensures we only process after tokens stop arriving (i.e.,
  // after the final msg.update() render). Each new mutation resets the timer.
  let scanTimer = null;
  const pendingContainers = new Set();

  function scheduleScan(container) {
    if (container) pendingContainers.add(container);
    // Reset timer on every call so we wait for a quiet period
    if (scanTimer) clearTimeout(scanTimer);
    scanTimer = setTimeout(() => {
      scanTimer = null;
      for (const c of pendingContainers) {
        processContainer(c);
      }
      pendingContainers.clear();
    }, 1000);
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "childList") {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType !== Node.ELEMENT_NODE) return;

          // Walk up to the message container and schedule a debounced scan.
          // During streaming, every token triggers a React re-render which
          // adds/removes child nodes. We schedule instead of processing
          // immediately so we only run once after tokens stop flowing.
          const ancestor = findAncestorContainer(node);
          if (ancestor) {
            scheduleScan(ancestor);
          }

          // Also check if the added node itself is a new container
          if (
            (node.id && node.id.startsWith("step-")) ||
            (node.classList && node.classList.contains("prose"))
          ) {
            scheduleScan(node);
          }
        });
      } else if (mutation.type === "characterData") {
        const ancestor = findAncestorContainer(mutation.target);
        if (ancestor) {
          scheduleScan(ancestor);
        }
      }
    }
  });

  function init() {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    // Process any already-rendered containers
    findAndProcessContainers(document.body);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
