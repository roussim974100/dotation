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
  const mojibakeMarkers = ["Ã", "Â", "ï¿½", "�"];
  if (!mojibakeMarkers.some((marker) => text.includes(marker))) {
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
    if (!mojibakeMarkers.some((marker) => repaired.includes(marker))) {
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

let workflowDialogResolver = null;

function ensureWorkflowDialog() {
  let overlay = document.getElementById("workflowDialog");
  if (overlay) {
    return overlay;
  }

  overlay = document.createElement("div");
  overlay.id = "workflowDialog";
  overlay.className = "workflow-dialog is-hidden";
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = `
    <div class="workflow-dialog__backdrop" data-workflow-close="backdrop"></div>
    <div class="workflow-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="workflowDialogTitle">
      <div class="workflow-dialog__header">
        <div class="workflow-dialog__spinner" id="workflowDialogSpinner" aria-hidden="true"></div>
        <div>
          <strong id="workflowDialogTitle">Traitement en cours</strong>
          <p id="workflowDialogText"></p>
        </div>
      </div>
      <ul id="workflowDialogSteps" class="workflow-dialog__list"></ul>
      <div id="workflowDialogActions" class="workflow-dialog__actions d-none">
        <button type="button" class="btn btn-outline-secondary d-none" id="workflowDialogSecondaryBtn"></button>
        <button type="button" class="btn btn-primary" id="workflowDialogConfirmBtn">OK</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector("#workflowDialogConfirmBtn")?.addEventListener("click", () => {
    const resolver = workflowDialogResolver;
    closeWorkflowDialog();
    if (resolver) {
      resolver("confirm");
    }
  });

  overlay.querySelector("#workflowDialogSecondaryBtn")?.addEventListener("click", () => {
    const resolver = workflowDialogResolver;
    closeWorkflowDialog();
    if (resolver) {
      resolver("secondary");
    }
  });

  overlay.querySelector("[data-workflow-close='backdrop']")?.addEventListener("click", () => {
    if (!workflowDialogResolver) {
      return;
    }
    const resolver = workflowDialogResolver;
    closeWorkflowDialog();
    resolver("secondary");
  });

  return overlay;
}

function getWorkflowStepStateLabel(status) {
  if (status === "active") {
    return "En cours";
  }
  if (status === "done") {
    return "TerminÃ©";
  }
  if (status === "error") {
    return "Erreur";
  }
  return "Ã€ traiter";
}

function renderWorkflowDialog(options = {}) {
  const overlay = ensureWorkflowDialog();
  const titleNode = overlay.querySelector("#workflowDialogTitle");
  const textNode = overlay.querySelector("#workflowDialogText");
  const spinnerNode = overlay.querySelector("#workflowDialogSpinner");
  const stepsNode = overlay.querySelector("#workflowDialogSteps");
  const actionsNode = overlay.querySelector("#workflowDialogActions");
  const confirmNode = overlay.querySelector("#workflowDialogConfirmBtn");
  const secondaryNode = overlay.querySelector("#workflowDialogSecondaryBtn");
  const steps = Array.isArray(options.steps) ? options.steps : [];

  workflowDialogResolver = typeof options.onResolve === "function" ? options.onResolve : workflowDialogResolver;

  titleNode.textContent = options.title || "Traitement en cours";
  textNode.textContent = options.text || "";
  spinnerNode.classList.toggle("d-none", Boolean(options.hideSpinner));
  stepsNode.innerHTML = steps.map((step) => `
    <li class="workflow-dialog__item is-${step.status || "pending"}">
      <span class="workflow-dialog__bullet" aria-hidden="true"></span>
      <div class="workflow-dialog__content">
        <span class="workflow-dialog__label">${repairMojibakeText(step.label || "")}</span>
        <span class="workflow-dialog__state">${getWorkflowStepStateLabel(step.status || "pending")}</span>
      </div>
    </li>
  `).join("");

  const showConfirm = Boolean(options.showConfirm);
  const showSecondary = Boolean(options.secondaryLabel);
  actionsNode.classList.toggle("d-none", !showConfirm && !showSecondary);
  confirmNode.classList.toggle("d-none", !showConfirm);
  confirmNode.textContent = options.confirmLabel || "OK";
  secondaryNode.classList.toggle("d-none", !showSecondary);
  secondaryNode.textContent = options.secondaryLabel || "";

  overlay.classList.remove("is-hidden");
  overlay.setAttribute("aria-hidden", "false");
}

function closeWorkflowDialog() {
  const overlay = document.getElementById("workflowDialog");
  if (!overlay) {
    return;
  }
  overlay.classList.add("is-hidden");
  overlay.setAttribute("aria-hidden", "true");
  workflowDialogResolver = null;
}

function showWorkflowDialog(options = {}) {
  workflowDialogResolver = null;
  renderWorkflowDialog(options);
}

function askWorkflowDialog(options = {}) {
  return new Promise((resolve) => {
    workflowDialogResolver = resolve;
    renderWorkflowDialog(options);
  });
}

function createConfettiPiece(index) {
  const piece = document.createElement("span");
  piece.className = "completion-celebration__piece";
  piece.style.left = `${Math.random() * 100}%`;
  piece.style.animationDelay = `${(index % 12) * 0.06}s`;
  piece.style.animationDuration = `${2 + Math.random() * 1.4}s`;
  piece.style.background = ["#0f5b8d", "#d9a441", "#64a7d9", "#1f8f59"][index % 4];
  piece.style.transform = `translateY(-12vh) rotate(${Math.random() * 180}deg)`;
  return piece;
}

function playConfettiCelebration() {
  return new Promise((resolve) => {
    const layer = document.createElement("div");
    layer.className = "completion-celebration completion-celebration--confetti";
    for (let index = 0; index < 42; index += 1) {
      layer.appendChild(createConfettiPiece(index));
    }
    document.body.appendChild(layer);
    window.setTimeout(() => {
      layer.remove();
      resolve();
    }, 2600);
  });
}

function playBoatDepartureCelebration() {
  return new Promise((resolve) => {
    const layer = document.createElement("div");
    layer.className = "completion-celebration completion-celebration--boat";
    layer.innerHTML = `
      <div class="boat-departure">
        <div class="boat-departure__waves"></div>
        <div class="boat-departure__boat">
          <span class="boat-departure__flag" aria-hidden="true"></span>
          <span class="boat-departure__cabin" aria-hidden="true"></span>
          <span class="boat-departure__hull" aria-hidden="true"></span>
        </div>
      </div>
    `;
    document.body.appendChild(layer);
    window.setTimeout(() => {
      layer.remove();
      resolve();
    }, 2800);
  });
}

function playCompletionCelebration(kind) {
  if (kind === "boat") {
    return playBoatDepartureCelebration();
  }
  return playConfettiCelebration();
}

window.repairMojibakeText = repairMojibakeText;
window.repairMojibakeInNode = repairMojibakeInNode;
window.showWorkflowDialog = showWorkflowDialog;
window.askWorkflowDialog = askWorkflowDialog;
window.closeWorkflowDialog = closeWorkflowDialog;
window.playCompletionCelebration = playCompletionCelebration;

document.addEventListener("DOMContentLoaded", () => {
  initBackToTop();
  initContextualHelpLinks();
  initMojibakeRepair();
});

