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
      const page = ref.page != null ? `p. ${ref.page}` : ref.chunk != null ? `chunk ${ref.chunk}` : "";
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
    const ttH = 100; // approximate
    let left = rect.left + window.scrollX;
    let top = rect.bottom + window.scrollY + 6;

    // Clamp to viewport
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
   * Parse citation JSON from the hidden sentinel span inside a step element.
   * Returns null if not found.
   */
  function extractRefs(stepEl) {
    const sentinel = stepEl.querySelector(".citation-data[data-citations]");
    if (!sentinel) return null;
    try {
      return JSON.parse(sentinel.getAttribute("data-citations"));
    } catch (e) {
      return null;
    }
  }

  /**
   * Transform [n] text nodes into interactive citation markers.
   * Skips content inside the reference block itself.
   */
  function transformMarkers(container, refsMap) {
    // Walk text nodes in the prose area, skip the reference block
    const refBlock = container.querySelector(".citation-ref-block");
    const citData = container.querySelector(".citation-data");

    const walker = document.createTreeWalker(
      container,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          // Skip nodes inside the reference block or sentinel
          if (refBlock && refBlock.contains(node)) return NodeFilter.FILTER_REJECT;
          if (citData && citData.contains(node)) return NodeFilter.FILTER_REJECT;
          // Skip nodes inside existing citation markers
          if (node.parentElement && node.parentElement.closest(".citation-marker")) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      }
    );

    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    // Regex: matches [1], [12], etc.
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
          frag.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
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
          // Unknown reference id — keep as-is
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
   * Wrap the rendered reference block paragraphs in a styled div.
   *
   * The block is streamed as markdown and renders as:
   *   <p><strong>References</strong></p>
   *   <p>[1] ...</p>
   *
   * We detect the bold "References" / "Referências" / "Referencias" header
   * and wrap everything from there to end-of-message in citation-ref-block.
   */
  const REF_TITLES = ["References", "Referências", "Referencias", "Références"];

  function wrapRefBlock(container) {
    if (container.querySelector(".citation-ref-block")) return; // already done

    // Chainlit renders **bold** as <span class="font-bold"> (not <strong>).
    // We also accept <strong> for resilience against version changes.
    const titleCandidates = container.querySelectorAll(
      'strong, b, [class~="font-bold"], [class*="font-semibold"]'
    );
    let titleStrong = null;
    for (const s of titleCandidates) {
      if (REF_TITLES.some((t) => s.textContent.trim() === t)) {
        titleStrong = s;
        break;
      }
    }
    if (!titleStrong) return;

    // The <p> that wraps the <strong> is our starting point
    const titleP = titleStrong.closest("p");
    if (!titleP) return;

    // Collect titleP and all following siblings
    const siblings = [];
    let cur = titleP;
    while (cur) {
      // Stop at the hidden sentinel
      if (cur.classList && cur.classList.contains("citation-data")) {
        cur = cur.nextElementSibling;
        continue;
      }
      siblings.push(cur);
      cur = cur.nextElementSibling;
    }

    if (siblings.length === 0) return;

    const wrapper = document.createElement("div");
    wrapper.className = "citation-ref-block";

    titleP.parentNode.insertBefore(wrapper, titleP);
    siblings.forEach((s) => wrapper.appendChild(s));
  }

  // ------------------------------------------------------------------ //
  // Process a single step element                                        //
  // ------------------------------------------------------------------ //

  const processedSteps = new WeakSet();

  function processStep(stepEl) {
    if (processedSteps.has(stepEl)) return;

    const refs = extractRefs(stepEl);
    if (!refs || refs.length === 0) return;

    // Only mark processed once we have refs (streaming may not be done yet)
    processedSteps.add(stepEl);

    const refsMap = {};
    refs.forEach((r) => {
      refsMap[r.id] = r;
    });

    wrapRefBlock(stepEl);
    transformMarkers(stepEl, refsMap);
  }

  // ------------------------------------------------------------------ //
  // MutationObserver — watch for new/updated step elements              //
  // ------------------------------------------------------------------ //

  function findAndProcessSteps(root) {
    const candidates = [];

    if (root.querySelectorAll) {
      // Chainlit ≥2.x: step elements use id="step-{uuid}"
      const byId = root.querySelectorAll('[id^="step-"]');
      candidates.push(...byId);

      // Fallback: .prose containers (Chainlit renders message text inside .prose)
      // De-duplicate: only include .prose elements not already nested in a step-* element
      const prosetEls = root.querySelectorAll('.prose');
      for (const el of prosetEls) {
        if (!el.closest('[id^="step-"]')) {
          candidates.push(el);
        }
      }
    }

    // Also check if root itself is a step or prose container
    if (root.id && root.id.startsWith("step-")) {
      candidates.push(root);
    } else if (root.classList && root.classList.contains("prose")) {
      if (!root.closest('[id^="step-"]')) {
        candidates.push(root);
      }
    }

    // De-duplicate via Set (querySelectorAll + manual pushes may overlap)
    const seen = new Set();
    for (const step of candidates) {
      if (!seen.has(step)) {
        seen.add(step);
        processStep(step);
      }
    }
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "childList") {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            findAndProcessSteps(node);
          }
        });
      } else if (mutation.type === "characterData") {
        // Text was updated — re-check the parent step
        let parent = mutation.target.parentElement;
        while (parent) {
          if (parent.id && parent.id.startsWith("step-")) {
            processStep(parent);
            break;
          }
          parent = parent.parentElement;
        }
      }
    }
  });

  // Start observing once DOM is ready
  function init() {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    // Process any already-rendered steps
    findAndProcessSteps(document.body);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
