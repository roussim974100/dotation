// ── CSRF token global ─────────────────────────────────────────────────────
// Chargé une fois par page, partagé par tous les modules (storage.js, admin.js…)
let _csrfTokenCache = null;

async function getCsrfToken() {
  if (_csrfTokenCache) return _csrfTokenCache;
  try {
    const res = await fetch("/api/csrf-token", { credentials: "same-origin", cache: "no-store" });
    const data = await res.json();
    _csrfTokenCache = data.token || "";
  } catch (_) {
    _csrfTokenCache = "";
  }
  return _csrfTokenCache;
}

function invalidateCsrfToken() {
  _csrfTokenCache = null;
}
// ─────────────────────────────────────────────────────────────────────────

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
let signatureValidityDialogResolver = null;

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
    return "Terminé";
  }
  if (status === "error") {
    return "Erreur";
  }
  return "À traiter";
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

function ensureSignatureValidityDialog() {
  let overlay = document.getElementById("signatureValidityDialog");
  if (overlay) {
    return overlay;
  }

  overlay = document.createElement("div");
  overlay.id = "signatureValidityDialog";
  overlay.className = "workflow-dialog is-hidden";
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = `
    <div class="workflow-dialog__backdrop" data-signature-validity-close="backdrop"></div>
    <div class="workflow-dialog__panel signature-validity-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="signatureValidityDialogTitle">
      <div class="workflow-dialog__header">
        <div class="workflow-dialog__spinner d-none" aria-hidden="true"></div>
        <div>
          <strong id="signatureValidityDialogTitle">Validité du lien</strong>
          <p id="signatureValidityDialogText"></p>
        </div>
      </div>
      <div class="signature-validity-dialog__body">
        <label class="form-label" for="signatureValidityDaysInput">Durée de validité</label>
        <div class="signature-validity-dialog__row">
          <input class="form-control" id="signatureValidityDaysInput" type="number" min="1" max="30" step="1" value="7">
          <span class="signature-validity-dialog__suffix">jours</span>
        </div>
        <p class="signature-validity-dialog__hint">Choisissez une durée comprise entre 1 et 30 jours.</p>
        <p class="signature-validity-dialog__error d-none" id="signatureValidityDialogError"></p>
      </div>
      <div class="workflow-dialog__actions">
        <button type="button" class="btn btn-outline-secondary" id="signatureValidityDialogCancelBtn">Annuler</button>
        <button type="button" class="btn btn-primary" id="signatureValidityDialogConfirmBtn">Continuer</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const resolveAndClose = (value) => {
    const resolver = signatureValidityDialogResolver;
    closeSignatureValidityDialog();
    if (resolver) {
      resolver(value);
    }
  };

  overlay.querySelector("#signatureValidityDialogCancelBtn")?.addEventListener("click", () => {
    resolveAndClose(null);
  });

  overlay.querySelector("#signatureValidityDialogConfirmBtn")?.addEventListener("click", () => {
    const input = overlay.querySelector("#signatureValidityDaysInput");
    const errorNode = overlay.querySelector("#signatureValidityDialogError");
    const rawValue = Number.parseInt(input?.value || "7", 10);
    const sanitized = Number.isFinite(rawValue) ? rawValue : NaN;
    if (!Number.isFinite(sanitized) || sanitized < 1 || sanitized > 30) {
      errorNode.textContent = "Veuillez saisir une durée valide entre 1 et 30 jours.";
      errorNode.classList.remove("d-none");
      input?.focus();
      return;
    }
    errorNode.classList.add("d-none");
    resolveAndClose(sanitized);
  });

  overlay.querySelector("[data-signature-validity-close='backdrop']")?.addEventListener("click", () => {
    resolveAndClose(null);
  });

  overlay.querySelector("#signatureValidityDaysInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      overlay.querySelector("#signatureValidityDialogConfirmBtn")?.click();
    }
  });

  return overlay;
}

function closeSignatureValidityDialog() {
  const overlay = document.getElementById("signatureValidityDialog");
  if (!overlay) {
    return;
  }
  overlay.classList.add("is-hidden");
  overlay.setAttribute("aria-hidden", "true");
  signatureValidityDialogResolver = null;
}

function askSignatureValidityDialog(options = {}) {
  return new Promise((resolve) => {
    const overlay = ensureSignatureValidityDialog();
    signatureValidityDialogResolver = resolve;

    const titleNode = overlay.querySelector("#signatureValidityDialogTitle");
    const textNode = overlay.querySelector("#signatureValidityDialogText");
    const inputNode = overlay.querySelector("#signatureValidityDaysInput");
    const errorNode = overlay.querySelector("#signatureValidityDialogError");
    const confirmNode = overlay.querySelector("#signatureValidityDialogConfirmBtn");

    titleNode.textContent = options.title || "Validité du lien";
    textNode.textContent = options.text || "Définissez la durée de validité du lien de signature à distance.";
    inputNode.value = String(options.defaultValue || 7);
    inputNode.min = "1";
    inputNode.max = String(options.maxDays || 30);
    errorNode.textContent = "";
    errorNode.classList.add("d-none");
    confirmNode.textContent = options.confirmLabel || "Continuer";

    overlay.classList.remove("is-hidden");
    overlay.setAttribute("aria-hidden", "false");
    window.setTimeout(() => inputNode.focus(), 0);
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

// ───────────────────────────────────────────────────────
// Menu utilisateur : dark mode toggle, changement mdp
// ───────────────────────────────────────────────────────

const DARK_MODE_KEY = "userDarkModePreference";

function isDarkModeActive() {
  return document.documentElement.dataset.colorMode === "dark";
}

function updateDarkModeLabel() {
  const btn = document.getElementById("darkModeToggle");
  if (btn) {
    btn.textContent = isDarkModeActive() ? "\u2600 Mode clair" : "\u263E Mode sombre";
  }
}

function toggleDarkMode() {
  const next = isDarkModeActive() ? "light" : "dark";
  localStorage.setItem(DARK_MODE_KEY, next);
  if (typeof applyBrandingTheme === "function") {
    applyBrandingTheme(window.APP_BRANDING || {});
  }
  updateDarkModeLabel();
}

function initUserMenu() {
  const menu = document.getElementById("userMenu");
  if (!menu) {
    return;
  }

  // Fermer le menu au clic externe
  document.addEventListener("click", (e) => {
    if (menu.open && !menu.contains(e.target)) {
      menu.open = false;
    }
  });

  // Dark mode toggle
  const darkBtn = document.getElementById("darkModeToggle");
  if (darkBtn) {
    darkBtn.addEventListener("click", (e) => {
      e.preventDefault();
      toggleDarkMode();
    });
  }

  // Changement de mot de passe
  const pwdBtn = document.getElementById("changePasswordBtn");
  if (pwdBtn) {
    pwdBtn.addEventListener("click", (e) => {
      e.preventDefault();
      menu.open = false;
      openPasswordChangeModal();
    });
  }

  // Mettre à jour le label du toggle
  updateDarkModeLabel();

  // Observer data-color-mode pour garder le label synchronisé
  const observer = new MutationObserver(() => updateDarkModeLabel());
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-color-mode"] });

  // Injecter l'identité utilisateur
  populateUserMenuIdentity();
}

async function populateUserMenuIdentity() {
  try {
    const response = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const user = await response.json();
    const nameEl = document.getElementById("userMenuName");
    const roleEl = document.getElementById("userMenuRole");
    if (nameEl) {
      nameEl.textContent = user.username || "";
    }
    if (roleEl) {
      roleEl.textContent = user.is_admin ? "Administrateur" : (user.groups || []).join(", ") || "Utilisateur";
    }
  } catch (_) {
    // silently ignore
  }
}

// ─── Modale changement de mot de passe ─────────────

function openPasswordChangeModal() {
  if (document.getElementById("passwordChangeModal")) {
    return;
  }
  const backdrop = document.createElement("div");
  backdrop.id = "passwordChangeModal";
  backdrop.className = "password-change-modal__backdrop";
  backdrop.innerHTML = `
    <div class="password-change-modal__dialog">
      <h3>Changer le mot de passe</h3>
      <div style="display:grid;gap:0.85rem;">
        <div>
          <label class="form-label" for="pwdCurrent">Mot de passe actuel</label>
          <input class="form-control" type="password" id="pwdCurrent" autocomplete="current-password">
        </div>
        <div>
          <label class="form-label" for="pwdNew">Nouveau mot de passe</label>
          <input class="form-control" type="password" id="pwdNew" autocomplete="new-password">
        </div>
        <div>
          <label class="form-label" for="pwdConfirm">Confirmer le nouveau mot de passe</label>
          <input class="form-control" type="password" id="pwdConfirm" autocomplete="new-password">
        </div>
        <p style="margin:0;font-size:0.82rem;color:var(--muted);">12 caractères minimum, majuscule, minuscule, chiffre et caractère spécial.</p>
      </div>
      <div id="pwdFeedback"></div>
      <div class="password-change-modal__actions">
        <button class="btn btn-outline-secondary" type="button" id="pwdCancelBtn">Annuler</button>
        <button class="btn btn-primary" type="button" id="pwdSubmitBtn">Valider</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);

  // Fermer au clic sur backdrop
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) {
      closePasswordChangeModal();
    }
  });

  document.getElementById("pwdCancelBtn").addEventListener("click", closePasswordChangeModal);
  document.getElementById("pwdSubmitBtn").addEventListener("click", submitPasswordChange);

  // Fermer avec Escape
  backdrop._escHandler = (e) => {
    if (e.key === "Escape") {
      closePasswordChangeModal();
    }
  };
  document.addEventListener("keydown", backdrop._escHandler);

  document.getElementById("pwdCurrent").focus();
}

