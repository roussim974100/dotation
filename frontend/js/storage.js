const STORAGE_KEY = "dotationDraftsCache";
const DASHBOARD_PENDING_UPDATES_KEY = "dashboardPendingUpdates";
const API_BASE = "/api/forms";
const PDF_BATCH_EXPORT_ENDPOINT = "/api/forms/export-pdf-batch";
const RESTITUTION_PDF_BATCH_EXPORT_ENDPOINT = "/api/forms/export-restitution-pdf-batch";
const DASHBOARD_REFRESH_INTERVAL_MS = 20000;
const DASHBOARD_SIGNATURE_LINK_NOTICE_KEY = "dashboardSignatureLinkNotice";
let sessionInfo = null;
let currentDraftRows = [];
let dashboardRefreshTimer = null;
let dashboardRefreshInFlight = false;
let dashboardLastUpdatedAt = "";
let dashboardKnownIds = new Set();
let dashboardPendingNewIds = new Set();
let dashboardSelectedIds = new Set();
let exportProgressFallbackTimer = null;
let exportProgressValue = 0;
const dashboardFilters = {
  search: "",
  status: "",
  timing: "",
  qualite: "",
  service: ""
};

// Cache navigateur de secours : utile hors backend ou en cas de coupure réseau.
function getCachedDrafts() {
  try {
    const drafts = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(drafts) ? drafts : [];
  } catch (error) {
    return [];
  }
}

function setCachedDrafts(drafts) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts));
}

function loadPendingDashboardUpdates() {
  try {
    const raw = sessionStorage.getItem(DASHBOARD_PENDING_UPDATES_KEY);
    const ids = JSON.parse(raw || "[]");
    return new Set(Array.isArray(ids) ? ids : []);
  } catch (error) {
    return new Set();
  }
}

function persistPendingDashboardUpdates() {
  try {
    sessionStorage.setItem(
      DASHBOARD_PENDING_UPDATES_KEY,
      JSON.stringify([...dashboardPendingNewIds])
    );
  } catch (error) {
    // Rien de bloquant : le tableau de bord reste utilisable sans cette persistance.
  }
}

