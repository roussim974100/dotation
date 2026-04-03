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
  service: "",
  sort: "recent"
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
    if (!raw) {
      return null;
    }
    const payload = JSON.parse(raw);
    if (payload?.kind === "restitution") {
      sessionStorage.removeItem(DASHBOARD_SIGNATURE_LINK_NOTICE_KEY);
      return null;
    }
    return payload;
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
    pendingFinalization: Boolean(payload.restitution?.pendingFinalization),
    completedResources: progress.completed,
    totalResources: progress.total,
    resourceProgressRatio: progress.ratio,
    timingStatus: progress.timingStatus,
    timingLabel: progress.timingLabel
  };
}

function usesDynamicResourceAssignmentDate(resource) {
  if (resource && (Object.prototype.hasOwnProperty.call(resource, "hasAssignmentDate") || Object.prototype.hasOwnProperty.call(resource, "has_assignment_date"))) {
    return Boolean(resource.hasAssignmentDate ?? resource.has_assignment_date);
  }
  return true;
}

function summarizeDynamicResource(resource) {
  const fields = resource?.fields || {};
  const values = Object.values(fields).map((value) => String(value || "").trim()).filter(Boolean);
  if (values.length) {
    return values.join(" - ");
  }
  return String(resource?.details || "").trim();
}

function isDynamicResourceComplete(resource) {
  if (!resource?.selected) {
    return false;
  }
  const fieldSchema = Array.isArray(resource.fieldSchema)
    ? resource.fieldSchema
    : (Array.isArray(resource.field_schema) ? resource.field_schema : []);
  const fieldValues = resource.fields || {};
  if (fieldSchema.length) {
    const hasMissingRequiredField = fieldSchema.some((field) => field.required && !String(fieldValues[field.key] || "").trim());
    if (hasMissingRequiredField) {
      return false;
    }
  } else if (!summarizeDynamicResource(resource)) {
    return false;
  }
  if (usesDynamicResourceAssignmentDate(resource) && !String(resource.assignedAt || "").trim()) {
    return false;
  }
  return true;
}

function collectRequestedResourcesFromPayload(payload) {
  const resources = [];
  const pushIfSelected = (item, key) => {
    if (item?.selected) {
      resources.push({ key, isCompleted: Boolean(item.assignedAt) });
    }
  };

  const materiel = payload?.materiel || {};
  const immateriel = payload?.immateriel || {};
  Object.entries(materiel).forEach(([key, item]) => pushIfSelected(item, key));
  Object.entries(immateriel).forEach(([key, item]) => pushIfSelected(item, key));
  (payload?.resources?.additional || []).forEach((resource) => {
    if (resource?.selected) {
      resources.push({
        key: resource.id || resource.code || "resource",
        isCompleted: isDynamicResourceComplete(resource)
      });
    }
  });
  return resources;
}