function closePasswordChangeModal() {
  const modal = document.getElementById("passwordChangeModal");
  if (modal) {
    if (modal._escHandler) {
      document.removeEventListener("keydown", modal._escHandler);
    }
    modal.remove();
  }
}

const PASSWORD_ERROR_MESSAGES = {
  missing_fields: "Veuillez remplir tous les champs.",
  invalid_current_password: "Le mot de passe actuel est incorrect.",
  password_too_short: "Le nouveau mot de passe est trop court (12 caractères minimum).",
  password_no_upper: "Le mot de passe doit contenir au moins une majuscule.",
  password_no_lower: "Le mot de passe doit contenir au moins une minuscule.",
  password_no_digit: "Le mot de passe doit contenir au moins un chiffre.",
  password_no_special: "Le mot de passe doit contenir au moins un caractère spécial.",
};

async function submitPasswordChange() {
  const current = document.getElementById("pwdCurrent")?.value || "";
  const newPw = document.getElementById("pwdNew")?.value || "";
  const confirm = document.getElementById("pwdConfirm")?.value || "";
  const feedback = document.getElementById("pwdFeedback");
  const submitBtn = document.getElementById("pwdSubmitBtn");

  if (!current || !newPw || !confirm) {
    showPwdFeedback(feedback, "Veuillez remplir tous les champs.", true);
    return;
  }
  if (newPw !== confirm) {
    showPwdFeedback(feedback, "Les mots de passe ne correspondent pas.", true);
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "En cours…";

  try {
    const csrfToken = await getCsrfToken();
    const response = await fetch("/api/me/password", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ current_password: current, new_password: newPw }),
    });
    const data = await response.json();
    if (response.ok) {
      showPwdFeedback(feedback, "Mot de passe modifié avec succès.", false);
      setTimeout(closePasswordChangeModal, 1500);
    } else {
      const msg = PASSWORD_ERROR_MESSAGES[data.error] || data.error || "Erreur inconnue.";
      showPwdFeedback(feedback, msg, true);
    }
  } catch (_) {
    showPwdFeedback(feedback, "Erreur de connexion au serveur.", true);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Valider";
  }
}

function showPwdFeedback(el, msg, isError) {
  if (!el) {
    return;
  }
  el.textContent = msg;
  el.className = "password-change-modal__feedback " +
    (isError ? "password-change-modal__feedback--error" : "password-change-modal__feedback--success");
}

document.addEventListener("DOMContentLoaded", () => {
  initBackToTop();
  initContextualHelpLinks();
  initMojibakeRepair();
  initUserMenu();
});