function loadDashboardSignatureLinkNotice() {
  try {
    const raw = sessionStorage.getItem(DASHBOARD_SIGNATURE_LINK_NOTICE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function persistDashboardSignatureLinkNotice(payload) {
  try {
    if (!payload) {
      sessionStorage.removeItem(DASHBOARD_SIGNATURE_LINK_NOTICE_KEY);
      return;
    }
    sessionStorage.setItem(DASHBOARD_SIGNATURE_LINK_NOTICE_KEY, JSON.stringify(payload));
  } catch (error) {
    // Rien de bloquant.
  }
}

function upsertCachedDraft(summary, payload) {
  // On garde un snapshot local minimal pour la reprise rapide d'une fiche.
  const drafts = getCachedDrafts();
  const normalized = {
    id: summary.id,
    title: summary.title,
    status: summary.status,
    isLocked: summary.isLocked,
    beneficiaryType: summary.beneficiaryType,
    nom: summary.nom,
    prenom: summary.prenom,
    service: summary.service,
    fonction: summary.fonction,
    mandat: summary.mandat,
    assignedAt: summary.assignedAt,
    returnedAt: summary.returnedAt,
    updatedAt: summary.updatedAt,
    data: payload
  };
  const index = drafts.findIndex((draft) => draft.id === normalized.id);

  if (index >= 0) {
    drafts[index] = normalized;
  } else {
    drafts.unshift(normalized);
  }

  setCachedDrafts(drafts);
}

function removeCachedDraft(id) {
  const drafts = getCachedDrafts().filter((draft) => draft.id !== id);
  setCachedDrafts(drafts);
}

function buildDraftTitle(data) {
  const qualite = data.beneficiaire.qualite;
  const service = data.beneficiaire.service || "SERVICE";
  const mandat = data.beneficiaire.mandat || "MANDAT";
  const nom = (data.beneficiaire.nom || "SANS NOM").toUpperCase();
  const prenom = data.beneficiaire.prenom || "";
  const prefix = qualite === "elu" ? mandat : service;
  return `${prefix.toUpperCase()} - ${nom} ${prenom}`.trim();
}

function buildLocalSummary(payload) {
  // Résumé reconstruit localement quand l'API n'est pas joignable.
  const now = new Date().toISOString();
  const status = payload.workflow.status || "draft";
  const beneficiaire = payload.beneficiaire || {};
  const id = payload.meta.id || `local-${Date.now()}`;

  payload.meta = {
    ...(payload.meta || {}),
    id,
    savedAt: now,
    createdAt: payload.meta.createdAt || now
  };

  const progress = summarizeDraftProgressFromPayload(payload);

  return {
    id,
    title: buildDraftTitle(payload),
    dossierType: payload.dossier.type || "arrivee",
    status,
    isLocked: Boolean(payload.meta.lockedAt),
    beneficiaryType: beneficiaire.qualite || "",
    nom: beneficiaire.nom || "",
    prenom: beneficiaire.prenom || "",
    service: beneficiaire.service || "",
    fonction: beneficiaire.fonction || "",
    mandat: beneficiaire.mandat || "",
    assignedAt: payload.meta.assignedAt || now,
    startAt: payload.meta.startAt || "",
    returnedAt: payload.restitution.returnedAt || "",
    updatedAt: now,
    completedResources: progress.completed,
    totalResources: progress.total,
    resourceProgressRatio: progress.ratio,
    timingStatus: progress.timingStatus,
    timingLabel: progress.timingLabel
  };
}

function collectRequestedResourcesFromPayload(payload) {
  const resources = [];
  const pushIfSelected = (item, key) => {
    if (item?.selected) {
      resources.push({ key, assignedAt: item.assignedAt || "" });
    }
  };

  const materiel = payload?.materiel || {};
  const immateriel = payload?.immateriel || {};
  Object.entries(materiel).forEach(([key, item]) => pushIfSelected(item, key));
  Object.entries(immateriel).forEach(([key, item]) => pushIfSelected(item, key));
  (payload?.resources?.additional || []).forEach((resource) => {
    if (resource?.selected) {
      resources.push({ key: resource.id || resource.code || "resource", assignedAt: resource.assignedAt || "" });
    }
  });
  return resources;
}

function summarizeDraftProgressFromPayload(payload = {}) {
  const requested = collectRequestedResourcesFromPayload(payload);
  const total = requested.length;
  const completed = requested.filter((resource) => resource.assignedAt).length;
  const startAt = payload?.meta?.startAt || "";

  if (total === 0) {
    return { completed: 0, total: 0, ratio: 0, timingStatus: "neutral", timingLabel: "À planifier" };
  }
  if (completed >= total) {
    return { completed, total, ratio: 1, timingStatus: "ok", timingLabel: "Prêt" };
  }
  if (!startAt) {
    return { completed, total, ratio: completed / total, timingStatus: "neutral", timingLabel: "À planifier" };
  }

  const startDate = new Date(/^\d{4}-\d{2}-\d{2}$/.test(startAt) ? `${startAt}T00:00:00` : startAt);
  if (Number.isNaN(startDate.getTime())) {
    return { completed, total, ratio: completed / total, timingStatus: "neutral", timingLabel: "À planifier" };
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  startDate.setHours(0, 0, 0, 0);
  const daysUntilStart = Math.round((startDate - today) / 86400000);
  if (daysUntilStart < 0) {
    return { completed, total, ratio: completed / total, timingStatus: "late", timingLabel: "En retard" };
  }
  if (daysUntilStart <= 3) {
    return { completed, total, ratio: completed / total, timingStatus: "warning", timingLabel: "En danger" };
  }
  return { completed, total, ratio: completed / total, timingStatus: "ok", timingLabel: "Dans les temps" };
}

function getDraftProgressMetrics(draft) {
  if (Number.isFinite(draft.completedResources) && Number.isFinite(draft.totalResources)) {
    return {
      completed: draft.completedResources,
      total: draft.totalResources,
      ratio: Number.isFinite(draft.resourceProgressRatio) ? draft.resourceProgressRatio : (draft.totalResources ? draft.completedResources / draft.totalResources : 0),
      timingStatus: draft.timingStatus || "neutral",
      timingLabel: draft.timingLabel || "À planifier"
    };
  }
  return summarizeDraftProgressFromPayload(draft.data || {});
}

function formatShortDate(value) {
  if (!value) {
    return "-";
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" }).format(date);
}

function buildDashboardRow(draft, permissions) {
  const progress = getDraftProgressMetrics(draft);
  const progressPercent = Math.max(0, Math.min(100, Math.round((progress.ratio || 0) * 100)));
  const title = draft.title || (draft.data ? buildDraftTitle(draft.data) : "Dossier");
  const dossierTypeLabel = formatDossierTypeLabel(draft.dossierType || draft.data?.dossier?.type || "");
  const startAtLabel = draft.startAt
    ? `Prise de fonction : ${escapeHtml(formatShortDate(draft.startAt))}`
    : "Prise de fonction non renseignée";

  return `
    <tr class="draft-row ${dashboardPendingNewIds.has(draft.id) ? "draft-row--new" : ""}">
      <td class="draft-check-col">
        ${(permissions.canExport || permissions.canDelete) ? `<input class="form-check-input draft-select" type="checkbox" value="${draft.id}" aria-label="Sélectionner ${escapeHtml(title)}">` : ""}
      </td>
      <td data-label="Dossier">
        <div class="draft-title">${escapeHtml(title)}</div>
        <div class="draft-meta">${escapeHtml(dossierTypeLabel)}</div>
        <div class="draft-meta">${escapeHtml(draft.nom || draft.data?.beneficiaire?.nom || "")} ${escapeHtml(draft.prenom || draft.data?.beneficiaire?.prenom || "")}</div>
        <div class="draft-meta">${startAtLabel}</div>
      </td>
      <td data-label="Qualité">${escapeHtml(formatQualiteLabel(draft))}</td>
      <td data-label="État"><span class="status-chip status-chip--${escapeHtml(draft.status || "draft")}" data-status-preview-id="${draft.id}">${escapeHtml(formatStatusLabel(draft.status || "draft"))}</span></td>
      <td data-label="Pilotage">
        <span class="timing-chip timing-chip--${escapeHtml(progress.timingStatus)}">${escapeHtml(progress.timingLabel)}</span>
      </td>
      <td data-label="Progression">
        <div class="resource-progress">
          <div class="resource-progress__fraction">${progress.completed}/${progress.total}</div>
          <div class="resource-progress__track">
            <div class="resource-progress__bar" style="width:${progressPercent}%"></div>
          </div>
        </div>
      </td>
      <td data-label="Dernière modification">${escapeHtml(formatDate(draft.updatedAt))}</td>
      <td data-label="Actions" class="draft-actions-cell">
        <div class="draft-actions">
          ${buildDraftActionButtons(draft, permissions)}
        </div>
      </td>
    </tr>
  `;
}

function formatQualiteLabel(item) {
  const qualite = item.beneficiaryType || item.data?.beneficiaire?.qualite;
  if (qualite === "elu") {
    return item.mandat || item.data?.beneficiaire?.mandat || "Élu";
  }
  if (qualite === "agent") {
    return item.service || item.data?.beneficiaire?.service || "Agent";
  }
  return "Non renseigné";
}

function formatStatusLabel(status) {
  const labels = {
    draft: "À compléter",
    partial_assignment: "Attribution partielle",
    awaiting_signature: "En attente de signature",
    active: "Attribution active",
    returned: "Restitution terminée",
    partial_return: "Restitution partielle",
    cancelled: "Dossier annulé"
  };
  return labels[status] || "À compléter";
}

function hasRestitutionData(draft) {
  const restitution = draft.data?.restitution || {};
  return Boolean(
    draft.returnedAt
    || draft.returnReason
    || restitution.returnedAt
    || restitution.notes
    || restitution.reason
    || restitution.signatureDataUrl
    || restitution.signatureReason
    || Object.keys(restitution.items || {}).length
  );
}

function hasAssignmentSignature(draft) {
  return Boolean(draft.data?.validation?.signatureDataUrl);
}

function hasRestitutionSignature(draft) {
  return Boolean(draft.data?.restitution?.signatureDataUrl);
}

function canRequestAssignmentSignature(draft, options) {
  return Boolean(
    options.canEdit
    && !hasRestitutionData(draft)
    && !hasAssignmentSignature(draft)
    && ["draft", "partial_assignment", "awaiting_signature"].includes(draft.status || "draft")
  );
}

function canRequestRestitutionSignature(draft, options) {
  const restitution = draft.data?.restitution || {};
  const signatureStatus = restitution.signatureStatus || "";
  return Boolean(
    options.canRestitution
    && hasRestitutionData(draft)
    && !hasRestitutionSignature(draft)
    && signatureStatus !== "impossible"
    && ["active", "partial_return", "awaiting_signature"].includes(draft.status || "draft")
  );
}

function canOpenRestitution(draft, options) {
  if (!options.canRestitution) {
    return false;
  }
  const status = draft.status || "draft";
  if (["active", "partial_return", "returned"].includes(status)) {
    return true;
  }
  return status === "awaiting_signature" && hasRestitutionData(draft);
}

function isRestitutionDashboardDraft(draft) {
  const status = draft.status || "draft";
  return hasRestitutionData(draft) || ["partial_return", "returned"].includes(status);
}

function renderDraftActionMenu(label, tone, actions) {
  const sections = actions.filter((action) => String(action || "").trim());
  if (!sections.length) {
    return "";
  }
  return `
    <details class="draft-actions__menu" data-action-menu data-label="${escapeHtml(label)}" data-open-label="${escapeHtml(`${label} - moins d'actions`)}">
      <summary class="btn btn-sm ${tone}"><span data-action-menu-label>${escapeHtml(label)}</span></summary>
      <div class="draft-actions__menu-panel">
        ${sections.map((action) => `<div class="draft-actions__menu-section">${action}</div>`).join("")}
      </div>
    </details>
  `;
}

function buildDraftActionButtons(draft, options) {
  const openActions = [
    `<button class="btn btn-sm btn-primary" type="button" onclick="editDraft('${draft.id}')">Ouvrir dossier</button>`
  ];

  if (canOpenRestitution(draft, options)) {
    openActions.push(`<button class="btn btn-sm btn-outline-primary" type="button" onclick="openRestitution('${draft.id}')">Ouvrir restitution</button>`);
  }

  const pdfActions = [];
  if (options.canExport) {
    pdfActions.push(`<button class="btn btn-sm btn-outline-success" type="button" onclick="exportDraftPdf('${draft.id}')">Télécharger le PDF dossier</button>`);
    pdfActions.push(`<button class="btn btn-sm btn-outline-success" type="button" onclick="prepareDraftPdfEmail('${draft.id}')">Envoyer le PDF dossier</button>`);
  }
  if (options.canExport && hasRestitutionData(draft)) {
    pdfActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="exportRestitutionPdf('${draft.id}')">Télécharger le PDF restitution</button>`);
    pdfActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="prepareRestitutionPdfEmail('${draft.id}')">Envoyer le PDF restitution</button>`);
  }

  const signatureActions = [];
  if (canRequestAssignmentSignature(draft, options)) {
    signatureActions.push(`<button class="btn btn-sm btn-outline-info" type="button" onclick="prepareAssignmentSignatureEmail('${draft.id}')">Préparer l'e-mail de signature</button>`);
    signatureActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="shareSignatureLink('${draft.id}')">Copier le lien de signature</button>`);
  }

  if (canRequestRestitutionSignature(draft, options)) {
    signatureActions.push(`<button class="btn btn-sm btn-outline-info" type="button" onclick="prepareRestitutionSignatureEmail('${draft.id}')">Préparer l'e-mail de signature</button>`);
    signatureActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="copyRestitutionSignatureLink('${draft.id}')">Copier le lien de signature</button>`);
  }

  const managementActions = [];
  if (options.canDelete) {
    managementActions.push(`<button class="btn btn-sm btn-outline-danger" type="button" onclick="removeDraft('${draft.id}')">Supprimer le dossier</button>`);
  }

  return `
    <div class="draft-actions__primary">
      ${renderDraftActionMenu("Ouvrir", "btn-outline-primary", [openActions.join("")])}
      ${renderDraftActionMenu("PDF", "btn-outline-success", [pdfActions.join("")])}
      ${renderDraftActionMenu("Signature", "btn-outline-info", [signatureActions.join("")])}
      ${renderDraftActionMenu("Gestion", "btn-outline-secondary", [managementActions.join("")])}
    </div>
  `;
}

function bindDraftActionMenus() {
  document.querySelectorAll("[data-action-menu]").forEach((menu) => {
    if (menu.dataset.boundActionMenu) {
      return;
    }

    const labelNode = menu.querySelector("[data-action-menu-label]");
    const defaultLabel = menu.dataset.label || "Actions";
    const openLabel = menu.dataset.openLabel || "Moins d'actions";

    const updateLabel = () => {
      if (labelNode) {
        labelNode.textContent = menu.open ? openLabel : defaultLabel;
      }
    };

    menu.addEventListener("toggle", () => {
      if (menu.open) {
        menu.closest(".draft-actions")?.querySelectorAll("[data-action-menu]").forEach((otherMenu) => {
          if (otherMenu !== menu) {
            otherMenu.open = false;
          }
        });
      }
      updateLabel();
    });

    updateLabel();
    menu.dataset.boundActionMenu = "true";
  });
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function getDraftSearchText(draft) {
  const status = draft.status || "draft";
  const timingLabel = draft.timingLabel || draft.data?.timingLabel || "";
  return [
    draft.title || (draft.data ? buildDraftTitle(draft.data) : ""),
    draft.nom || draft.data?.beneficiaire?.nom || "",
    draft.prenom || draft.data?.beneficiaire?.prenom || "",
    draft.service || draft.data?.beneficiaire?.service || "",
    draft.fonction || draft.data?.beneficiaire?.fonction || "",
    draft.mandat || draft.data?.beneficiaire?.mandat || "",
    formatStatusLabel(status),
    status,
    timingLabel,
    draft.timingStatus || ""
  ].join(" ");
}

function getDraftQualiteValue(draft) {
  return draft.beneficiaryType || draft.data?.beneficiaire?.qualite || "";
}

function getDraftServiceValue(draft) {
  return draft.service || draft.data?.beneficiaire?.service || "";
}

function applyDashboardFilters(drafts) {
  return drafts.filter((draft) => {
    const matchesSearch = !dashboardFilters.search
      || normalizeText(getDraftSearchText(draft)).includes(normalizeText(dashboardFilters.search));
    const matchesStatus = !dashboardFilters.status || (draft.status || "draft") === dashboardFilters.status;
    const matchesTiming = !dashboardFilters.timing || (draft.timingStatus || "") === dashboardFilters.timing;
    const matchesQualite = !dashboardFilters.qualite || getDraftQualiteValue(draft) === dashboardFilters.qualite;
    const matchesService = !dashboardFilters.service || getDraftServiceValue(draft) === dashboardFilters.service;
    return matchesSearch && matchesStatus && matchesTiming && matchesQualite && matchesService;
  });
}

function hydrateServiceFilterOptions(drafts) {
  const serviceFilter = document.getElementById("serviceFilter");
  if (!serviceFilter) {
    return;
  }

  const currentValue = serviceFilter.value;
  const services = [...new Set(
    drafts
      .map((draft) => getDraftServiceValue(draft))
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, "fr"))
  )];

  serviceFilter.innerHTML = [
    '<option value="">Tous les services</option>',
    ...services.map((service) => `<option value="${escapeHtml(service)}">${escapeHtml(service)}</option>`)
  ].join("");
  serviceFilter.value = services.includes(currentValue) ? currentValue : dashboardFilters.service;
}

function buildDotationPreview(data) {
  // Petit résumé lisible utilisé dans le hover de l'état.
  if (!data) {
    return [];
  }

  const items = [];
  const materiel = data.materiel || {};
  const immateriel = data.immateriel || {};
  const pushItem = (label, detail) => {
    items.push(detail ? `${label} : ${detail}` : label);
  };

  if (materiel.ordinateur?.selected) {
    pushItem("Ordinateur", [materiel.ordinateur.nomPoste, materiel.ordinateur.marque, materiel.ordinateur.modele].filter(Boolean).join(" - "));
  }
  if (materiel.ecran?.selected) {
    pushItem("Écran", [materiel.ecran.marque, materiel.ecran.modele].filter(Boolean).join(" - "));
  }
  if (materiel.telephone?.selected) {
    pushItem("Téléphone", [materiel.telephone.nomTelephone, materiel.telephone.marque, materiel.telephone.modele].filter(Boolean).join(" - "));
  }
  if (materiel.tablette?.selected) {
    pushItem("Tablette", [materiel.tablette.nomTablette, materiel.tablette.marque, materiel.tablette.modele].filter(Boolean).join(" - "));
  }
  if (immateriel.email?.selected) {
    pushItem("Email", immateriel.email.adresse || "");
  }
  if (immateriel.vpn?.selected) {
    pushItem("VPN", "");
  }
  if (materiel.badge?.selected) {
    pushItem("Badge", materiel.badge.numero || "");
  }
  if (materiel.cles?.selected) {
    pushItem("Clé(s)", (materiel.cles.values || []).filter(Boolean).join(" - "));
  }
  if (materiel.veste?.selected) {
    pushItem("Veste", "");
  }
  if (materiel.chaussuresSecurite?.selected) {
    pushItem("Chaussures de sécurité", "");
  }
  if (immateriel.zoneAlarme?.selected) {
    pushItem("Zone alarme", (immateriel.zoneAlarme.zones || []).filter(Boolean).join(" - "));
  }
  if (materiel.vehicule?.selected) {
    pushItem("Véhicule", [materiel.vehicule.marque, materiel.vehicule.modele].filter(Boolean).join(" - "));
  }
  if (materiel.autre?.selected) {
    pushItem("Autre matériel", materiel.autre.description || "");
  }
  for (const resource of data.resources?.additional || []) {
    if (resource.selected) {
      pushItem(resource.label || "Ressource complémentaire", resource.details || "");
    }
  }

  return items;
}

function formatDossierTypeLabel(dossierType) {
  const labels = {
    arrivee: "Nouvelle arrivée",
    changement_service: "Changement de service",
    mise_a_jour: "Mise à jour de ressources",
    sortie: "Sortie / restitution"
  };
  const legacyMap = {
    nouvel_agent: "arrivee",
    nouvel_elu: "arrivee",
    elu_en_place: "mise_a_jour"
  };
  return labels[legacyMap[dossierType] || dossierType] || "Dossier";
}

async function requestJson(url, options = {}) {
  // Wrapper fetch centralisé :
  // - JSON par défaut
  // - propagation d'un code d'erreur exploitable par le frontend
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    credentials: "same-origin",
    ...options
  });

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    const requestError = new Error(payload.error || `HTTP ${response.status}`);
    requestError.status = response.status;
    throw requestError;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function listForms() {
  try {
    const forms = await requestJson(API_BASE);
    return forms;
  } catch (error) {
    return getCachedDrafts();
  }
}

async function getSessionInfo() {
  // Charge le contexte utilisateur une seule fois pour piloter les boutons affichés.
  if (sessionInfo) {
    return sessionInfo;
  }
  try {
    sessionInfo = await requestJson("/api/session");
  } catch (error) {
    sessionInfo = null;
  }
  return sessionInfo;
}

async function getDraftById(id) {
  try {
    const result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}`);
    upsertCachedDraft(result.summary, result.data);
    return result;
  } catch (error) {
    const fallback = getCachedDrafts().find((draft) => draft.id === id);
    if (!fallback) {
      return null;
    }
    return {
      summary: fallback,
      data: fallback.data,
      items: []
    };
  }
}

async function saveFormData(payload) {
  // Sauvegarde backend prioritaire, avec fallback local uniquement si le serveur est indisponible.
  const formId = payload.meta.id;
  const url = formId ? `${API_BASE}/${encodeURIComponent(formId)}` : API_BASE;
  const method = formId ? "PUT" : "POST";

  try {
    const result = await requestJson(url, {
      method,
      body: JSON.stringify(payload)
    });

    upsertCachedDraft(result.summary, result.data);
    return result;
  } catch (error) {
    if (error.status) {
      throw error;
    }
    const summary = buildLocalSummary(payload);
    upsertCachedDraft(summary, payload);
    return {
      summary,
      data: payload,
      items: [],
      offline: true
    };
  }
}

async function deleteDraft(id) {
  try {
    await requestJson(`${API_BASE}/${encodeURIComponent(id)}`, {
      method: "DELETE"
    });
  } finally {
    removeCachedDraft(id);
  }
}

function newForm() {
  if (!(sessionInfo?.permissions?.includes("*") || sessionInfo?.permissions?.includes("forms.create"))) {
    window.alert("Votre profil est en consultation seule. La création de dossier n'est pas autorisée.");
    return;
  }
  window.location.href = "form.html";
}

function editDraft(id) {
  window.location.href = `form.html?id=${encodeURIComponent(id)}`;
}

function openRestitution(id) {
  window.location.href = `restitution.html?id=${encodeURIComponent(id)}`;
}

async function renderDraftList() {
  if (dashboardRefreshInFlight) {
    return;
  }
  dashboardRefreshInFlight = true;
  // Écran principal :
  // - liste toutes les fiches
  // - sépare les attributions et les restitutions
  // - calcule le compteur des fiches encore à compléter
  // - affiche les actions selon les droits de l'utilisateur
  const draftList = document.getElementById("draftList");
  const restitutionList = document.getElementById("restitutionList");
  const assignmentDraftCount = document.getElementById("assignmentDraftCount");
  const restitutionDraftCount = document.getElementById("restitutionDraftCount");
  const emptyState = document.getElementById("emptyState");
  const assignmentEmptyState = document.getElementById("assignmentEmptyState");
  const restitutionEmptyState = document.getElementById("restitutionEmptyState");
  const assignmentCountBadge = document.getElementById("assignmentCountBadge");
  const restitutionCountBadge = document.getElementById("restitutionCountBadge");

  if (!draftList || !restitutionList) {
    dashboardRefreshInFlight = false;
    return;
  }

  try {
    captureDashboardSelection();
    const drafts = await listForms();
    const sortedDrafts = [...drafts].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
    const previousIds = new Set(dashboardKnownIds);
    const newDraftIds = previousIds.size === 0
      ? []
      : sortedDrafts
        .map((draft) => draft.id)
        .filter((id) => id && !previousIds.has(id));
    dashboardKnownIds = new Set(sortedDrafts.map((draft) => draft.id).filter(Boolean));
    dashboardPendingNewIds = new Set(
      [...dashboardPendingNewIds].filter((id) => dashboardKnownIds.has(id))
    );
    newDraftIds.forEach((id) => dashboardPendingNewIds.add(id));
    persistPendingDashboardUpdates();
    currentDraftRows = sortedDrafts;
    hydrateServiceFilterOptions(sortedDrafts);
    const filteredDrafts = applyDashboardFilters(sortedDrafts);
    const assignmentDrafts = filteredDrafts.filter((draft) => !isRestitutionDashboardDraft(draft));
    const restitutionDrafts = filteredDrafts.filter((draft) => isRestitutionDashboardDraft(draft));
    const completableAssignmentDrafts = assignmentDrafts.filter((draft) => ["draft", "partial_assignment", "awaiting_signature"].includes(draft.status || "draft"));
    const completableRestitutionDrafts = restitutionDrafts.filter((draft) => ["partial_return", "awaiting_signature"].includes(draft.status || "draft"));

    if (assignmentDraftCount) {
      assignmentDraftCount.textContent = completableAssignmentDrafts.length.toString();
    }
    if (restitutionDraftCount) {
      restitutionDraftCount.textContent = completableRestitutionDrafts.length.toString();
    }
    if (assignmentCountBadge) {
      assignmentCountBadge.textContent = assignmentDrafts.length.toString();
    }
    if (restitutionCountBadge) {
      restitutionCountBadge.textContent = restitutionDrafts.length.toString();
    }

    if (filteredDrafts.length === 0) {
      draftList.innerHTML = "";
      restitutionList.innerHTML = "";
      dashboardSelectedIds = new Set();
      emptyState.classList.remove("d-none");
      assignmentEmptyState?.classList.add("d-none");
      restitutionEmptyState?.classList.add("d-none");
      updateDashboardRefreshInfo();
      setDashboardUpdateNotice();
      updateExportSelectedState();
      return;
    }

    emptyState.classList.add("d-none");
    const user = await getSessionInfo();
    const canExport = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.export"));
    const canDelete = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.delete"));
    const canRestitution = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.restitution"));
    const canEdit = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.edit"));
    draftList.innerHTML = assignmentDrafts
      .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
      .join("");
    restitutionList.innerHTML = restitutionDrafts
      .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
      .join("");
    assignmentEmptyState?.classList.toggle("d-none", assignmentDrafts.length > 0);
    restitutionEmptyState?.classList.toggle("d-none", restitutionDrafts.length > 0);

    dashboardLastUpdatedAt = new Date().toISOString();
    updateDashboardRefreshInfo();
    setDashboardUpdateNotice();
    bindStatusPreviews();
    bindDraftActionMenus();
    bindSelectionActions(canExport, canDelete);
    restoreDashboardSelection();
  } finally {
    dashboardRefreshInFlight = false;
  }
}

function saveBlob(blob, filename) {
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl);
  }, 1500);
}

