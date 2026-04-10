// Panneau latéral d'aperçu rapide du tableau de bord.
// S'ouvre au clic sur une ligne de dossier, sans quitter la page.
// Dépend de getDraftById, escapeHtml, formatShortDate, formatDraftStatusLabel,
// formatQualiteLabel, buildDotationPreview, collectRequestedResourcesFromPayload
// définis dans storage.js et dashboard-preview.js.

const PANEL_ANIM_MS = 220;

function getQuickPanel() {
  return document.getElementById("quickPreviewPanel");
}

function getQuickPanelOverlay() {
  return document.getElementById("quickPreviewOverlay");
}

function closeQuickPanel() {
  const panel = getQuickPanel();
  const overlay = getQuickPanelOverlay();
  if (!panel) return;
  panel.classList.remove("quick-panel--open");
  overlay?.classList.remove("quick-panel-overlay--open");
  panel.setAttribute("aria-hidden", "true");
  panel.dataset.currentId = "";
}

function _buildResourceSection(data) {
  const items = buildDotationPreview(data);
  if (!items.length) return "";
  const rows = items.map((item) => `<li class="quick-panel__resource-item">${escapeHtml(item)}</li>`).join("");
  return `<div class="quick-panel__section">
    <h4 class="quick-panel__section-title">Ressources attribuées</h4>
    <ul class="quick-panel__resource-list">${rows}</ul>
  </div>`;
}

function _buildProgressSection(data) {
  const requested = collectRequestedResourcesFromPayload(data);
  if (!requested.length) return "";
  const completed = requested.filter((r) => r.isCompleted).length;
  const total = requested.length;
  const pct = total ? Math.round((completed / total) * 100) : 0;
  return `<div class="quick-panel__section">
    <h4 class="quick-panel__section-title">Progression attribution</h4>
    <div class="quick-panel__progress">
      <div class="quick-panel__progress-label">${completed}/${total} ressource${total > 1 ? "s" : ""}</div>
      <div class="quick-panel__progress-track">
        <div class="quick-panel__progress-bar" style="width:${pct}%"></div>
      </div>
    </div>
  </div>`;
}

function _buildUncSection(data) {
  const unc = data.unc_acces || [];
  if (!unc.length) return "";
  const rows = unc.map((u) => `<li class="quick-panel__resource-item"><code>${escapeHtml(u.chemin || "")}</code></li>`).join("");
  return `<div class="quick-panel__section">
    <h4 class="quick-panel__section-title">Accès réseau (UNC)</h4>
    <ul class="quick-panel__resource-list">${rows}</ul>
  </div>`;
}

function _buildActions(id, data) {
  const status = data.workflow?.status || "draft";
  const canRestitution = ["active"].includes(status);
  const actions = [
    `<a class="btn btn-primary quick-panel__btn" href="form.html?id=${encodeURIComponent(id)}">Ouvrir le dossier</a>`,
  ];
  if (canRestitution) {
    actions.push(`<a class="btn btn-outline-secondary quick-panel__btn" href="form.html?id=${encodeURIComponent(id)}&tab=restitution">Restitution</a>`);
  }
  return `<div class="quick-panel__actions">${actions.join("")}</div>`;
}

async function openQuickPanel(id) {
  const panel = getQuickPanel();
  const overlay = getQuickPanelOverlay();
  if (!panel) return;

  // Si déjà ouvert sur le même dossier, fermer
  if (panel.dataset.currentId === id && panel.classList.contains("quick-panel--open")) {
    closeQuickPanel();
    return;
  }

  panel.dataset.currentId = id;
  panel.innerHTML = `<div class="quick-panel__loading">Chargement…</div>`;
  panel.classList.add("quick-panel--open");
  overlay?.classList.add("quick-panel-overlay--open");
  panel.setAttribute("aria-hidden", "false");

  const result = await getDraftById(id);
  if (!result || !result.data) {
    panel.innerHTML = `<div class="quick-panel__error">Impossible de charger ce dossier.</div>`;
    return;
  }

  const data = result.data;
  const meta = result;
  const status = data.workflow?.status || "draft";
  const nom = data.beneficiaire?.nom || "";
  const prenom = data.beneficiaire?.prenom || "";
  const service = data.beneficiaire?.service || "";
  const qualite = formatQualiteLabel({ data });
  const statusLabel = formatDraftStatusLabel({ status, data });
  const startAt = data.meta?.startAt || "";
  const dossierType = data.dossier?.type || "";
  const startLabel = dossierType === "mise_a_jour"
    ? null
    : startAt ? `Prise de fonction : ${formatShortDate(startAt)}` : "Prise de fonction non renseignée";

  panel.innerHTML = `
    <div class="quick-panel__header">
      <button class="quick-panel__close" type="button" aria-label="Fermer l'aperçu">✕</button>
      <div class="quick-panel__identity">
        <span class="quick-panel__name">${escapeHtml(`${prenom} ${nom}`.trim() || "Sans nom")}</span>
        <span class="quick-panel__meta">${escapeHtml(qualite)}${service ? ` · ${escapeHtml(service)}` : ""}</span>
      </div>
      <span class="status-chip status-chip--${escapeHtml(status)} quick-panel__status">${escapeHtml(statusLabel)}</span>
    </div>
    <div class="quick-panel__body">
      ${startLabel ? `<p class="quick-panel__start">${escapeHtml(startLabel)}</p>` : ""}
      ${_buildProgressSection(data)}
      ${_buildResourceSection(data)}
      ${_buildUncSection(data)}
    </div>
    ${_buildActions(id, data)}
  `;

  panel.querySelector(".quick-panel__close")?.addEventListener("click", closeQuickPanel);
}

function bindQuickPreviews() {
  document.querySelectorAll("[data-quick-preview-id]").forEach((row) => {
    if (row.dataset.quickPreviewBound) return;
    row.addEventListener("click", (e) => {
      // Ne pas intercepter les clics sur les boutons/liens/checkbox de la ligne
      if (e.target.closest("button, a, input, .draft-actions, details")) return;
      void openQuickPanel(row.dataset.quickPreviewId);
    });
    row.dataset.quickPreviewBound = "true";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const overlay = getQuickPanelOverlay();
  overlay?.addEventListener("click", closeQuickPanel);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeQuickPanel();
  });

  // Rebind après chaque rechargement du tableau de bord
  const draftList = document.getElementById("draftList");
  const restitutionList = document.getElementById("restitutionList");

  const observer = new MutationObserver(() => bindQuickPreviews());
  if (draftList) observer.observe(draftList, { childList: true });
  if (restitutionList) observer.observe(restitutionList, { childList: true });
});
