function initBackToTop() {
  if (!document.body.classList.contains("app-shell")) {
    return;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "back-to-top";
  button.id = "backToTopBtn";
  button.textContent = "Haut";
  button.setAttribute("aria-label", "Revenir en haut de la page");
  document.body.appendChild(button);

  const toggleVisibility = () => {
    button.classList.toggle("is-visible", window.scrollY > 320);
  };

  button.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  const updateButtonPosition = () => {
    const baseOffset = window.innerWidth <= 767.98 ? 12 : 16;
    const actionBars = Array.from(document.querySelectorAll(".action-bar"));
    const extraOffset = actionBars.reduce((maxOffset, bar) => {
      const rect = bar.getBoundingClientRect();
      const overlap = Math.max(0, window.innerHeight - rect.top);
      return Math.max(maxOffset, overlap > 0 ? overlap + 12 : 0);
    }, 0);
    button.style.bottom = `${baseOffset + extraOffset}px`;
  };

  const handleViewportChange = () => {
    toggleVisibility();
    updateButtonPosition();
  };

  window.addEventListener("scroll", handleViewportChange, { passive: true });
  window.addEventListener("resize", updateButtonPosition);
  toggleVisibility();
  updateButtonPosition();
}

function initContextualHelpLinks() {
  const currentRelativeUrl = `${window.location.pathname.split("/").pop() || "index.html"}${window.location.search || ""}${window.location.hash || ""}`;

  document.querySelectorAll("a[data-help-page]").forEach((link) => {
    const page = link.dataset.helpPage;
    if (!page) {
      return;
    }

    const targetUrl = new URL(link.getAttribute("href") || "help.html", window.location.href);
    targetUrl.searchParams.set("page", page);
    targetUrl.searchParams.set("return", currentRelativeUrl);
    link.setAttribute("href", `${targetUrl.pathname}${targetUrl.search}`);
  });
}

function repairMojibakeText(value) {
  const text = String(value || "");
  if (!/(?:�.|�.|�.|?)/.test(text)) {
    return text;
  }

  const tryDecode = (input) => {
    try {
      const bytes = Uint8Array.from([...input].map((character) => character.charCodeAt(0) & 0xff));
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch (error) {
      return input;
    }
  };

  let repaired = text;
  for (let index = 0; index < 3; index += 1) {
    const candidate = tryDecode(repaired);
    if (candidate === repaired) {
      break;
    }
    repaired = candidate;
    if (!/(?:�.|�.|�.|?)/.test(repaired)) {
      break;
    }
  }
  return repaired;
}

function repairMojibakeInNode(root) {
  if (!root) {
    return;
  }

  if (root.nodeType === Node.TEXT_NODE) {
    const repaired = repairMojibakeText(root.textContent);
    if (repaired !== root.textContent) {
      root.textContent = repaired;
    }
    return;
  }

  if (root.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  ["placeholder", "title", "aria-label", "value"].forEach((attribute) => {
    if (root.hasAttribute(attribute)) {
      const repaired = repairMojibakeText(root.getAttribute(attribute));
      if (repaired !== root.getAttribute(attribute)) {
        root.setAttribute(attribute, repaired);
      }
    }
  });

  for (const child of root.childNodes) {
    repairMojibakeInNode(child);
  }
}

function initMojibakeRepair() {
  document.title = repairMojibakeText(document.title);
  repairMojibakeInNode(document.body);

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === "characterData") {
        repairMojibakeInNode(mutation.target);
      }
      mutation.addedNodes.forEach((node) => repairMojibakeInNode(node));
    });
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
  });
}

window.repairMojibakeText = repairMojibakeText;
window.repairMojibakeInNode = repairMojibakeInNode;

document.addEventListener("DOMContentLoaded", () => {
  initBackToTop();
  initContextualHelpLinks();
  initMojibakeRepair();
});