function summarizeDraftProgressFromPayload(payload = {}) {
  const requested = collectRequestedResourcesFromPayload(payload);
  const total = requested.length;
  const completed = requested.filter((resource) => resource.isCompleted).length;
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

function getTimingOffsetLabel(startAt) {
  if (!startAt) {
    return "";
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(startAt) ? `${startAt}T00:00:00` : startAt;
  const startDate = new Date(normalized);
  if (Number.isNaN(startDate.getTime())) {
    return "";
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  startDate.setHours(0, 0, 0, 0);
  const dayDelta = Math.round((startDate - today) / 86400000);
  if (dayDelta === 0) {
    return "Échéance aujourd'hui";
  }
  if (dayDelta > 0) {
    return `${dayDelta} j d'avance`;
  }
  return `${Math.abs(dayDelta)} j de retard`;
}

function buildDashboardRow(draft, permissions) {
  const progress = getDraftProgressMetrics(draft);
  const progressPercent = Math.max(0, Math.min(100, Math.round((progress.ratio || 0) * 100)));
  const title = draft.title || (draft.data ? buildDraftTitle(draft.data) : "Dossier");
  const dossierTypeLabel = formatDossierTypeLabel(draft.dossierType || draft.data?.dossier?.type || "");
  const timingOffsetLabel = getDashboardViewMode() === "history_assignments"
    ? getTimingOffsetLabel(draft.startAt)
    : "";
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
      <td data-label="État">${escapeHtml(formatQualiteLabel(draft))}</td>
      <td data-label="Avancement"><span class="status-chip status-chip--${escapeHtml(draft.status || "draft")}" data-status-preview-id="${draft.id}">${escapeHtml(formatDraftStatusLabel(draft))}</span></td>
      <td data-label="Pilotage">
        <span class="timing-chip timing-chip--${escapeHtml(progress.timingStatus)}" data-timing-preview-id="${draft.id}">${escapeHtml(progress.timingLabel)}</span>
        ${timingOffsetLabel ? `<div class="draft-meta draft-meta--timing">${escapeHtml(timingOffsetLabel)}</div>` : ""}
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
    return "Élu(e)";
  }
  if (qualite === "agent") {
    return "Agent";
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

function formatDraftStatusLabel(draft) {
  if (draft?.pendingFinalization && (draft.status || "draft") === "partial_return") {
    return "En attente de finalisation";
  }
  return formatStatusLabel(draft?.status || "draft");
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

function isOperationalAssignmentDraft(draft) {
  return !isRestitutionDashboardDraft(draft)
    && ["draft", "partial_assignment", "awaiting_signature"].includes(draft.status || "draft");
}

function isOperationalRestitutionDraft(draft) {
  return hasRestitutionData(draft)
    && ["active", "partial_return", "awaiting_signature"].includes(draft.status || "draft");
}

function isCompletedAssignmentDraft(draft) {
  return !hasRestitutionData(draft) && (draft.status || "draft") === "active";
}

function isCompletedRestitutionDraft(draft) {
  return (draft.status || "draft") === "returned";
}

function getDashboardViewMode() {
  return document.body?.dataset?.dashboardView || "active";
}

function sortDraftsForDisplay(drafts) {
  const sorted = [...drafts];
  sorted.sort((left, right) => {
    const leftDate = new Date(left.updatedAt || left.assignedAt || 0).getTime();
    const rightDate = new Date(right.updatedAt || right.assignedAt || 0).getTime();
    if (dashboardFilters.sort === "oldest") {
      return leftDate - rightDate;
    }
    return rightDate - leftDate;
  });
  return sorted;
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
  }
  if (options.canExport && hasRestitutionData(draft)) {
    pdfActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="exportRestitutionPdf('${draft.id}')">Télécharger le PDF restitution</button>`);
  }

  const signatureActions = [];
  if (canRequestAssignmentSignature(draft, options)) {
    signatureActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="shareSignatureLink('${draft.id}')">Copier le lien de signature</button>`);
  }

  if (canRequestRestitutionSignature(draft, options)) {
    signatureActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="copyRestitutionSignatureLink('${draft.id}')">Copier le lien de signature</button>`);
  }

  const emailActions = [];
  emailActions.push(`<button class="btn btn-sm btn-outline-primary" type="button" onclick="prepareAssignmentInfoEmail('${draft.id}')">Informer de la création du dossier</button>`);
  if (hasRestitutionData(draft) || ["active", "partial_return", "awaiting_signature", "returned"].includes(draft.status || "draft")) {
    emailActions.push(`<button class="btn btn-sm btn-outline-primary" type="button" onclick="prepareRestitutionInfoEmail('${draft.id}')">Informer de la restitution</button>`);
  }
  if (options.canExport) {
    emailActions.push(`<button class="btn btn-sm btn-outline-success" type="button" onclick="prepareDraftPdfEmail('${draft.id}')">Envoyer le PDF dossier</button>`);
  }
  if (options.canExport && hasRestitutionData(draft)) {
    emailActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="prepareRestitutionPdfEmail('${draft.id}')">Envoyer le PDF restitution</button>`);
  }
  if (canRequestAssignmentSignature(draft, options)) {
    emailActions.push(`<button class="btn btn-sm btn-outline-info" type="button" onclick="prepareAssignmentSignatureEmail('${draft.id}')">Envoyer le lien de signature du dossier</button>`);
  }
  if (canRequestRestitutionSignature(draft, options)) {
    emailActions.push(`<button class="btn btn-sm btn-outline-info" type="button" onclick="prepareRestitutionSignatureEmail('${draft.id}')">Envoyer le lien de signature de restitution</button>`);
  }

  const managementActions = [];
  if (options.canDelete) {
    managementActions.push(`<button class="btn btn-sm btn-outline-danger" type="button" onclick="removeDraft('${draft.id}')">Supprimer le dossier</button>`);
  }

  return `
    <div class="draft-actions__primary">
      ${renderDraftActionMenu("Ouvrir", "btn-outline-primary", [openActions.join("")])}
      ${renderDraftActionMenu("PDF", "btn-outline-success", [pdfActions.join("")])}
      ${renderDraftActionMenu("E-mail", "btn-outline-primary", [emailActions.join("")])}
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
    formatDraftStatusLabel(draft),
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

function filterDraftsForCurrentView(drafts) {
  const viewMode = getDashboardViewMode();

  if (viewMode === "history_assignments") {
    return drafts.filter((draft) => isCompletedAssignmentDraft(draft));
  }

  if (viewMode === "history_restitutions") {
    return drafts.filter((draft) => isCompletedRestitutionDraft(draft));
  }

  return drafts.filter((draft) => isOperationalAssignmentDraft(draft) || isOperationalRestitutionDraft(draft));
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
  const pushItem = (label, detail) => {
    items.push(detail ? `${label} : ${detail}` : label);
  };

  // Ressources dynamiques (nouveau format)
  for (const resource of data.resources?.additional || []) {
    if (!resource.selected) continue;
    const fields = resource.fields || {};
    const fieldValues = Object.values(fields).map((v) => Array.isArray(v) ? v.join(", ") : String(v || "")).filter(Boolean);
    pushItem(resource.label || "Ressource", resource.details || fieldValues.join(" - "));
  }

  // Fallback pour les anciens dossiers avec materiel/immateriel hardcodé
  if (!items.length) {
    const materiel = data.materiel || {};
    const immateriel = data.immateriel || {};
    for (const [, item] of Object.entries(materiel)) {
      if (item?.selected) pushItem(item.label || "Matériel", item.details || "");
    }
    for (const [, item] of Object.entries(immateriel)) {
      if (item?.selected) pushItem(item.label || "Immatériel", item.details || "");
    }
  }

  // Accès UNC
  const uncAcces = data.unc_acces || [];
  if (uncAcces.length) {
    const uncDetails = uncAcces.map((unc) => unc.chemin || "").filter(Boolean);
    pushItem(`Accès UNC (${uncAcces.length})`, uncDetails.join(", "));
  }

  return items;
}

function buildMissingProgressPreview(data) {
  if (!data) {
    return [];
  }

  const missing = [];
  const workflowStatus = data.workflow?.status || "draft";
  const beneficiaire = data.beneficiaire || {};
  const validation = data.validation || {};
  const resourceErrors = Array.isArray(data.meta?.resourceValidationErrors)
    ? data.meta.resourceValidationErrors.filter(Boolean)
    : [];

  if (!beneficiaire.nom) {
    missing.push("Nom");
  }
  if (!beneficiaire.prenom) {
    missing.push("Prénom");
  }
  if ((beneficiaire.qualite || "agent") === "elu") {
    if (!beneficiaire.mandat) {
      missing.push("Mandat");
    }
  } else if (!beneficiaire.service) {
    missing.push("Service");
  }

  if (!validation.rgpdAccepted) {
    missing.push("Validation RGPD");
  }

  if (!validation.signatureDataUrl && ["draft", "partial_assignment", "awaiting_signature"].includes(workflowStatus)) {
    missing.push("Signature du dossier");
  }

  return [...new Set([...resourceErrors, ...missing])];
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
  const {
    headers = {},
    timeoutMs = 15000,
    signal,
    ...fetchOptions
  } = options;
  const controller = !signal && typeof AbortController !== "undefined" ? new AbortController() : null;
  const activeSignal = signal || controller?.signal;
  let timeoutId = null;

  if (controller && Number.isFinite(timeoutMs) && timeoutMs > 0) {
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }

  let response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...headers
      },
      credentials: "same-origin",
      signal: activeSignal,
      ...fetchOptions
    });
  } catch (error) {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
    if (error?.name === "AbortError") {
      const timeoutError = new Error("Le serveur ne répond pas.");
      timeoutError.status = 0;
      timeoutError.code = "request_timeout";
      throw timeoutError;
    }
    throw error;
  }

  if (timeoutId) {
    window.clearTimeout(timeoutId);
  }

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = payload?.error || `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
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

async function listForms() {
  try {
    const items = await requestJson(API_BASE);
    const summaries = Array.isArray(items) ? items : [];
    const cachedById = new Map(getCachedDrafts().map((draft) => [draft.id, draft]));
    const merged = summaries.map((summary) => ({
      ...(cachedById.get(summary.id) || {}),
      ...summary
    }));
    setCachedDrafts(merged);
    return merged;
  } catch (error) {
    return getCachedDrafts();
  }
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
  // Le rendu est partagé entre :
  // - le tableau de bord opérationnel
  // - l'historique des dossiers terminés
  // - l'historique des restitutions terminées
  const draftList = document.getElementById("draftList");
  const restitutionList = document.getElementById("restitutionList");
  const historyList = document.getElementById("historyList");
  const assignmentDraftCount = document.getElementById("assignmentDraftCount");
  const restitutionDraftCount = document.getElementById("restitutionDraftCount");
  const historyCountValue = document.getElementById("historyCountValue");
  const emptyState = document.getElementById("emptyState");
  const assignmentEmptyState = document.getElementById("assignmentEmptyState");
  const restitutionEmptyState = document.getElementById("restitutionEmptyState");
  const assignmentCountBadge = document.getElementById("assignmentCountBadge");
  const restitutionCountBadge = document.getElementById("restitutionCountBadge");
  const historyCountBadge = document.getElementById("historyCountBadge");
  const historyEmptyState = document.getElementById("historyEmptyState");
  const viewMode = getDashboardViewMode();

  if (!draftList && !restitutionList && !historyList) {
    dashboardRefreshInFlight = false;
    return;
  }

  try {
    captureDashboardSelection();
    const drafts = await listForms();
    const sortedDrafts = sortDraftsForDisplay(drafts);
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
    const filteredDrafts = filterDraftsForCurrentView(applyDashboardFilters(sortedDrafts));
    const assignmentDrafts = filteredDrafts.filter((draft) => isOperationalAssignmentDraft(draft));
    const restitutionDrafts = filteredDrafts.filter((draft) => isOperationalRestitutionDraft(draft));
    const historyDrafts = filteredDrafts;
    const completableAssignmentDrafts = sortedDrafts.filter((draft) => isOperationalAssignmentDraft(draft));
    const completableRestitutionDrafts = sortedDrafts.filter((draft) => isOperationalRestitutionDraft(draft));

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
    if (historyCountValue) {
      historyCountValue.textContent = historyDrafts.length.toString();
    }
    if (historyCountBadge) {
      historyCountBadge.textContent = historyDrafts.length.toString();
    }

    if (filteredDrafts.length === 0) {
      if (draftList) {
        draftList.innerHTML = "";
      }
      if (restitutionList) {
        restitutionList.innerHTML = "";
      }
      if (historyList) {
        historyList.innerHTML = "";
      }
      dashboardSelectedIds = new Set();
      emptyState?.classList.toggle("d-none", viewMode !== "active");
      assignmentEmptyState?.classList.add("d-none");
      restitutionEmptyState?.classList.add("d-none");
      historyEmptyState?.classList.toggle("d-none", viewMode === "active");
      updateDashboardRefreshInfo();
      setDashboardUpdateNotice();
      updateExportSelectedState();
      return;
    }

    emptyState?.classList.add("d-none");
    historyEmptyState?.classList.add("d-none");
    const user = await getSessionInfo();
    const canExport = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.export"));
    const canDelete = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.delete"));
    const canRestitution = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.restitution"));
    const canEdit = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.edit"));

    if (viewMode === "active") {
      if (draftList) {
        draftList.innerHTML = assignmentDrafts
          .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
          .join("");
      }
      if (restitutionList) {
        restitutionList.innerHTML = restitutionDrafts
          .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
          .join("");
      }
      assignmentEmptyState?.classList.toggle("d-none", assignmentDrafts.length > 0);
      restitutionEmptyState?.classList.toggle("d-none", restitutionDrafts.length > 0);
    } else if (historyList) {
      historyList.innerHTML = historyDrafts
        .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
        .join("");
      historyEmptyState?.classList.toggle("d-none", historyDrafts.length > 0);
    }

    dashboardLastUpdatedAt = new Date().toISOString();
    updateDashboardRefreshInfo();
    if (viewMode === "active") {
      setDashboardUpdateNotice();
    }
    bindStatusPreviews();
    bindTimingPreviews();
    bindDraftActionMenus();
    bindSelectionActions(viewMode === "active" && canExport, viewMode === "active" && canDelete);
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

function getDraftRecipientEmail(draft) {
  return getPdfEmailRecipient(draft);
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

function escapeHtmlForEmail(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderEmailLine(line) {
  const rawLine = String(line ?? "").trim();
  if (!rawLine) {
    return "";
  }
  if (/^https?:\/\/\S+$/i.test(rawLine)) {
    const safeUrl = escapeHtmlForEmail(rawLine);
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" style="color:#0f5b8d;font-weight:600;text-decoration:underline;word-break:break-word;">${safeUrl}</a>`;
  }
  return escapeHtmlForEmail(rawLine);
}

function renderEmailParagraphs(bodyLines = []) {
  return bodyLines
    .map((line) => String(line ?? ""))
    .reduce((blocks, line) => {
      if (!line.trim()) {
        blocks.push("");
        return blocks;
      }
      const safeLine = renderEmailLine(line);
      const lastIndex = blocks.length - 1;
      if (lastIndex >= 0 && blocks[lastIndex] !== "") {
        blocks[lastIndex] = `${blocks[lastIndex]}<br>${safeLine}`;
      } else {
        blocks.push(safeLine);
      }
      return blocks;
    }, [])
    .filter((block) => block !== "")
    .map((block) => `<p style="margin:0 0 14px;color:#233547;font-size:15px;line-height:1.65;">${block}</p>`)
    .join("");
}

async function buildHtmlEmailDocument({ title, eyebrow = "A quai", bodyLines, metaLines = [] }) {
  const metaHtml = metaLines.length
    ? `
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px;border-collapse:collapse;">
        ${metaLines.map((line) => `
          <tr>
            <td style="padding:0 0 6px;color:#5f7388;font-size:13px;line-height:1.5;">${escapeHtmlForEmail(line)}</td>
          </tr>
        `).join("")}
      </table>
    `
    : "";

  return `
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtmlForEmail(title)}</title>
</head>
<body style="margin:0;padding:24px 12px;background:#eef4f8;font-family:Segoe UI,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:720px;border-collapse:collapse;">
          <tr>
            <td style="padding:0 0 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                <tr>
                  <td style="color:#0f5b8d;font-size:13px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;">
                    ${escapeHtmlForEmail(eyebrow)}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;border:1px solid #d4dde6;border-radius:20px;padding:24px 28px;box-shadow:0 12px 26px rgba(15,55,84,.08);">
              <h1 style="margin:0 0 14px;color:#17344f;font-family:Georgia,'Times New Roman',serif;font-size:28px;line-height:1.2;">${escapeHtmlForEmail(title)}</h1>
              ${metaHtml}
              ${renderEmailParagraphs(bodyLines)}
            </td>
          </tr>
          <tr>
            <td style="padding:14px 8px 0;color:#607080;font-size:12px;line-height:1.6;">
              <p style="margin:0;">Message préparé depuis A quai, application interne de suivi des attributions et restitutions.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`.trim();
}
function buildRelatedHtmlEmailContent({ recipientEmail, subject, htmlBody }) {
  return [
    "X-Unsent: 1",
    `Subject: ${subject}`,
    `To: ${recipientEmail}`,
    "MIME-Version: 1.0",
    'Content-Type: text/html; charset="utf-8"',
    "Content-Transfer-Encoding: 8bit",
    "",
    htmlBody
  ].join("\r\n");
}

function buildPdfEmailContent({ recipientEmail, subject, bodyLines, htmlBody, attachmentName, attachmentBase64 }) {
  const boundary = `----=_Dotation_${Date.now().toString(16)}_${Math.random().toString(16).slice(2, 10)}`;
  return [
    "X-Unsent: 1",
    `Subject: ${subject}`,
    `To: ${recipientEmail}`,
    "MIME-Version: 1.0",
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    'Content-Type: text/html; charset="utf-8"',
    "Content-Transfer-Encoding: 8bit",
    "",
    htmlBody || renderEmailParagraphs(bodyLines),
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

async function saveSimpleEmailDraft({ recipientEmail, subject, title, bodyLines, metaLines = [] }, fileNameBase) {
  const emailContent = buildRelatedHtmlEmailContent({
    recipientEmail,
    subject,
    htmlBody: await buildHtmlEmailDocument({
      title,
      eyebrow: "A quai",
      metaLines,
      bodyLines
    })
  });
  const fileName = `${sanitizeDownloadFileName(fileNameBase, "email")}.eml`;
  saveBlob(new Blob([emailContent], { type: "message/rfc822;charset=utf-8" }), fileName);
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
    const bodyLines = [
      "Bonjour,",
      "",
      `Vous trouverez en pièce jointe le ${documentLabel.toLowerCase()}.`,
      `Dossier : ${title}`,
      fullName ? `Personne concernée : ${fullName}` : "",
      "",
      "Cordialement,"
    ].filter(Boolean);
    const emailContent = buildPdfEmailContent({
      recipientEmail,
      subject: `${documentLabel} - ${title}`,
      bodyLines,
      htmlBody: await buildHtmlEmailDocument({
        title: documentLabel,
        eyebrow: "A quai",
        metaLines: [title, fullName].filter(Boolean),
        bodyLines
      }),
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
  return {
    recipientEmail,
    subject: "Lien de signature de restitution",
    title: "Signature de restitution",
    metaLines: [title, fullName].filter(Boolean),
    bodyLines: [
      "Bonjour,",
      "",
      "Vous trouverez ci-dessous le lien pour consulter et signer la restitution :",
      absoluteUrl,
      "",
      `Dossier : ${title}`,
      fullName ? `Personne concernée : ${fullName}` : "",
      "",
      "Cordialement,"
    ].filter(Boolean)
  };
}

function buildAssignmentSignatureEmailContent(draft, absoluteUrl) {
  const title = draft?.title || "Dossier";
  const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
  const recipientEmail = getPdfEmailRecipient(draft);
  return {
    recipientEmail,
    subject: "Lien de signature du dossier d'attribution",
    title: "Signature du dossier",
    metaLines: [title, fullName].filter(Boolean),
    bodyLines: [
      "Bonjour,",
      "",
      "Vous trouverez ci-dessous le lien pour consulter et signer le dossier d'attribution :",
      absoluteUrl,
      "",
      `Dossier : ${title}`,
      fullName ? `Personne concernée : ${fullName}` : "",
      "",
      "Cordialement,"
    ].filter(Boolean)
  };
}

function buildAssignmentInfoEmailContent(draft) {
  const title = draft?.title || "Dossier";
  const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
  const recipientEmail = getDraftRecipientEmail(draft);
  const service = draft?.service || draft?.data?.beneficiaire?.service || "";
  const startAt = draft?.startAt ? formatShortDate(draft.startAt) : "";
  return {
    recipientEmail,
    subject: `Information sur votre dossier - ${title}`,
    title: "Nouveau dossier créé",
    metaLines: [title, fullName, service ? `Service : ${service}` : "", startAt ? `Prise de fonction : ${startAt}` : ""].filter(Boolean),
    bodyLines: [
      "Bonjour,",
      "",
      "Nous vous informons qu'un nouveau dossier de dotation a été créé pour préparer vos ressources et accès.",
      `Dossier : ${title}`,
      fullName ? `Personne concernée : ${fullName}` : "",
      service ? `Service : ${service}` : "",
      startAt ? `Date de prise de fonction : ${startAt}` : "",
      "",
      "Les services concernés poursuivent désormais le traitement de votre dossier.",
      "",
      "Cordialement,"
    ].filter(Boolean)
  };
}

function buildRestitutionInfoEmailContent(draft) {
  const title = draft?.title || "Dossier";
  const fullName = `${draft?.prenom || ""} ${draft?.nom || ""}`.trim();
  const recipientEmail = getDraftRecipientEmail(draft);
  const returnedAt = draft?.returnedAt ? formatShortDate(draft.returnedAt) : "";
  return {
    recipientEmail,
    subject: `Information sur votre restitution - ${title}`,
    title: "Restitution engagée",
    metaLines: [title, fullName, returnedAt ? `Date de restitution : ${returnedAt}` : ""].filter(Boolean),
    bodyLines: [
      "Bonjour,",
      "",
      "Nous vous informons qu'une restitution de ressources est engagée sur votre dossier.",
      `Dossier : ${title}`,
      fullName ? `Personne concernée : ${fullName}` : "",
      returnedAt ? `Date de restitution renseignée : ${returnedAt}` : "",
      "",
      "Si une signature ou une action complémentaire est attendue, vous recevrez un message dédié.",
      "",
      "Cordialement,"
    ].filter(Boolean)
  };
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
    const emailDraft = buildAssignmentSignatureEmailContent(draft, absoluteUrl);
    await saveSimpleEmailDraft(emailDraft, `signature_dossier_${draft?.title || id}`);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail de signature.");
  }
}

async function prepareAssignmentInfoEmail(id) {
  try {
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    if (!draft) {
      throw new Error("Impossible de retrouver le dossier.");
    }
    const emailDraft = buildAssignmentInfoEmailContent(draft);
    await saveSimpleEmailDraft(emailDraft, `information_dossier_${draft?.title || id}`);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail d'information du dossier.");
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
    const emailDraft = buildRestitutionEmailContent(draft, absoluteUrl);
    await saveSimpleEmailDraft(emailDraft, `signature_restitution_${draft?.title || id}`);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail de restitution.");
  }
}

async function prepareRestitutionInfoEmail(id) {
  try {
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    if (!draft) {
      throw new Error("Impossible de retrouver le dossier.");
    }
    const emailDraft = buildRestitutionInfoEmailContent(draft);
    await saveSimpleEmailDraft(emailDraft, `information_restitution_${draft?.title || id}`);
  } catch (error) {
    window.alert(error.message || "Impossible de préparer l'e-mail d'information de restitution.");
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
  const missingItems = buildMissingProgressPreview(result.data);
  const sections = [];
  if (previewItems.length) {
    sections.push(`<h4>Ressources attribuées</h4><ul>${previewItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
  }
  if (missingItems.length) {
    sections.push(`<h4>À compléter pour finaliser</h4><ul class="status-hover-card__missing-list">${missingItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
  }
  card.innerHTML = sections.length
    ? sections.join("")
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

function buildTimingPreview(data) {
  if (!data) {
    return [];
  }
  const sections = [];
  const startAt = data.meta?.startAt || "";
  if (startAt) {
    const offsetLabel = getTimingOffsetLabel(startAt);
    sections.push(`Prise de fonction : ${formatShortDate(startAt)}${offsetLabel ? ` (${offsetLabel})` : ""}`);
  } else {
    sections.push("Prise de fonction non renseignée");
  }
  const requested = collectRequestedResourcesFromPayload(data);
  const completed = requested.filter((r) => r.isCompleted);
  const missing = requested.filter((r) => !r.isCompleted);
  sections.push(`Progression : ${completed.length}/${requested.length} ressource(s) attribuée(s)`);
  if (missing.length) {
    const additional = data.resources?.additional || [];
    const materiel = data.materiel || {};
    const immateriel = data.immateriel || {};
    const missingLabels = missing.map((r) => {
      const fromAdditional = additional.find((a) => (a.id || a.code) === r.key);
      if (fromAdditional) return fromAdditional.label || r.key;
      const fromMat = materiel[r.key];
      if (fromMat) return fromMat.label || r.key;
      const fromImm = immateriel[r.key];
      if (fromImm) return fromImm.label || r.key;
      return r.key;
    });
    sections.push(`En attente : ${missingLabels.join(", ")}`);
  }
  return sections;
}

async function showTimingPreview(target, id) {
  const card = getHoverCard();
  if (!card) {
    return;
  }
  card.innerHTML = '<p class="status-hover-card__hint">Chargement...</p>';
  card.classList.remove("d-none");
  positionHoverCard(card, target);

  const result = await getDraftById(id);
  if (!result || !result.data) {
    card.innerHTML = '<p class="status-hover-card__hint">Impossible de charger le détail.</p>';
    positionHoverCard(card, target);
    return;
  }
  const items = buildTimingPreview(result.data);
  card.innerHTML = items.length
    ? `<h4>Pilotage</h4><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : '<p class="status-hover-card__hint">Aucune information de pilotage.</p>';
  positionHoverCard(card, target);
}

function bindTimingPreviews() {
  document.querySelectorAll("[data-timing-preview-id]").forEach((chip) => {
    if (chip.dataset.timingPreviewBound) {
      return;
    }
    chip.addEventListener("mouseenter", () => {
      void showTimingPreview(chip, chip.dataset.timingPreviewId);
    });
    chip.addEventListener("mouseleave", hideStatusPreview);
    chip.dataset.timingPreviewBound = "true";
  });
}

function bindDashboardFilters() {
  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  const timingFilter = document.getElementById("timingFilter");
  const qualiteFilter = document.getElementById("qualiteFilter");
  const serviceFilter = document.getElementById("serviceFilter");
  const sortFilter = document.getElementById("sortFilter");
  const resetButton = document.getElementById("resetFiltersBtn");

  if (!searchInput || !statusFilter || !timingFilter || !qualiteFilter || !serviceFilter || !sortFilter || !resetButton) {
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

  sortFilter.addEventListener("change", (event) => {
    dashboardFilters.sort = event.target.value || "recent";
    void renderDraftList();
  });

  resetButton.addEventListener("click", () => {
    dashboardFilters.search = "";
    dashboardFilters.status = "";
    dashboardFilters.timing = "";
    dashboardFilters.qualite = "";
    dashboardFilters.service = "";
    dashboardFilters.sort = "recent";
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
    if (sortFilter) {
      sortFilter.value = "recent";
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
  if (!document.getElementById("draftList") && !document.getElementById("historyList")) {
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
      document.getElementById("uncExportLink")?.classList.remove("d-none");
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