function parseDownloadFileName(response, fallback) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const fileNameMatch = disposition.match(/filename="([^"]+)"/i);
  return fileNameMatch ? fileNameMatch[1] : fallback;
}

function getPdfEmailRecipient(draft) {
  const payload = draft?.data || {};
  return (
    payload?.immateriel?.email?.adresse
    || payload?.beneficiaire?.email
    || ""
  ).trim();
}

function toBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

function wrapBase64Lines(value, lineLength = 76) {
  const lines = [];
  for (let index = 0; index < value.length; index += lineLength) {
    lines.push(value.slice(index, index + lineLength));
  }
  return lines;
}

function buildPdfEmailContent({ recipientEmail, subject, bodyLines, attachmentName, attachmentBase64 }) {
  const boundary = `----=_Dotation_${Date.now().toString(16)}_${Math.random().toString(16).slice(2, 10)}`;
  return [
    "X-Unsent: 1",
    `Subject: ${subject}`,
    `To: ${recipientEmail}`,
    "MIME-Version: 1.0",
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    ...bodyLines,
    "",
    `--${boundary}`,
    `Content-Type: application/pdf; name="${attachmentName}"`,
    "Content-Transfer-Encoding: base64",
    `Content-Disposition: attachment; filename="${attachmentName}"`,
    "",
    ...wrapBase64Lines(attachmentBase64),
    `--${boundary}--`
  ].join("\r\n");
}

