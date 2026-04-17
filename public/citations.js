/**
 * Citation marker styling - Story 9.1
 *
 * Wraps [n] text patterns in styled spans (superscript badges) for visual polish.
 * The reference block is rendered as markdown by the server and styled via CSS.
 */
(function () {
  "use strict";

  const MARKER_RE = /\[(\d+)\]/g;

  function styleMarkers(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (node.parentElement && node.parentElement.closest(".citation-marker")) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach((textNode) => {
      const text = textNode.nodeValue;
      MARKER_RE.lastIndex = 0;
      if (!MARKER_RE.test(text)) return;
      MARKER_RE.lastIndex = 0;

      const frag = document.createDocumentFragment();
      let lastIdx = 0;
      let match;
      while ((match = MARKER_RE.exec(text)) !== null) {
        if (lastIdx < match.index) {
          frag.appendChild(document.createTextNode(text.slice(lastIdx, match.index)));
        }
        const span = document.createElement("span");
        span.className = "citation-marker";
        span.textContent = match[0];
        frag.appendChild(span);
        lastIdx = match.index + match[0].length;
      }
      if (lastIdx < text.length) {
        frag.appendChild(document.createTextNode(text.slice(lastIdx)));
      }
      textNode.parentNode.replaceChild(frag, textNode);
    });
  }

  const observer = new MutationObserver(() => {
    document.querySelectorAll(".prose").forEach((el) => {
      if (!el.querySelector(".citation-marker")) {
        styleMarkers(el);
      }
    });
  });

  function init() {
    observer.observe(document.body, { childList: true, subtree: true });
    document.querySelectorAll(".prose").forEach((el) => styleMarkers(el));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