async function fetchPdfDocument(id, kind) {
  const isRestitution = kind === "restitution";
  const config = isRestitution
    ? {
        endpoint: `${API_BASE}/${encodeURIComponent(id)}/restitution-pdf`,
        title: "Préparation du PDF restitution",
        text: "Le bon de restitution est en cours de génération.",
        fallbackName: `restitution-${id}.pdf`
      }
    : {
        endpoint: `${API_BASE}/${encodeURIComponent(id)}/pdf`,
        title: "Préparation du PDF dossier",
        text: "Le document est en cours de génération.",
        fallbackName: `dossier-${id}.pdf`
      };

  showExportLoader(config.title, config.text);
  try {
    const { response, blob } = await fetchDownloadWithProgress(config.endpoint, {
      credentials: "same-origin"
    });
    return {
      blob,
      fileName: parseDownloadFileName(response, config.fallbackName)
    };
  } finally {
    window.setTimeout(() => {
      hideExportLoader();
    }, 250);
  }
}

async function preparePdfEmail(id, kind) {
  try {
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    const { blob, fileName } = await fetchPdfDocument(id, kind);
    const attachmentBase64 = toBase64(await blob.arrayBuffer());
    const recipientEmail = getPdfEmailRecipient(draft);
    const title = draft?.title || "Dossier";
    const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
    const documentLabel = kind === "restitution" ? "PDF de restitution" : "PDF de dossier";
    const emailContent = buildPdfEmailContent({
      recipientEmail,
      subject: `${documentLabel} - ${title}`,
      bodyLines: [
        "Bonjour,",
        "",
        `Vous trouverez en piece jointe le ${documentLabel.toLowerCase()}.`,
        `Dossier : ${title}`,
        fullName ? `Personne concernée : ${fullName}` : "",
        "",
        "Cordialement,"
      ].filter(Boolean),
      attachmentName: fileName,
      attachmentBase64
    });
    const emailFileName = `${sanitizeDownloadFileName(`${kind}_pdf_email_${title}`, `${kind}_pdf_email`)}.eml`;
    saveBlob(new Blob([emailContent], { type: "message/rfc822;charset=utf-8" }), emailFileName);
  } catch (error) {
    window.alert(
      error.message || (kind === "restitution"
        ? "Impossible de préparer l'e-mail du PDF restitution."
        : "Impossible de préparer l'e-mail du PDF dossier.")
    );
  }
}

async function prepareDraftPdfEmail(id) {
  await preparePdfEmail(id, "dossier");
}

async function prepareRestitutionPdfEmail(id) {
  await preparePdfEmail(id, "restitution");
}

async function exportDraftPdf(id) {
  try {
    const { blob, fileName } = await fetchPdfDocument(id, "dossier");
    saveBlob(blob, fileName);
  } catch (error) {
    alert("Impossible de générer le PDF dossier.");
  }
}

async function exportRestitutionPdf(id) {
  try {
    const { blob, fileName } = await fetchPdfDocument(id, "restitution");
    saveBlob(blob, fileName);
  } catch (error) {
    alert("Impossible de générer le PDF restitution.");
  }
}

function findDraftSummary(id) {
  return currentDraftRows.find((draft) => draft.id === id) || getCachedDrafts().find((draft) => draft.id === id) || null;
}

async function copyTextWithFallback(text, promptLabel) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    window.prompt(promptLabel, text);
    return false;
  }
}

function sanitizeDownloadFileName(value, fallback = "document") {
  const normalized = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return normalized || fallback;
}

function getRestitutionRecipientEmail(draft) {
  const payload = draft?.data || {};
  return (
    payload?.immateriel?.email?.adresse
    || payload?.beneficiaire?.email
    || ""
  ).trim();
}

function buildRestitutionEmailContent(draft, absoluteUrl) {
  const title = draft?.title || "Dossier";
  const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
  const recipientEmail = getRestitutionRecipientEmail(draft);
  const lines = [
    "Bonjour,",
    "",
    "Vous trouverez ci-dessous le lien pour consulter et signer la restitution :",
    absoluteUrl,
    "",
    `Dossier : ${title}`,
    fullName ? `Personne concernée : ${fullName}` : "",
    "",
    "Cordialement,"
  ].filter(Boolean);

  return [
    "X-Unsent: 1",
    "Subject: Lien de signature de restitution",
    `To: ${recipientEmail}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    ...lines
  ].join("\r\n");
}

function buildAssignmentSignatureEmailContent(draft, absoluteUrl) {
  const title = draft?.title || "Dossier";
  const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
  const recipientEmail = getPdfEmailRecipient(draft);
  const lines = [
    "Bonjour,",
    "",
    "Vous trouverez ci-dessous le lien pour consulter et signer le dossier d'attribution :",
    absoluteUrl,
    "",
    `Dossier : ${title}`,
    fullName ? `Personne concernée : ${fullName}` : "",
    "",
    "Cordialement,"
  ].filter(Boolean);

  return [
    "X-Unsent: 1",
    "Subject: Lien de signature du dossier d'attribution",
    `To: ${recipientEmail}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    ...lines
  ].join("\r\n");
}

async function ensureAssignmentSignatureLink(id) {
  let result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/signature-link`);
  if (!result?.link || result.link.status !== "active" || !result.link.url) {
    result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/signature-link`, {
      method: "POST"
    });
  }
  return {
    link: result.link,
    absoluteUrl: new URL(result.link.url, window.location.origin).href
  };
}

async function ensureRestitutionSignatureLink(id) {
  let result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/restitution-signature-link`);
  if (!result?.link || result.link.status !== "active" || !result.link.url) {
    result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/restitution-signature-link`, {
      method: "POST"
    });
  }
  return {
    link: result.link,
    absoluteUrl: new URL(result.link.url, window.location.origin).href
  };
}

async function shareSignatureLink(id) {
  try {
    const { absoluteUrl } = await ensureAssignmentSignatureLink(id);
    const copied = await copyTextWithFallback(absoluteUrl, "Copiez ce lien de signature :");
    window.alert(copied ? "Lien de signature copié dans le presse-papiers." : "Lien de signature prêt à être copié.");
  } catch (error) {
    window.alert(error.message || "Impossible de préparer le lien de signature.");
  }
}

async function prepareAssignmentSignatureEmail(id) {
  try {
    const { absoluteUrl } = await ensureAssignmentSignatureLink(id);
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    const emailContent = buildAssignmentSignatureEmailContent(draft, absoluteUrl);
    const title = draft?.title || id;
    const fileName = `${sanitizeDownloadFileName(`attribution_signature_${title}`, "attribution_signature")}.eml`;
    saveBlob(new Blob([emailContent], { type: "message/rfc822;charset=utf-8" }), fileName);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail de signature.");
  }
}

async function copyRestitutionSignatureLink(id) {
  try {
    const { absoluteUrl } = await ensureRestitutionSignatureLink(id);
    const copied = await copyTextWithFallback(absoluteUrl, "Copiez ce lien de signature de restitution :");
    window.alert(copied ? "Lien de signature de restitution copié dans le presse-papiers." : "Lien de signature de restitution prêt à être copié.");
  } catch (error) {
    window.alert(error.message || "Impossible de préparer le lien de restitution.");
  }
}

async function prepareRestitutionSignatureEmail(id) {
  try {
    const { absoluteUrl } = await ensureRestitutionSignatureLink(id);
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    const emailContent = buildRestitutionEmailContent(draft, absoluteUrl);
    const title = draft?.title || id;
    const fileName = `${sanitizeDownloadFileName(`restitution_email_${title}`, "restitution_email")}.eml`;
    saveBlob(new Blob([emailContent], { type: "message/rfc822;charset=utf-8" }), fileName);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail de restitution.");
  }
}

function bindSignatureLinkNotice() {
  const notice = document.getElementById("signatureLinkNotice");
  if (!notice) {
    return;
  }
  const copyButton = notice.querySelector("[data-signature-link-copy]");
  if (copyButton && !copyButton.dataset.boundCopyLink) {
    copyButton.addEventListener("click", async () => {
      const link = copyButton.dataset.link || "";
      if (!link) {
        return;
      }
      try {
        await navigator.clipboard.writeText(link);
        window.alert("Lien copié.");
      } catch (error) {
        window.prompt("Copiez ce lien :", link);
      }
    });
    copyButton.dataset.boundCopyLink = "true";
  }
  const dismissButton = notice.querySelector("[data-signature-link-dismiss]");
  if (dismissButton && !dismissButton.dataset.boundDismissLink) {
    dismissButton.addEventListener("click", () => {
      persistDashboardSignatureLinkNotice(null);
      renderDashboardSignatureLinkNotice();
    });
    dismissButton.dataset.boundDismissLink = "true";
  }
  const revokeButton = notice.querySelector("[data-signature-link-revoke]");
  if (revokeButton && !revokeButton.dataset.boundRevokeLink) {
    revokeButton.addEventListener("click", async () => {
      const linkId = revokeButton.dataset.linkId || "";
      if (!linkId) {
        return;
      }
      if (!window.confirm("Révoquer ce lien de signature ?")) {
        return;
      }
      try {
        await requestJson(`/api/signature-links/${encodeURIComponent(linkId)}`, {
          method: "DELETE"
        });
        persistDashboardSignatureLinkNotice(null);
        renderDashboardSignatureLinkNotice();
        window.alert("Lien révoqué.");
      } catch (error) {
        window.alert(error.message || "Impossible de révoquer ce lien.");
      }
    });
    revokeButton.dataset.boundRevokeLink = "true";
  }
}

function renderDashboardSignatureLinkNotice() {
  const notice = document.getElementById("signatureLinkNotice");
  if (!notice) {
    return;
  }

  const payload = loadDashboardSignatureLinkNotice();
  if (!payload?.url) {
    notice.classList.add("d-none");
    notice.innerHTML = "";
    return;
  }

  const label = payload.kind === "restitution" ? "Lien de signature de restitution prêt" : "Lien de signature prêt";
  const canRevoke = Boolean(
    payload.linkId
    && (
      sessionInfo?.permissions?.includes("*")
      || sessionInfo?.permissions?.includes(payload.kind === "restitution" ? "forms.restitution" : "forms.edit")
    )
  );
  notice.innerHTML = `
    <div class="dashboard-update-notice__content">
      <div>
        <div>${escapeHtml(label)}</div>
        <div class="panel-text mb-0">${escapeHtml(payload.title || "")}</div>
        <div class="panel-text mb-0"><a href="${escapeHtml(payload.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(payload.url)}</a></div>
      </div>
      <div class="d-flex gap-2 flex-wrap">
        <button type="button" class="btn btn-sm btn-outline-primary" data-signature-link-copy data-link="${escapeHtml(payload.url)}">Copier le lien</button>
        ${canRevoke ? `<button type="button" class="btn btn-sm btn-outline-danger" data-signature-link-revoke data-link-id="${escapeHtml(payload.linkId)}">Révoquer</button>` : ""}
        <button type="button" class="btn btn-sm btn-outline-secondary" data-signature-link-dismiss>Masquer</button>
      </div>
    </div>
  `;
  notice.classList.remove("d-none");
  bindSignatureLinkNotice();
}

function setExportLoaderProgress(value) {
  const normalized = Math.max(0, Math.min(100, Math.round(value)));
  exportProgressValue = normalized;
  const bar = document.getElementById("exportLoaderBar");
  const percent = document.getElementById("exportLoaderPercent");
  if (bar) {
    bar.style.width = `${normalized}%`;
  }
  if (percent) {
    percent.textContent = `${normalized} %`;
  }
}

function showExportLoader(title, text) {
  const overlay = document.getElementById("exportLoader");
  document.getElementById("exportLoaderTitle").textContent = title;
  document.getElementById("exportLoaderText").textContent = text;
  startFallbackExportProgress({ start: 4, cap: 28, step: 3, interval: 220 });
  overlay?.classList.remove("is-hidden");
}

function hideExportLoader() {
  if (exportProgressFallbackTimer) {
    window.clearInterval(exportProgressFallbackTimer);
    exportProgressFallbackTimer = null;
  }
  exportProgressValue = 0;
  document.getElementById("exportLoader")?.classList.add("is-hidden");
}

function startFallbackExportProgress(options = {}) {
  if (exportProgressFallbackTimer) {
    window.clearInterval(exportProgressFallbackTimer);
  }
  const start = Number(options.start ?? Math.max(exportProgressValue, 8));
  const cap = Number(options.cap ?? 90);
  const step = Number(options.step ?? 6);
  const interval = Number(options.interval ?? 350);
  let value = start;
  setExportLoaderProgress(value);
  exportProgressFallbackTimer = window.setInterval(() => {
    value = Math.min(value + step, cap);
    setExportLoaderProgress(value);
  }, interval);
}

async function fetchDownloadWithProgress(url, options = {}) {
  // Pipeline de téléchargement en deux temps :
  // 1. une progression simulée pendant la préparation serveur
  // 2. une progression réelle dès que le flux HTTP devient lisible.
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const contentLength = Number(response.headers.get("Content-Length") || 0);
  if (!response.body || !contentLength) {
    startFallbackExportProgress({
      start: Math.max(exportProgressValue, 32),
      cap: 94,
      step: 4,
      interval: 260
    });
    const blob = await response.blob();
    setExportLoaderProgress(100);
    return { response, blob };
  }

  if (exportProgressFallbackTimer) {
    window.clearInterval(exportProgressFallbackTimer);
    exportProgressFallbackTimer = null;
  }

  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    chunks.push(value);
    received += value.length;
    const downloadProgress = 35 + ((received / contentLength) * 65);
    setExportLoaderProgress(Math.max(exportProgressValue, downloadProgress));
  }

  const blob = new Blob(chunks, { type: response.headers.get("Content-Type") || "application/octet-stream" });
  setExportLoaderProgress(100);
  return { response, blob };
}

function getSelectedDraftIds() {
  return Array.from(document.querySelectorAll(".draft-select:checked")).map((input) => input.value);
}

function captureDashboardSelection() {
  dashboardSelectedIds = new Set(getSelectedDraftIds());
}

function restoreDashboardSelection() {
  const visibleIds = new Set(
    Array.from(document.querySelectorAll(".draft-select")).map((input) => input.value)
  );
  dashboardSelectedIds = new Set(
    [...dashboardSelectedIds].filter((id) => visibleIds.has(id))
  );

  document.querySelectorAll(".draft-select").forEach((input) => {
    input.checked = dashboardSelectedIds.has(input.value);
  });

  const selectAll = document.getElementById("selectAllDrafts");
  if (selectAll) {
    const all = document.querySelectorAll(".draft-select");
    const checked = document.querySelectorAll(".draft-select:checked");
    selectAll.checked = all.length > 0 && all.length === checked.length;
  }

  updateExportSelectedState();
}

function updateExportSelectedState() {
  const selectedCount = getSelectedDraftIds().length;
  const exportButton = document.getElementById("exportSelectedPdfBtn");
  const restitutionExportButton = document.getElementById("exportSelectedRestitutionPdfBtn");
  const deleteButton = document.getElementById("deleteSelectedBtn");

  if (exportButton) {
    exportButton.disabled = selectedCount === 0;
    exportButton.textContent = selectedCount > 1 ? `PDF de ${selectedCount} dossiers` : "PDF dossier sélectionné";
  }

  if (restitutionExportButton) {
    restitutionExportButton.disabled = selectedCount === 0;
    restitutionExportButton.textContent = selectedCount > 1 ? `PDF de ${selectedCount} restitutions` : "PDF restitution sélectionnée";
  }

  if (deleteButton) {
    deleteButton.disabled = selectedCount === 0;
    deleteButton.textContent = selectedCount > 1 ? `Supprimer ${selectedCount} dossiers` : "Supprimer la sélection";
  }
}

async function exportSelectedPdfs() {
  // Export groupe :
  // - 1 fiche => PDF direct
  // - plusieurs fiches => ZIP de PDF
  const ids = getSelectedDraftIds();
  if (ids.length === 0) {
    alert("Sélectionnez au moins une fiche à exporter.");
    return;
  }

  if (ids.length === 1) {
    await exportDraftPdf(ids[0]);
    return;
  }

  showExportLoader("Préparation des PDF dossier", "Les documents du lot sont en cours de génération et de compression.");
  try {
    const { response, blob } = await fetchDownloadWithProgress(PDF_BATCH_EXPORT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({ ids })
    });

    const disposition = response.headers.get("Content-Disposition") || "";
    const fileNameMatch = disposition.match(/filename="([^"]+)"/i);
    const fileName = fileNameMatch ? fileNameMatch[1] : "dossiers_attribution_pdf.zip";
    saveBlob(blob, fileName);
  } catch (error) {
    alert("Impossible de générer le ZIP des PDF dossier.");
  } finally {
    window.setTimeout(() => {
      hideExportLoader();
    }, 250);
  }
}

async function exportSelectedRestitutionPdfs() {
  const ids = getSelectedDraftIds();
  if (ids.length === 0) {
    alert("Sélectionnez au moins un dossier à exporter.");
    return;
  }

  if (ids.length === 1) {
    await exportRestitutionPdf(ids[0]);
    return;
  }

  showExportLoader("Préparation des PDF restitution", "Les bons de restitution sont en cours de génération et de compression.");
  try {
    const { response, blob } = await fetchDownloadWithProgress(RESTITUTION_PDF_BATCH_EXPORT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({ ids })
    });

    const disposition = response.headers.get("Content-Disposition") || "";
    const fileNameMatch = disposition.match(/filename="([^"]+)"/i);
    const fileName = fileNameMatch ? fileNameMatch[1] : "restitutions_pdf.zip";
    saveBlob(blob, fileName);
  } catch (error) {
    alert("Impossible de générer le ZIP des PDF restitution.");
  } finally {
    window.setTimeout(() => {
      hideExportLoader();
    }, 250);
  }
}

async function deleteSelectedDrafts() {
  const ids = getSelectedDraftIds();
  if (ids.length === 0) {
    alert("Sélectionnez au moins un dossier à supprimer.");
    return;
  }

  const confirmed = window.confirm(
    ids.length > 1
      ? `Supprimer définitivement les ${ids.length} dossiers sélectionnés ?`
      : "Supprimer définitivement le dossier sélectionné ?"
  );
  if (!confirmed) {
    return;
  }

  for (const id of ids) {
    await deleteDraft(id);
  }
  await renderDraftList();
}

function bindSelectionActions(canExport, canDelete) {
  // Branche le "tout sélectionner" et les actions groupées.
  const exportButton = document.getElementById("exportSelectedPdfBtn");
  const restitutionExportButton = document.getElementById("exportSelectedRestitutionPdfBtn");
  const deleteButton = document.getElementById("deleteSelectedBtn");
  const selectAll = document.getElementById("selectAllDrafts");
  const canSelect = canExport || canDelete;

  if (exportButton) {
    exportButton.classList.toggle("d-none", !canExport);
    exportButton.disabled = true;
    if (!exportButton.dataset.boundExportSelection) {
      exportButton.addEventListener("click", () => {
        void exportSelectedPdfs();
      });
      exportButton.dataset.boundExportSelection = "true";
    }
  }

  if (restitutionExportButton) {
    restitutionExportButton.classList.toggle("d-none", !canExport);
    restitutionExportButton.disabled = true;
    if (!restitutionExportButton.dataset.boundExportRestitutionSelection) {
      restitutionExportButton.addEventListener("click", () => {
        void exportSelectedRestitutionPdfs();
      });
      restitutionExportButton.dataset.boundExportRestitutionSelection = "true";
    }
  }

  if (deleteButton) {
    deleteButton.classList.toggle("d-none", !canDelete);
    deleteButton.disabled = true;
    if (!deleteButton.dataset.boundDeleteSelection) {
      deleteButton.addEventListener("click", () => {
        void deleteSelectedDrafts();
      });
      deleteButton.dataset.boundDeleteSelection = "true";
    }
  }

  if (selectAll) {
    selectAll.disabled = !canSelect;
    if (!selectAll.dataset.boundSelectAll) {
      selectAll.addEventListener("change", () => {
        document.querySelectorAll(".draft-select").forEach((input) => {
          input.checked = selectAll.checked;
        });
        captureDashboardSelection();
        updateExportSelectedState();
      });
      selectAll.dataset.boundSelectAll = "true";
    }
  }

  document.querySelectorAll(".draft-select").forEach((input) => {
    if (input.dataset.boundSelect) {
      return;
    }
    input.addEventListener("change", () => {
      captureDashboardSelection();
      if (selectAll) {
        const all = document.querySelectorAll(".draft-select");
        const checked = document.querySelectorAll(".draft-select:checked");
        selectAll.checked = all.length > 0 && all.length === checked.length;
      }
      updateExportSelectedState();
    });
    input.dataset.boundSelect = "true";
  });
}

async function removeDraft(id) {
  const item = await getDraftById(id);
  if (!item) {
    return;
  }

  const confirmed = window.confirm(`Supprimer le dossier "${item.summary.title}" `);
  if (!confirmed) {
    return;
  }

  await deleteDraft(id);
  await renderDraftList();
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function getHoverCard() {
  return document.getElementById("statusHoverCard");
}

function hideStatusPreview() {
  const card = getHoverCard();
  if (!card) {
    return;
  }
  card.classList.add("d-none");
}

function positionHoverCard(card, target) {
  const rect = target.getBoundingClientRect();
  const top = Math.min(window.innerHeight - card.offsetHeight - 12, rect.bottom + 10);
  const left = Math.min(window.innerWidth - card.offsetWidth - 12, rect.left);
  card.style.top = `${Math.max(12, top)}px`;
  card.style.left = `${Math.max(12, left)}px`;
}

async function showStatusPreview(target, id) {
  const card = getHoverCard();
  if (!card) {
    return;
  }

  card.innerHTML = '<p class="status-hover-card__hint">Chargement des ressources...</p>';
  card.classList.remove("d-none");
  positionHoverCard(card, target);

  const result = await getDraftById(id);
  if (!result || !result.data) {
    card.innerHTML = '<p class="status-hover-card__hint">Impossible de charger le détail.</p>';
    positionHoverCard(card, target);
    return;
  }
  const previewItems = buildDotationPreview(result.data);
  card.innerHTML = previewItems.length
    ? `<h4>Ressources attribuées</h4><ul>${previewItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : '<p class="status-hover-card__hint">Aucune ressource renseignée.</p>';
  positionHoverCard(card, target);
}

function bindStatusPreviews() {
  // Le hover charge à la demande le détail d'une fiche pour éviter d'alourdir la liste initiale.
  document.querySelectorAll("[data-status-preview-id]").forEach((chip) => {
    if (chip.dataset.previewBound) {
      return;
    }
    chip.addEventListener("mouseenter", () => {
      void showStatusPreview(chip, chip.dataset.statusPreviewId);
    });
    chip.addEventListener("mouseleave", hideStatusPreview);
    chip.dataset.previewBound = "true";
  });
}

function bindDashboardFilters() {
  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  const timingFilter = document.getElementById("timingFilter");
  const qualiteFilter = document.getElementById("qualiteFilter");
  const serviceFilter = document.getElementById("serviceFilter");
  const resetButton = document.getElementById("resetFiltersBtn");

  if (!searchInput || !statusFilter || !timingFilter || !qualiteFilter || !serviceFilter || !resetButton) {
    return;
  }

  searchInput.addEventListener("input", (event) => {
    dashboardFilters.search = event.target.value.trim();
    void renderDraftList();
  });

  statusFilter.addEventListener("change", (event) => {
    dashboardFilters.status = event.target.value;
    void renderDraftList();
  });

  timingFilter.addEventListener("change", (event) => {
    dashboardFilters.timing = event.target.value;
    void renderDraftList();
  });

  qualiteFilter.addEventListener("change", (event) => {
    dashboardFilters.qualite = event.target.value;
    void renderDraftList();
  });

  serviceFilter.addEventListener("change", (event) => {
    dashboardFilters.service = event.target.value;
    void renderDraftList();
  });

  resetButton.addEventListener("click", () => {
    dashboardFilters.search = "";
    dashboardFilters.status = "";
    dashboardFilters.timing = "";
    dashboardFilters.qualite = "";
    dashboardFilters.service = "";
    if (searchInput) {
      searchInput.value = "";
    }
    if (statusFilter) {
      statusFilter.value = "";
    }
    if (timingFilter) {
      timingFilter.value = "";
    }
    if (qualiteFilter) {
      qualiteFilter.value = "";
    }
    if (serviceFilter) {
      serviceFilter.value = "";
    }
    void renderDraftList();
  });
}

function updateDashboardRefreshInfo() {
  const info = document.getElementById("dashboardRefreshInfo");
  if (!info) {
    return;
  }
  if (!dashboardLastUpdatedAt) {
    info.textContent = "Mise à jour automatique active.";
    return;
  }
  const formatted = new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(dashboardLastUpdatedAt));
  info.textContent = `Mise à jour automatique active. Dernière actualisation : ${formatted}.`;
}

function acknowledgeDashboardUpdates() {
  dashboardPendingNewIds = new Set();
  persistPendingDashboardUpdates();
  setDashboardUpdateNotice();
  document.querySelectorAll(".draft-row--new").forEach((row) => {
    row.classList.remove("draft-row--new");
  });
}

function bindDashboardUpdateNotice() {
  const notice = document.getElementById("dashboardUpdateNotice");
  if (!notice) {
    return;
  }
  const button = notice.querySelector("[data-dashboard-ack]");
  if (!button || button.dataset.boundAck) {
    return;
  }
  button.addEventListener("click", acknowledgeDashboardUpdates);
  button.dataset.boundAck = "true";
}

function updateDashboardPendingBadge() {
  const badge = document.getElementById("dashboardPendingBadge");
  if (!badge) {
    return;
  }

  const pendingCount = dashboardPendingNewIds.size;
  if (pendingCount === 0) {
    badge.textContent = "";
    badge.classList.add("d-none");
    return;
  }

  badge.textContent = pendingCount > 1 ? `${pendingCount} nouveaux` : "1 nouveau";
  badge.classList.remove("d-none");
}

function setDashboardUpdateNotice() {
  const notice = document.getElementById("dashboardUpdateNotice");
  if (!notice) {
    return;
  }

  const pendingCount = dashboardPendingNewIds.size;
  updateDashboardPendingBadge();

  if (pendingCount === 0) {
    persistPendingDashboardUpdates();
    notice.innerHTML = "";
    notice.classList.add("d-none");
    notice.classList.remove("is-highlighted");
    return;
  }

  const message = pendingCount > 1
    ? `${pendingCount} nouveaux dossiers ont été détectés.`
    : "1 nouveau dossier a été détecté.";

  notice.innerHTML = `
    <div class="dashboard-update-notice__content">
      <span>${escapeHtml(message)}</span>
      <button type="button" class="btn btn-sm btn-outline-primary" data-dashboard-ack>J'ai vu</button>
    </div>
  `;
  notice.classList.remove("d-none");
  notice.classList.remove("is-highlighted");
  void notice.offsetWidth;
  notice.classList.add("is-highlighted");
  bindDashboardUpdateNotice();
}

function refreshDashboardIfVisible() {
  if (document.hidden) {
    return;
  }
  void renderDraftList();
}

function startDashboardAutoRefresh() {
  if (dashboardRefreshTimer) {
    window.clearInterval(dashboardRefreshTimer);
  }
  dashboardRefreshTimer = window.setInterval(() => {
    refreshDashboardIfVisible();
  }, DASHBOARD_REFRESH_INTERVAL_MS);
}

document.addEventListener("DOMContentLoaded", () => {
  // Initialisation d'accueil : session, liste et masquage du hover au scroll.
  if (!document.getElementById("draftList")) {
    return;
  }
  dashboardPendingNewIds = loadPendingDashboardUpdates();
  renderDashboardSignatureLinkNotice();
  void getSessionInfo().then((user) => {
    if (user && (user.permissions.includes("users.manage") || user.permissions.includes("*"))) {
      document.getElementById("adminLink").classList.remove("d-none");
    }
    if (user && (user.permissions.includes("forms.export") || user.permissions.includes("*"))) {
      document.getElementById("backupExportLink").classList.remove("d-none");
    }
    if (user && (user.permissions.includes("forms.create") || user.permissions.includes("*"))) {
      document.getElementById("newFormBtn")?.classList.remove("d-none");
      document.getElementById("emptyStateNewFormBtn")?.classList.remove("d-none");
    }
    renderDashboardSignatureLinkNotice();
  });
  bindDashboardFilters();
  void renderDraftList();
  startDashboardAutoRefresh();
  document.getElementById("refreshDashboardBtn")?.addEventListener("click", () => {
    refreshDashboardIfVisible();
  });
  document.addEventListener("visibilitychange", refreshDashboardIfVisible);
  window.addEventListener("focus", refreshDashboardIfVisible);
  document.addEventListener("scroll", hideStatusPreview, { passive: true });
});

// Module du tableau de bord :
// listes, actions de lot, exports et caches de secours.
