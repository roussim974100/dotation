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
const DASHBOARD_PAGE_SIZE = 20;
let assignmentDisplayCount = DASHBOARD_PAGE_SIZE;
let restitutionDisplayCount = DASHBOARD_PAGE_SIZE;
let historyDisplayCount = DASHBOARD_PAGE_SIZE;
let exportProgressFallbackTimer = null;
let exportProgressValue = 0;
const dashboardFilters = {
  search: "",
  status: "",
  timing: "",
  qualite: "",
  service: "",
  // field: "date" (defaut) | "title" | "qualite" | "service" | "status" | "timing" | "progress"
  // direction: "asc" | "desc". Le select #sortFilter (recent/oldest) ne pilote que le champ "date" ;
  // le tri par clic sur un en-tete de colonne (cf bindSortableHeaders) pilote tous les champs.
  sort: { field: "date", direction: "desc" }
};

const DASHBOARD_SORT_DEFAULT = { field: "date", direction: "desc" };

// Ordre logique (pas alphabetique) pour les champs a enumeration.
const DASHBOARD_STATUS_ORDER = {
  draft: 0, partial_assignment: 1, awaiting_signature: 2, active: 3,
  partial_return: 4, returned: 5, cancelled: 6
};
const DASHBOARD_TIMING_ORDER = { late: 0, warning: 1, neutral: 2, ok: 3 };

// Une fonction par champ triable : renvoie une valeur comparable (nombre ou string).
const DASHBOARD_SORT_VALUE_GETTERS = {
  date: (draft) => new Date(draft.updatedAt || draft.assignedAt || 0).getTime(),
  title: (draft) => (draft.title || "").toLocaleLowerCase("fr"),
  qualite: (draft) => (formatQualiteLabel(draft) || "").toLocaleLowerCase("fr"),
  service: (draft) => (getDraftServiceValue(draft) || "").toLocaleLowerCase("fr"),
  status: (draft) => DASHBOARD_STATUS_ORDER[draft.status || "draft"] ?? 99,
  timing: (draft) => DASHBOARD_TIMING_ORDER[getDraftProgressMetrics(draft).timingStatus] ?? 99,
  progress: (draft) => getDraftProgressMetrics(draft).ratio || 0,
  // Ecart remise/restitution (restitutions-pending.html uniquement) : negatif = restitue
  // en avance, positif = en retard. Neutre si l'une des deux dates manque.
  recovery: (draft) => (draft.returnedAt && draft.assignedAt)
    ? new Date(draft.returnedAt).getTime() - new Date(draft.assignedAt).getTime()
    : 0,
};

// Definition centralisee des colonnes des tableaux dashboard : une seule source pour
// le libelle (th desktop + data-label mobile), le champ de tri et le rendu de cellule.
// Remplace les <th> autrefois dupliques et codes en dur sur chacune des 4 pages
// dashboard (et qui avaient deja derive : "Qualite" appelee "Etat" sur une page,
// "Avancement" appele "Etat" sur une autre, pour les memes donnees).
const DASHBOARD_COLUMNS = {
  checkbox: {
    label: null,
    sortField: null,
    headClass: "draft-check-col",
    headHtml: () => `<input id="selectAllDrafts" class="form-check-input" type="checkbox" aria-label="Tout sélectionner">`,
    render: (ctx) => `
      <td class="draft-check-col">
        ${(ctx.permissions.canExport || ctx.permissions.canDelete) ? `<input class="form-check-input draft-select" type="checkbox" value="${ctx.draft.id}" aria-label="Sélectionner ${escapeHtml(ctx.title)}">` : ""}
      </td>`
  },
  dossier: {
    label: "Dossier",
    sortField: "title",
    render: (ctx) => `
      <td data-label="Dossier">
        <div class="draft-title-wrap">
          <span class="draft-title">${escapeHtml(ctx.title)}</span>
          ${(ctx.draft.data?.unc_acces?.length > 0) ? `<span class="draft-unc-badge" title="${ctx.draft.data.unc_acces.length} chemin${ctx.draft.data.unc_acces.length > 1 ? "s" : ""} UNC">UNC</span>` : ""}
        </div>
        <div class="draft-meta">${escapeHtml(ctx.dossierTypeLabel)}${ctx.startAtLabel ? ` · ${ctx.startAtLabel}` : ""}</div>
      </td>`
  },
  qualite: {
    label: "Qualité",
    secondary: true, // masquee sur ecran etroit (l'info reste dans l'apercu rapide)
    sortField: "qualite",
    render: (ctx) => `<td data-label="Qualité">${escapeHtml(formatQualiteLabel(ctx.draft))}</td>`
  },
  avancement: {
    label: "Avancement",
    sortField: "status",
    render: (ctx) => `<td data-label="Avancement"><span class="status-chip status-chip--${escapeHtml(ctx.draft.status || "draft")}" data-status-preview-id="${ctx.draft.id}">${escapeHtml(formatDraftStatusLabel(ctx.draft))}</span></td>`
  },
  pilotage: {
    label: "Pilotage",
    sortField: "timing",
    render: (ctx) => `
      <td data-label="Pilotage">
        <span class="timing-chip timing-chip--${escapeHtml(ctx.progress.timingStatus)}" data-timing-preview-id="${ctx.draft.id}">${escapeHtml(ctx.progress.timingLabel)}</span>
        ${ctx.timingOffsetLabel ? `<div class="draft-meta draft-meta--timing">${escapeHtml(ctx.timingOffsetLabel)}</div>` : ""}
      </td>`
  },
  progression: {
    label: "Progression",
    sortField: "progress",
    render: (ctx) => `
      <td data-label="Progression">
        <div class="resource-progress">
          <div class="resource-progress__fraction">${ctx.progress.completed}/${ctx.progress.total}</div>
          <div class="resource-progress__track">
            <div class="resource-progress__bar" style="width:${ctx.progressPercent}%"></div>
          </div>
        </div>
      </td>`
  },
  recuperation: {
    label: "Récupération",
    sortField: "recovery",
    render: (ctx) => `<td data-label="Récupération">${ctx.recoveryBadge || ""}</td>`
  },
  derniere_modification: {
    label: "Dernière modification",
    secondary: true,
    sortField: "date",
    render: (ctx) => `<td data-label="Dernière modification">${escapeHtml(formatDate(ctx.draft.updatedAt))}</td>`
  },
  actions: {
    label: "Actions",
    sortField: null,
    headClass: "text-end",
    render: (ctx) => `
      <td data-label="Actions" class="draft-actions-cell">
        <div class="draft-actions">
          ${buildDraftActionButtons(ctx.draft, ctx.permissions)}
        </div>
      </td>`
  }
};

// Colonnes visibles par vue, dans l'ordre d'affichage.
const DASHBOARD_VIEW_COLUMNS = {
  active: ["checkbox", "dossier", "qualite", "avancement", "pilotage", "progression", "derniere_modification", "actions"],
  restitutions_pending: ["checkbox", "dossier", "qualite", "avancement", "pilotage", "progression", "recuperation", "derniere_modification", "actions"],
  history_assignments: ["dossier", "qualite", "pilotage", "progression", "derniere_modification", "actions"],
  history_restitutions: ["dossier", "qualite", "pilotage", "progression", "derniere_modification", "actions"],
};

// Onglets de navigation des 4 tableaux de bord : une seule definition (libelle, page, regle de
// comptage) au lieu de 4 copies de <nav> en dur. Le compteur applique le meme predicat que la vue.
const DASHBOARD_NAV = [
  { view: "active", label: "Attributions en cours", href: "index.html", count: (d) => isOperationalAssignmentDraft(d) },
  { view: "history_assignments", label: "Attributions finalisées", href: "assignments-completed.html", count: (d) => isCompletedAssignmentDraft(d) },
  { view: "restitutions_pending", label: "Restitutions en cours", href: "restitutions-pending.html", count: (d) => isOperationalRestitutionDraft(d) },
  { view: "history_restitutions", label: "Restitutions finalisées", href: "restitutions-completed.html", count: (d) => isCompletedRestitutionDraft(d) }
];

function renderDashboardNav(drafts) {
  const nav = document.getElementById("dashboardNav");
  if (!nav) {
    return;
  }
  const current = getDashboardViewMode();
  nav.innerHTML = DASHBOARD_NAV.map((tab) => {
    const isActive = tab.view === current;
    const count = Array.isArray(drafts) ? drafts.filter(tab.count).length : null;
    return `<a class="dashboard-nav__link${isActive ? " is-active" : ""}" href="${tab.href}"${isActive ? ' aria-current="page"' : ""}>${escapeHtml(tab.label)}${count === null ? "" : ` <span class="dashboard-nav__count">${count}</span>`}</a>`;
  }).join("");
}

function getDashboardViewColumns() {
  return DASHBOARD_VIEW_COLUMNS[getDashboardViewMode()] || DASHBOARD_VIEW_COLUMNS.active;
}

function renderDashboardTableHead(containerId) {
  const thead = document.getElementById(containerId);
  if (!thead) {
    return;
  }
  const cells = getDashboardViewColumns().map((key) => {
    const col = DASHBOARD_COLUMNS[key];
    if (!col) {
      return "";
    }
    if (col.headHtml) {
      return `<th class="${col.headClass || ""}">${col.headHtml()}</th>`;
    }
    const headClasses = [col.headClass, col.secondary ? "dash-col--secondary" : ""].filter(Boolean).join(" ");
    const classAttr = headClasses ? ` class="${headClasses}"` : "";
    const sortAttr = col.sortField ? ` data-sort-field="${col.sortField}"` : "";
    return `<th${sortAttr}${classAttr}>${escapeHtml(col.label || "")}</th>`;
  }).join("");
  thead.innerHTML = `<tr>${cells}</tr>`;
}

function hasActiveFilters() {
  return Boolean(
    dashboardFilters.search || dashboardFilters.status || dashboardFilters.timing
    || dashboardFilters.qualite || dashboardFilters.service
  );
}

// Filtres du tableau de bord : controle DOM, cle de dashboardFilters et evenement de remise a zero.
const DASHBOARD_FILTER_CONTROLS = [
  { key: "search", id: "searchInput", label: "Recherche", event: "input" },
  { key: "status", id: "statusFilter", label: "Avancement", event: "change" },
  { key: "timing", id: "timingFilter", label: "Pilotage", event: "change" },
  { key: "qualite", id: "qualiteFilter", label: "Qualité", event: "change" },
  { key: "service", id: "serviceFilter", label: "Service", event: "change" }
];

function renderFilterChips() {
  const host = document.getElementById("filterChips");
  if (!host) return;
  host.innerHTML = DASHBOARD_FILTER_CONTROLS
    .filter((control) => dashboardFilters[control.key] && document.getElementById(control.id))
    .map((control) => {
      const el = document.getElementById(control.id);
      const text = el.tagName === "SELECT" ? el.selectedOptions[0]?.textContent || dashboardFilters[control.key] : dashboardFilters[control.key];
      return `<button class="filter-chip" type="button" data-clear-filter="${control.id}" aria-label="Retirer le filtre ${escapeHtml(control.label)}">${escapeHtml(control.label)} : ${escapeHtml(text)} <span aria-hidden="true">✕</span></button>`;
    }).join("");
}

function initFilterToolbar() {
  const toolbar = document.querySelector(".filter-toolbar");
  const actions = toolbar?.querySelector(".filter-toolbar__actions");
  const grid = toolbar?.querySelector(".filter-toolbar__grid");
  if (!toolbar || !actions || !grid || document.getElementById("toggleFiltersBtn")) return;

  grid.id = grid.id || "filterToolbarGrid";
  toolbar.classList.add("is-collapsed");

  const toggle = document.createElement("button");
  toggle.id = "toggleFiltersBtn";
  toggle.type = "button";
  toggle.className = "btn btn-outline-secondary btn-sm";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", grid.id);
  toggle.textContent = "Filtres";
  toggle.addEventListener("click", () => {
    const collapsed = toolbar.classList.toggle("is-collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
  });
  actions.prepend(toggle);

  const chips = document.createElement("div");
  chips.id = "filterChips";
  chips.className = "filter-chips";
  toolbar.appendChild(chips);
  chips.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-clear-filter]");
    const el = chip && document.getElementById(chip.dataset.clearFilter);
    if (!el) return;
    el.value = "";
    el.dispatchEvent(new Event(el.tagName === "INPUT" ? "input" : "change", { bubbles: true }));
  });
}

function updateFilterBadge() {
  renderFilterChips();
  const badge = document.getElementById("filterActiveBadge");
  if (!badge) return;
  const count = [
    dashboardFilters.search,
    dashboardFilters.status,
    dashboardFilters.timing,
    dashboardFilters.qualite,
    dashboardFilters.service,
    (dashboardFilters.sort.field !== DASHBOARD_SORT_DEFAULT.field
      || dashboardFilters.sort.direction !== DASHBOARD_SORT_DEFAULT.direction) ? "sort" : "",
  ].filter(Boolean).length;
  badge.textContent = count;
  badge.classList.toggle("d-none", count === 0);
}

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
    // Un champ masque (cf admin Ressources) n'a plus de saisie possible depuis le
    // formulaire : on ne peut donc plus exiger de valeur meme s'il est marque obligatoire.
    const hasMissingRequiredField = fieldSchema.some((field) => !field.hidden && field.required && !String(fieldValues[field.key] || "").trim());
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
  const workflowStatus = payload?.workflow?.status || "draft";
  const isOnboarded = ["active", "returned", "partial_return", "cancelled"].includes(workflowStatus);

  if (total === 0) {
    return { completed: 0, total: 0, ratio: 0, timingStatus: "neutral", timingLabel: "À planifier" };
  }
  if (completed >= total) {
    return { completed, total, ratio: 1, timingStatus: "ok", timingLabel: "Prêt" };
  }
  // Dossier actif ou restitué : la personne est en poste, ne plus afficher "En retard"
  if (isOnboarded) {
    return { completed, total, ratio: completed / total, timingStatus: "neutral", timingLabel: "À compléter" };
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
  const warningDays = Number(window.APP_BRANDING?.timingWarningDays) || 3;
  if (daysUntilStart <= warningDays) {
    return { completed, total, ratio: completed / total, timingStatus: "warning", timingLabel: "En danger" };
  }
  return { completed, total, ratio: completed / total, timingStatus: "ok", timingLabel: "Dans les temps" };
}

function getDraftProgressMetrics(draft) {
  if (Number.isFinite(draft.completedResources) && Number.isFinite(draft.totalResources)) {
    const isOnboarded = ["active", "returned", "partial_return", "cancelled"].includes(draft.status);
    let timingStatus = draft.timingStatus || "neutral";
    let timingLabel = draft.timingLabel || "À planifier";
    // Neutraliser le retard pour les dossiers où la personne est en poste
    if (isOnboarded && timingStatus === "late") {
      timingStatus = "neutral";
      timingLabel = draft.completedResources >= draft.totalResources ? "Prêt" : "À compléter";
    }
    return {
      completed: draft.completedResources,
      total: draft.totalResources,
      ratio: Number.isFinite(draft.resourceProgressRatio) ? draft.resourceProgressRatio : (draft.totalResources ? draft.completedResources / draft.totalResources : 0),
      timingStatus,
      timingLabel
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

function buildRestitutionsPendingRow(draft, permissions) {
  const progress = getDraftProgressMetrics(draft);
  const progressPercent = Math.max(0, Math.min(100, Math.round((progress.ratio || 0) * 100)));
  const title = draft.title || (draft.data ? buildDraftTitle(draft.data) : "Dossier");
  const dossierTypeLabel = formatDossierTypeLabel(draft.dossierType || draft.data?.dossier?.type || "");

  let recoveryBadge = "";
  if (draft.returnedAt && draft.assignedAt) {
    const returned = new Date(draft.returnedAt);
    const assigned = new Date(draft.assignedAt);
    if (returned < assigned) {
      recoveryBadge = '<span class="timing-chip timing-chip--ok">Tôt</span>';
    } else if (returned > assigned) {
      recoveryBadge = '<span class="timing-chip timing-chip--warning">Tardif</span>';
    } else {
      recoveryBadge = '<span class="timing-chip timing-chip--neutral">Dans les temps</span>';
    }
  }

  const ctx = {
    draft, permissions, progress, progressPercent, title, dossierTypeLabel, recoveryBadge,
    startAtLabel: "", timingOffsetLabel: ""
  };
  const cells = getDashboardViewColumns().map((key) => renderDashboardCell(key, ctx)).join("");

  return `
    <tr class="draft-row ${dashboardPendingNewIds.has(draft.id) ? "draft-row--new" : ""}" data-quick-preview-id="${draft.id}">
      ${cells}
    </tr>
  `;
}

// Rendu d'une cellule ; une colonne « secondary » recoit la classe qui la masque sur ecran etroit.
function renderDashboardCell(key, ctx) {
  const column = DASHBOARD_COLUMNS[key];
  const html = column?.render(ctx) || "";
  return column?.secondary ? html.replace(/<td/, '<td class="dash-col--secondary"') : html;
}

function buildDashboardRow(draft, permissions) {
  const viewMode = getDashboardViewMode();
  if (viewMode === "restitutions_pending") {
    return buildRestitutionsPendingRow(draft, permissions);
  }

  const progress = getDraftProgressMetrics(draft);
  const progressPercent = Math.max(0, Math.min(100, Math.round((progress.ratio || 0) * 100)));
  const title = draft.title || (draft.data ? buildDraftTitle(draft.data) : "Dossier");
  const dossierTypeLabel = formatDossierTypeLabel(draft.dossierType || draft.data?.dossier?.type || "");
  const _timingFrozenStatuses = ["active", "returned", "partial_return", "cancelled"];
  const timingOffsetLabel = getDashboardViewMode() === "history_assignments"
    && !_timingFrozenStatuses.includes(draft.status)
    && progress.timingLabel !== "Prêt"
    ? getTimingOffsetLabel(draft.startAt)
    : "";
  const _dossierType = draft.dossierType || draft.data?.dossier?.type || "";
  const startAtLabel = _dossierType === "mise_a_jour"
    ? ""
    : draft.startAt
      ? `Prise de fonction : ${escapeHtml(formatShortDate(draft.startAt))}`
      : "Prise de fonction non renseignée";

  const ctx = {
    draft, permissions, progress, progressPercent, title, dossierTypeLabel, startAtLabel, timingOffsetLabel,
    recoveryBadge: ""
  };
  const cells = getDashboardViewColumns().map((key) => renderDashboardCell(key, ctx)).join("");

  return `
    <tr class="draft-row ${dashboardPendingNewIds.has(draft.id) ? "draft-row--new" : ""}" data-quick-preview-id="${draft.id}">
      ${cells}
    </tr>
  `;
}

function formatQualiteLabel(item) {
  const qualite = item.beneficiaryType || item.data?.beneficiaire?.qualite;
  if (!qualite) return "Non renseigné";
  const types = window.APP_BRANDING?.beneficiaryTypes;
  if (types) {
    const found = types.find((t) => t.value === qualite);
    if (found) return found.label;
  }
  if (qualite === "elu") return "Élu(e)";
  if (qualite === "agent") return "Agent";
  return qualite;
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
  const { field, direction } = dashboardFilters.sort || DASHBOARD_SORT_DEFAULT;
  const getValue = DASHBOARD_SORT_VALUE_GETTERS[field] || DASHBOARD_SORT_VALUE_GETTERS.date;
  sorted.sort((left, right) => {
    const a = getValue(left);
    const b = getValue(right);
    const cmp = typeof a === "string" ? a.localeCompare(b, "fr") : (a || 0) - (b || 0);
    return direction === "asc" ? cmp : -cmp;
  });
  return sorted;
}

// Rendu d'un groupe d'actions : bouton direct si 1 item, dropdown si plusieurs.
// Menu "Plus d'actions" d'une ligne : sections nommees (documents, e-mail) puis, tout en bas et
// separee, l'action destructrice. Les actions sont portees par data-action (cf. DRAFT_ACTION_MAP).
function renderRowActionMenu(sections, dangerItems) {
  const groups = sections.filter((section) => section.items.length);
  if (!groups.length && !dangerItems.length) return "";
  const button = (item, tone = "btn-outline-secondary") =>
    `<button class="btn btn-sm ${tone}" type="button" data-action="${item.action}" data-id="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button>`;
  return `
    <details class="draft-actions__menu" data-action-menu data-label="⋯" data-open-label="✕">
      <summary class="btn btn-sm btn-outline-secondary" aria-label="Plus d'actions"><span data-action-menu-label>⋯</span></summary>
      <div class="draft-actions__menu-panel">
        ${groups.map((section) => `
        <div class="draft-actions__menu-section">
          <p class="draft-actions__menu-title">${escapeHtml(section.title)}</p>
          ${section.items.map((item) => button(item)).join("")}
        </div>`).join("")}
        ${dangerItems.length ? `<div class="draft-actions__menu-section">${dangerItems.map((item) => button(item, "btn-outline-danger")).join("")}</div>` : ""}
      </div>
    </details>
  `;
}

// Une ligne = "Ouvrir" + l'action metier de l'etape (restituer / demander la signature) + menu "Plus".
function buildDraftActionButtons(draft, options) {
  const id = draft.id;
  const status = draft.status || "draft";
  const hasRestitution = hasRestitutionData(draft);
  const viewMode = getDashboardViewMode();
  const inRestitutionPhase = ["returned", "partial_return", "awaiting_signature"].includes(status);

  // Dans la vue "Restitutions en cours", "Ouvrir" va directement à restitution.html
  const inRestitutionsPendingView = viewMode === "restitutions_pending";
  const openAction = (inRestitutionsPendingView && canOpenRestitution(draft, options))
    ? "openRestitution"
    : "editDraft";

  // Action metier de l'etape, mise en avant a cote de "Ouvrir".
  let stepAction = null;
  if (options.canRestitution && status === "active" && !inRestitutionsPendingView) {
    stepAction = { action: "openRestitution", label: "Restituer" };
  } else if (inRestitutionPhase && canRequestRestitutionSignature(draft, options)) {
    stepAction = { action: "prepareRestitutionSignatureEmail", label: status === "awaiting_signature" ? "Relancer la signature" : "Demander la signature" };
  } else if (!inRestitutionPhase && status !== "active" && canRequestAssignmentSignature(draft, options)) {
    stepAction = { action: "prepareAssignmentSignatureEmail", label: status === "awaiting_signature" ? "Relancer la signature" : "Demander la signature" };
  }

  // Documents (PDF) — l'ordre suit la phase
  const pdfItems = [];
  if (options.canExport) {
    if (inRestitutionPhase && hasRestitution) {
      pdfItems.push({ action: "exportRestitutionPdf", id, label: "PDF de restitution" });
      pdfItems.push({ action: "exportDraftPdf", id, label: "PDF du dossier" });
    } else {
      pdfItems.push({ action: "exportDraftPdf", id, label: "PDF du dossier" });
      if (hasRestitution) {
        pdfItems.push({ action: "exportRestitutionPdf", id, label: "PDF de restitution" });
      }
    }
  }

  // E-mails — actions adaptées au workflow courant (la demande de signature est promue en bouton)
  const emailItems = [];
  if (inRestitutionPhase) {
    emailItems.push({ action: "prepareRestitutionInfoEmail", id, label: "Informer de la restitution" });
    if (options.canExport && hasRestitution) {
      emailItems.push({ action: "prepareRestitutionPdfEmail", id, label: "Envoyer le PDF de restitution" });
    }
  } else {
    emailItems.push({ action: "prepareAssignmentInfoEmail", id, label: "Informer de la création" });
    if (options.canExport) {
      emailItems.push({ action: "prepareDraftPdfEmail", id, label: "Envoyer le PDF du dossier" });
    }
  }

  // Depuis un dossier deja finalise : repartir de l'identite de la personne pour une nouvelle attribution.
  const canCreate = sessionInfo?.permissions?.includes("*") || sessionInfo?.permissions?.includes("forms.create");
  const personItems = (canCreate && ["active", "returned", "partial_return"].includes(status))
    ? [{ action: "newAssignmentForPerson", id, label: "Nouvelle attribution pour cette personne" }]
    : [];

  const dangerItems = options.canDelete ? [{ action: "removeDraft", id, label: "Supprimer le dossier" }] : [];

  return `
    <div class="draft-actions__primary">
      <button class="btn btn-sm btn-primary" type="button" data-action="${openAction}" data-id="${id}">Ouvrir</button>
      ${stepAction ? `<button class="btn btn-sm btn-outline-primary" type="button" data-action="${stepAction.action}" data-id="${id}">${escapeHtml(stepAction.label)}</button>` : ""}
      ${renderRowActionMenu([
        { title: "Documents", items: pdfItems },
        { title: "Envoyer par e-mail", items: emailItems },
        { title: "Dossier", items: personItems }
      ], dangerItems)}
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
    return applyDashboardFilters(drafts.filter((draft) => isCompletedAssignmentDraft(draft)));
  }

  if (viewMode === "history_restitutions") {
    return applyDashboardFilters(drafts.filter((draft) => isCompletedRestitutionDraft(draft)));
  }

  if (viewMode === "restitutions_pending") {
    return applyDashboardFilters(drafts.filter((draft) => isOperationalRestitutionDraft(draft)));
  }

  return applyDashboardFilters(drafts.filter((draft) => isOperationalAssignmentDraft(draft)));
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

function formatDossierTypeLabel(dossierType) {
  const labels = {
    arrivee: "Nouvelle arrivée",
    changement_service: "Changement de service",
    mise_a_jour: "Mise à jour de ressources",
    sortie: "Sortie (régularisation)"
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
  // - injection automatique du token CSRF pour les méthodes mutantes
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

  const method = (fetchOptions.method || "GET").toUpperCase();
  const csrfHeaders = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && typeof getCsrfToken === "function") {
    csrfHeaders["X-CSRF-Token"] = await getCsrfToken();
  }

  let response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeaders,
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

// ETag de la liste : persiste avec le cache local, pour que changer d'onglet (autre page du tableau de bord)
// obtienne un 304 immediat au lieu de retelecharger toute la liste. Le serveur y inclut l'utilisateur,
// le seuil de pilotage et la date du jour.
const LIST_ETAG_KEY = "dotationDraftsEtag";
let listFormsEtag = (() => {
  try { return localStorage.getItem(LIST_ETAG_KEY); } catch (error) { return null; }
})();
async function listForms() {
  try {
    const fetchHeaders = {};
    // Sans cache local exploitable, un 304 renverrait une liste vide : on redemande alors la liste complete.
    if (listFormsEtag && getCachedDrafts().length > 0) {
      fetchHeaders["If-None-Match"] = listFormsEtag;
    }
    const response = await fetch(API_BASE, {
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...fetchHeaders },
      credentials: "same-origin",
    });
    if (response.status === 304) {
      return getCachedDrafts();
    }
    const etag = response.headers.get("ETag");
    if (etag) {
      listFormsEtag = etag;
      try { localStorage.setItem(LIST_ETAG_KEY, etag); } catch (error) { /* stockage indisponible : sans effet */ }
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const items = await response.json();
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
    showToast("Votre profil est en consultation seule. La création de dossier n'est pas autorisée.", "warning");
    return;
  }
  window.location.href = "form.html";
}

function editDraft(id) {
  window.location.href = `form.html?id=${encodeURIComponent(id)}`;
}

function newAssignmentForPerson(id) {
  window.location.href = `form.html?prefillFrom=${encodeURIComponent(id)}`;
}

function openRestitution(id) {
  window.location.href = `restitution-phase1.html?id=${encodeURIComponent(id)}`;
}

// Modale "Nouvelle restitution" : une restitution part toujours d'une attribution
// active sans restitution en cours, on la choisit donc dans cette liste.
async function openNewRestitutionModal() {
  if (!(sessionInfo?.permissions?.includes("*") || sessionInfo?.permissions?.includes("forms.restitution"))) {
    showToast("Votre profil ne permet pas de lancer une restitution.", "warning");
    return;
  }

  let modal = document.getElementById("newRestitutionModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "password-generator-modal d-none";
    modal.id = "newRestitutionModal";
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <div class="password-generator-modal__backdrop" data-new-restitution-close="true"></div>
      <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="newRestitutionModalTitle">
        <div class="password-generator-modal__header">
          <div>
            <p class="panel-eyebrow">Restitution</p>
            <h2 class="section-title" id="newRestitutionModalTitle">Nouvelle restitution</h2>
          </div>
          <button class="btn btn-outline-secondary btn-sm" type="button" data-new-restitution-close="true">Fermer</button>
        </div>
        <div class="btn-group w-100 mt-3" role="group" aria-label="Type de restitution">
          <button class="btn btn-outline-primary active" type="button" id="newRestitutionModePick" aria-pressed="true">Attribution existante</button>
          <button class="btn btn-outline-primary" type="button" id="newRestitutionModeRegul" aria-pressed="false">Personne sans attribution</button>
        </div>
        <div class="password-generator-modal__content" id="newRestitutionPickPanel">
          <label class="form-label" for="newRestitutionSearch">Attribution concernée</label>
          <input class="form-control mb-3" id="newRestitutionSearch" type="search" placeholder="Nom, prénom, service, titre…" autocomplete="off">
          <div class="list-group" id="newRestitutionResults" role="list"></div>
          <p class="form-text mb-0" id="newRestitutionHint"></p>
        </div>
        <form class="password-generator-modal__content d-none" id="newRestitutionRegulPanel" novalidate>
          <p class="form-text">Régularisation : le dossier est créé directement en restitution en cours, sans attribution.</p>
          <div id="newRestitutionRegulFields"></div>
          <fieldset class="mb-3">
            <legend class="form-label fs-6">Ressources à récupérer</legend>
            <div id="newRestitutionRegulResources" class="row row-cols-1 row-cols-sm-2 g-1"></div>
          </fieldset>
          <p class="text-danger small d-none" id="newRestitutionRegulError" role="alert"></p>
          <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
            <button class="btn btn-outline-primary" type="submit" id="newRestitutionRegulAnother" data-another="true">Enregistrer et créer une autre</button>
            <button class="btn btn-primary" type="submit" id="newRestitutionRegulSubmit">Créer la restitution</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(modal);
  }

  const search = document.getElementById("newRestitutionSearch");
  const results = document.getElementById("newRestitutionResults");
  const hint = document.getElementById("newRestitutionHint");
  const MAX_RESULTS = 50;

  if (!currentDraftRows.length) {
    try {
      currentDraftRows = await listForms();
    } catch (error) {
      showToast("Impossible de charger la liste des attributions.", "error");
      return;
    }
  }
  const candidates = currentDraftRows.filter((draft) => isCompletedAssignmentDraft(draft));

  const close = () => {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
    document.removeEventListener("keydown", onKeydown);
  };
  const onKeydown = (event) => {
    if (event.key === "Escape") {
      close();
    }
  };

  const renderResults = () => {
    const query = normalizeText(search.value);
    const matches = candidates.filter((draft) => {
      if (!query) return true;
      const haystack = normalizeText([
        draft.title, draft.nom, draft.prenom, getDraftServiceValue(draft)
      ].filter(Boolean).join(" "));
      return haystack.includes(query);
    });
    const shown = matches.slice(0, MAX_RESULTS);
    results.innerHTML = shown.map((draft) => `
      <button class="list-group-item list-group-item-action" type="button" data-new-restitution-id="${escapeHtml(draft.id)}">
        <span class="fw-semibold">${escapeHtml(draft.title || "Dossier")}</span>
        <span class="d-block small text-muted">${escapeHtml(getDraftServiceValue(draft) || "")}</span>
      </button>
    `).join("");
    if (candidates.length === 0) {
      hint.textContent = "Aucune attribution active à restituer pour le moment.";
    } else if (matches.length === 0) {
      hint.textContent = "Aucune attribution ne correspond à cette recherche.";
    } else if (matches.length > MAX_RESULTS) {
      hint.textContent = `${matches.length} résultats, affinez la recherche pour voir les autres.`;
    } else {
      hint.textContent = `${matches.length} attribution${matches.length > 1 ? "s" : ""} active${matches.length > 1 ? "s" : ""}.`;
    }
  };

  modal.querySelectorAll("[data-new-restitution-close]").forEach((btn) => {
    btn.onclick = close;
  });
  results.onclick = (event) => {
    const item = event.target.closest("[data-new-restitution-id]");
    if (item) {
      openRestitution(item.dataset.newRestitutionId);
    }
  };
  search.oninput = renderResults;
  search.value = "";
  renderResults();
  setupRegularisationPanel(modal);

  document.addEventListener("keydown", onKeydown);
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  search.focus();
}

// Champs du formulaire de régularisation, définis en objet (cf. feedback "objet plutôt que HTML en dur").
const REGULARISATION_FIELDS = [
  { key: "nom", label: "Nom", type: "text", required: true, autocomplete: "family-name" },
  { key: "prenom", label: "Prénom", type: "text", required: true, autocomplete: "given-name" },
  { key: "qualite", label: "Qualité", type: "select", options: [["agent", "Agent"], ["elu", "Élu(e)"]] },
  { key: "service", label: "Service", type: "select", options: [] }
];

function buildRegularisationFieldHtml(field) {
  const id = `regul_${field.key}`;
  const control = field.type === "select"
    ? `<select class="form-select" id="${id}">${field.options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("")}</select>`
    : `<input class="form-control" id="${id}" type="text"${field.required ? " required" : ""}${field.autocomplete ? ` autocomplete="${field.autocomplete}"` : ""}>`;
  return `<div class="mb-3"><label class="form-label" for="${id}">${escapeHtml(field.label)}${field.required ? " *" : ""}</label>${control}</div>`;
}

async function setupRegularisationPanel(modal) {
  const pickPanel = document.getElementById("newRestitutionPickPanel");
  const regulPanel = document.getElementById("newRestitutionRegulPanel");
  const fieldsWrap = document.getElementById("newRestitutionRegulFields");
  const resourcesWrap = document.getElementById("newRestitutionRegulResources");
  const errorEl = document.getElementById("newRestitutionRegulError");
  const submitBtn = document.getElementById("newRestitutionRegulSubmit");
  // Les deux boutons d'envoi sont verrouilles ensemble : sinon un double envoi cree un doublon.
  const setSubmitting = (busy) => regulPanel.querySelectorAll('button[type="submit"]').forEach((btn) => { btn.disabled = busy; });

  const showPanel = (name) => {
    pickPanel.classList.toggle("d-none", name !== "pick");
    regulPanel.classList.toggle("d-none", name !== "regul");
    [["newRestitutionModePick", "pick"], ["newRestitutionModeRegul", "regul"]].forEach(([id, mode]) => {
      const btn = document.getElementById(id);
      btn.classList.toggle("active", name === mode);
      btn.setAttribute("aria-pressed", String(name === mode));
    });
    (name === "pick" ? document.getElementById("newRestitutionSearch") : document.getElementById("regul_nom"))?.focus();
  };
  showPanel("pick");
  errorEl.classList.add("d-none");
  document.getElementById("newRestitutionModeRegul").onclick = () => showPanel("regul");
  document.getElementById("newRestitutionModePick").onclick = () => showPanel("pick");

  let services = [];
  let resources = [];
  try {
    [services, resources] = await Promise.all([
      requestJson("/api/reference/services"),
      requestJson("/api/reference/resources")
    ]);
  } catch (error) {
    services = [];
    resources = [];
  }
  const fields = REGULARISATION_FIELDS.map((field) => field.key === "service"
    ? { ...field, options: [["", "Non renseigné"], ...services.map((svc) => [svc.label, svc.label])] }
    : field);
  fieldsWrap.innerHTML = fields.map(buildRegularisationFieldHtml).join("");
  const returnable = resources.filter((res) => res.category === "materiel" && res.requires_return);
  resourcesWrap.innerHTML = returnable.length
    ? returnable.map((res) => `
        <div class="col"><div class="form-check">
          <input class="form-check-input" type="checkbox" id="regul_res_${res.id}" value="${res.id}">
          <label class="form-check-label" for="regul_res_${res.id}">${escapeHtml(res.label)}</label>
        </div></div>`).join("")
    : `<p class="form-text mb-0">Aucune ressource à restituer n'est définie dans le catalogue.</p>`;

  regulPanel.onsubmit = async (event) => {
    event.preventDefault();
    const createAnother = event.submitter?.dataset.another === "true";
    const value = (key) => document.getElementById(`regul_${key}`)?.value.trim() || "";
    const resourceIds = [...resourcesWrap.querySelectorAll("input:checked")].map((input) => input.value);
    const showError = (message) => {
      errorEl.textContent = message;
      errorEl.classList.remove("d-none");
    };
    if (!value("nom") || !value("prenom")) {
      showError("Le nom et le prénom sont obligatoires.");
      return;
    }
    if (resourceIds.length === 0) {
      showError("Sélectionnez au moins une ressource à récupérer.");
      return;
    }
    errorEl.classList.add("d-none");
    setSubmitting(true);
    try {
      const result = await requestJson("/api/forms/regularisation", {
        method: "POST",
        body: JSON.stringify({
          nom: value("nom"), prenom: value("prenom"), qualite: value("qualite"),
          service: value("service"), resourceIds
        })
      });
      if (createAnother) {
        // Saisie en serie : on vide le formulaire, la liste se rafraichira a la fermeture.
        showToast(`Restitution créée : ${result.title}.`, "success");
        regulPanel.reset();
        resourcesWrap.querySelectorAll("input:checked").forEach((input) => { input.checked = false; });
        setSubmitting(false);
        document.getElementById("regul_nom")?.focus();
        void renderDraftList();
      } else {
        openRestitution(result.form_id);
      }
    } catch (error) {
      showError(error.message || "Impossible de créer la restitution.");
      setSubmitting(false);
    }
  };
}

function renderLoadMoreButton(group, total, displayed, permissions) {
  const containerIds = { assignment: "assignmentLoadMoreWrap", restitution: "restitutionLoadMoreWrap", history: "historyLoadMoreWrap" };
  const containerId = containerIds[group];
  let wrap = document.getElementById(containerId);
  if (!wrap) return;
  const remaining = total - displayed;
  if (remaining <= 0) {
    wrap.innerHTML = "";
    return;
  }
  const next = Math.min(remaining, DASHBOARD_PAGE_SIZE);
  wrap.innerHTML = `<button class="btn btn-outline-secondary btn-sm" type="button" data-load-more="${group}">Voir ${next} de plus <span class="text-muted">(${remaining} restant${remaining > 1 ? "s" : ""})</span></button>`;
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
  const filterEmptyState = document.getElementById("filterEmptyState");
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
    renderDashboardNav(sortedDrafts);
    const filteredDrafts = filterDraftsForCurrentView(sortedDrafts);
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
      if (draftList) draftList.innerHTML = "";
      if (restitutionList) restitutionList.innerHTML = "";
      if (historyList) historyList.innerHTML = "";
      // Vider aussi les boutons "Voir plus" : sinon ils gardent le HTML du
      // rendu precedent (non filtre) et restent affiches sur une liste vide.
      ["assignmentLoadMoreWrap", "restitutionLoadMoreWrap", "historyLoadMoreWrap"].forEach((id) => {
        const wrap = document.getElementById(id);
        if (wrap) wrap.innerHTML = "";
      });
      dashboardSelectedIds = new Set();
      const filtersActive = hasActiveFilters() && sortedDrafts.length > 0;
      filterEmptyState?.classList.toggle("d-none", !filtersActive);
      emptyState?.classList.toggle("d-none", filtersActive || viewMode !== "active");
      assignmentEmptyState?.classList.add("d-none");
      restitutionEmptyState?.classList.add("d-none");
      historyEmptyState?.classList.toggle("d-none", filtersActive || viewMode === "active");
      updateDashboardRefreshInfo();
      setDashboardUpdateNotice();
      updateExportSelectedState();
      return;
    }

    emptyState?.classList.add("d-none");
    filterEmptyState?.classList.add("d-none");
    historyEmptyState?.classList.add("d-none");
    const user = await getSessionInfo();
    const canExport = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.export"));
    const canDelete = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.delete"));
    const canRestitution = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.restitution"));
    const canEdit = Boolean(user?.permissions?.includes("*") || user?.permissions?.includes("forms.edit"));

    if (viewMode === "active") {
      if (draftList) {
        const visibleAssignment = assignmentDrafts.slice(0, assignmentDisplayCount);
        draftList.innerHTML = visibleAssignment
          .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
          .join("");
        renderLoadMoreButton("assignment", assignmentDrafts.length, assignmentDisplayCount, { canExport, canDelete, canRestitution, canEdit });
      }
      if (restitutionList) {
        const visibleRestitution = restitutionDrafts.slice(0, restitutionDisplayCount);
        restitutionList.innerHTML = visibleRestitution
          .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
          .join("");
        renderLoadMoreButton("restitution", restitutionDrafts.length, restitutionDisplayCount, { canExport, canDelete, canRestitution, canEdit });
      }
      assignmentEmptyState?.classList.toggle("d-none", assignmentDrafts.length > 0);
      restitutionEmptyState?.classList.toggle("d-none", restitutionDrafts.length > 0);
    } else if (historyList) {
      const visibleHistory = historyDrafts.slice(0, historyDisplayCount);
      historyList.innerHTML = visibleHistory
        .map((draft) => buildDashboardRow(draft, { canExport, canDelete, canRestitution, canEdit }))
        .join("");
      renderLoadMoreButton("history", historyDrafts.length, historyDisplayCount, { canExport, canDelete, canRestitution, canEdit });
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
    const selectable = viewMode === "active" || viewMode === "restitutions_pending";
    bindSelectionActions(selectable && canExport, viewMode === "active" && canDelete);
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
  const extMatch = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (extMatch) {
    try {
      return decodeURIComponent(extMatch[1].trim());
    } catch (_err) {
      // fall through to plain filename / fallback
    }
  }
  const plainMatch = disposition.match(/filename="([^"]+)"/i);
  return plainMatch ? plainMatch[1] : fallback;
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
    showToast(
      error.message || (kind === "restitution"
        ? "Impossible de préparer l'e-mail du PDF restitution."
        : "Impossible de préparer l'e-mail du PDF dossier."),
      "error"
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
    showToast("Impossible de générer le PDF dossier.", "error");
  }
}

async function exportRestitutionPdf(id) {
  try {
    const { blob, fileName } = await fetchPdfDocument(id, "restitution");
    saveBlob(blob, fileName);
  } catch (error) {
    showToast("Impossible de générer le PDF restitution.", "error");
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
  const isMiseAJour = (draft?.dossierType || draft?.data?.dossier?.type || "") === "mise_a_jour";
  const startAt = (!isMiseAJour && draft?.startAt) ? formatShortDate(draft.startAt) : "";
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

async function ensureRestitutionSignatureLink(id, validityDays) {
  let result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/restitution-signature-link`);
  if (!result?.link || result.link.status !== "active" || !result.link.url) {
    result = await requestJson(`${API_BASE}/${encodeURIComponent(id)}/restitution-signature-link`, {
      method: "POST",
      body: validityDays ? JSON.stringify({ validityDays }) : undefined
    });
  }
  return {
    link: result.link,
    absoluteUrl: new URL(result.link.url, window.location.origin).href
  };
}

function askSignatureLinkValidityDays() {
  return new Promise((resolve) => {
    let modal = document.getElementById("signatureLinkValidityModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.className = "password-generator-modal d-none";
      modal.id = "signatureLinkValidityModal";
      modal.setAttribute("aria-hidden", "true");
      modal.innerHTML = `
        <div class="password-generator-modal__backdrop" data-validity-modal-close="true"></div>
        <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="signatureLinkValidityModalTitle">
          <div class="password-generator-modal__header">
            <div>
              <p class="panel-eyebrow">Signature à distance</p>
              <h2 class="section-title" id="signatureLinkValidityModalTitle">Validité du lien de signature</h2>
            </div>
            <button class="btn btn-outline-secondary btn-sm" type="button" data-validity-modal-close="true">Fermer</button>
          </div>
          <div class="password-generator-modal__content">
            <div class="mb-3">
              <label class="form-label" for="signatureLinkValidityDays">Nombre de jours</label>
              <input class="form-control" id="signatureLinkValidityDays" type="number" min="1" max="30" value="7">
              <div class="form-text">Choisissez une durée entre 1 et 30 jours.</div>
            </div>
          </div>
          <div class="password-generator-modal__actions">
            <button class="btn btn-outline-secondary" type="button" data-validity-modal-close="true">Annuler</button>
            <button class="btn btn-primary" id="signatureLinkValidityConfirmBtn" type="button">Générer le lien</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }

    const input = document.getElementById("signatureLinkValidityDays");
    input.value = "7";

    const close = (value) => {
      modal.classList.add("d-none");
      modal.setAttribute("aria-hidden", "true");
      resolve(value);
    };

    modal.querySelectorAll("[data-validity-modal-close]").forEach((btn) => {
      btn.onclick = () => close(null);
    });
    document.getElementById("signatureLinkValidityConfirmBtn").onclick = () => {
      const raw = Number.parseInt(input.value || "7", 10);
      const days = Number.isFinite(raw) ? Math.min(30, Math.max(1, raw)) : 7;
      close(days);
    };

    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
    input.focus();
  });
}

async function shareSignatureLink(id) {
  try {
    const { absoluteUrl } = await ensureAssignmentSignatureLink(id);
    const copied = await copyTextWithFallback(absoluteUrl, "Copiez ce lien de signature :");
    showToast(copied ? "Lien de signature copié dans le presse-papiers." : "Lien de signature prêt à être copié.", copied ? "success" : "info");
  } catch (error) {
    showToast(error.message || "Impossible de préparer le lien de signature.", "error");
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
    showToast(error.message || "Impossible de préparer l'e-mail de signature.", "error");
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
    showToast(error.message || "Impossible de préparer l'e-mail d'information du dossier.", "error");
  }
}

async function copyRestitutionSignatureLink(id) {
  try {
    const { absoluteUrl } = await ensureRestitutionSignatureLink(id);
    const copied = await copyTextWithFallback(absoluteUrl, "Copiez ce lien de signature de restitution :");
    showToast(copied ? "Lien de signature de restitution copié dans le presse-papiers." : "Lien de signature de restitution prêt à être copié.", copied ? "success" : "info");
  } catch (error) {
    showToast(error.message || "Impossible de préparer le lien de restitution.", "error");
  }
}

async function prepareRestitutionSignatureEmail(id) {
  try {
    const validityDays = await askSignatureLinkValidityDays();
    if (validityDays === null) {
      return;
    }
    const { absoluteUrl } = await ensureRestitutionSignatureLink(id, validityDays);
    const result = await getDraftById(id);
    const draft = result
      ? { ...result.summary, data: result.data }
      : findDraftSummary(id);
    const emailDraft = buildRestitutionEmailContent(draft, absoluteUrl);
    await saveSimpleEmailDraft(emailDraft, `signature_restitution_${draft?.title || id}`);
  } catch (error) {
    showToast(error.message || "Impossible de préparer l'e-mail de restitution.", "error");
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
    showToast(error.message || "Impossible de préparer l'e-mail d'information de restitution.", "error");
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
        showToast("Lien copié.", "success");
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
      if (!await askConfirm("Révoquer ce lien de signature ?", { confirmLabel: "Révoquer", confirmClass: "btn-danger" })) {
        return;
      }
      try {
        await requestJson(`/api/signature-links/${encodeURIComponent(linkId)}`, {
          method: "DELETE"
        });
        persistDashboardSignatureLinkNotice(null);
        renderDashboardSignatureLinkNotice();
        showToast("Lien révoqué.", "success");
      } catch (error) {
        showToast(error.message || "Impossible de révoquer ce lien.", "error");
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

  // Actions groupees contextuelles : visibles seulement quand une ligne est cochee (et permise).
  const setBulkState = (button) => {
    button.disabled = selectedCount === 0;
    button.classList.toggle("d-none", button.dataset.permitted !== "true" || selectedCount === 0);
  };

  if (exportButton) {
    setBulkState(exportButton);
    exportButton.textContent = selectedCount > 1 ? `PDF de ${selectedCount} dossiers` : "PDF du dossier sélectionné";
  }

  if (restitutionExportButton) {
    setBulkState(restitutionExportButton);
    restitutionExportButton.textContent = selectedCount > 1 ? `PDF de ${selectedCount} restitutions` : "PDF de la restitution sélectionnée";
  }

  if (deleteButton) {
    setBulkState(deleteButton);
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
    showToast("Sélectionnez au moins un dossier à supprimer.", "warning");
    return;
  }

  const confirmed = await askConfirm(
    ids.length > 1
      ? `Supprimer définitivement les ${ids.length} dossiers sélectionnés ?`
      : "Supprimer définitivement le dossier sélectionné ?",
    { confirmLabel: "Supprimer", confirmClass: "btn-danger" }
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
    exportButton.dataset.permitted = String(canExport);
    exportButton.disabled = true;
    if (!exportButton.dataset.boundExportSelection) {
      exportButton.addEventListener("click", () => {
        void exportSelectedPdfs();
      });
      exportButton.dataset.boundExportSelection = "true";
    }
  }

  if (restitutionExportButton) {
    restitutionExportButton.dataset.permitted = String(canExport);
    restitutionExportButton.disabled = true;
    if (!restitutionExportButton.dataset.boundExportRestitutionSelection) {
      restitutionExportButton.addEventListener("click", () => {
        void exportSelectedRestitutionPdfs();
      });
      restitutionExportButton.dataset.boundExportRestitutionSelection = "true";
    }
  }

  if (deleteButton) {
    deleteButton.dataset.permitted = String(canDelete);
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
  updateExportSelectedState();
}

async function removeDraft(id) {
  const item = await getDraftById(id);
  if (!item) {
    return;
  }

  const confirmed = await askConfirm(`Supprimer le dossier "${item.summary.title}" ?`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" });
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

function resetDashboardPagination() {
  assignmentDisplayCount = DASHBOARD_PAGE_SIZE;
  restitutionDisplayCount = DASHBOARD_PAGE_SIZE;
  historyDisplayCount = DASHBOARD_PAGE_SIZE;
}

// Point d'entree unique pour changer le tri (select #sortFilter ou clic sur en-tete de
// colonne) : garde les deux UI synchronisees avec dashboardFilters.sort.
function applyDashboardSort(field, direction) {
  dashboardFilters.sort = { field, direction };
  resetDashboardPagination();
  syncSortUI();
  updateFilterBadge();
  void renderDraftList();
}

// Reflete l'etat de tri courant sur le select "Trier par" (uniquement pertinent pour le
// champ "date") et sur les en-tetes de colonne triables (chevron + aria-sort).
function syncSortUI() {
  const { field, direction } = dashboardFilters.sort || DASHBOARD_SORT_DEFAULT;
  const sortFilter = document.getElementById("sortFilter");
  if (sortFilter) {
    sortFilter.value = field === "date" ? (direction === "asc" ? "oldest" : "recent") : "";
  }
  document.querySelectorAll(".draft-table th[data-sort-field]").forEach((th) => {
    const isActive = th.dataset.sortField === field;
    th.classList.toggle("is-sorted-asc", isActive && direction === "asc");
    th.classList.toggle("is-sorted-desc", isActive && direction === "desc");
    th.setAttribute("aria-sort", isActive ? (direction === "asc" ? "ascending" : "descending") : "none");
  });
}

// Delegation de clic sur les en-tetes triables : un clic sur un champ deja actif inverse
// le sens, un clic sur un nouveau champ demarre en ascendant (desc pour "date", pour
// rester coherent avec le tri "plus recent d'abord" historique par defaut).
function bindSortableHeaders() {
  document.querySelectorAll(".draft-table thead").forEach((thead) => {
    if (thead.dataset.sortBound === "true") {
      return;
    }
    thead.addEventListener("click", (event) => {
      const th = event.target.closest("th[data-sort-field]");
      if (!th) {
        return;
      }
      const field = th.dataset.sortField;
      const current = dashboardFilters.sort || DASHBOARD_SORT_DEFAULT;
      const direction = current.field === field
        ? (current.direction === "asc" ? "desc" : "asc")
        : (field === "date" ? "desc" : "asc");
      applyDashboardSort(field, direction);
    });
    thead.dataset.sortBound = "true";
  });
  syncSortUI();
}

function bindDashboardFilters() {
  const searchInput = document.getElementById("searchInput");
  const statusFilter = document.getElementById("statusFilter");
  const timingFilter = document.getElementById("timingFilter");
  const qualiteFilter = document.getElementById("qualiteFilter");
  const serviceFilter = document.getElementById("serviceFilter");
  const sortFilter = document.getElementById("sortFilter");
  const resetButton = document.getElementById("resetFiltersBtn");

  if (!searchInput || !timingFilter || !qualiteFilter || !serviceFilter || !sortFilter || !resetButton) {
    return;
  }

  bindSortableHeaders();
  initFilterToolbar();

  searchInput.addEventListener("input", (event) => {
    dashboardFilters.search = event.target.value.trim();
    resetDashboardPagination();
    updateFilterBadge();
    void renderDraftList();
  });

  statusFilter?.addEventListener("change", (event) => {
    dashboardFilters.status = event.target.value;
    resetDashboardPagination();
    updateFilterBadge();
    void renderDraftList();
  });

  timingFilter.addEventListener("change", (event) => {
    dashboardFilters.timing = event.target.value;
    resetDashboardPagination();
    updateFilterBadge();
    void renderDraftList();
  });

  qualiteFilter.addEventListener("change", (event) => {
    dashboardFilters.qualite = event.target.value;
    resetDashboardPagination();
    updateFilterBadge();
    void renderDraftList();
  });

  serviceFilter.addEventListener("change", (event) => {
    dashboardFilters.service = event.target.value;
    resetDashboardPagination();
    updateFilterBadge();
    void renderDraftList();
  });

  sortFilter.addEventListener("change", (event) => {
    applyDashboardSort("date", event.target.value === "oldest" ? "asc" : "desc");
  });

  resetButton.addEventListener("click", () => {
    dashboardFilters.search = "";
    dashboardFilters.status = "";
    dashboardFilters.timing = "";
    dashboardFilters.qualite = "";
    dashboardFilters.service = "";
    dashboardFilters.sort = { ...DASHBOARD_SORT_DEFAULT };
    if (searchInput) searchInput.value = "";
    if (statusFilter) statusFilter.value = "";
    if (timingFilter) timingFilter.value = "";
    if (qualiteFilter) qualiteFilter.value = "";
    if (serviceFilter) serviceFilter.value = "";
    syncSortUI();
    updateFilterBadge();
    void renderDraftList();
  });

  document.getElementById("filterEmptyResetBtn")?.addEventListener("click", () => {
    resetButton?.click();
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
let refreshDashboardDebounceTimer = null;
function refreshDashboardIfVisible() {
  if (document.hidden) {
    return;
  }
  if (refreshDashboardDebounceTimer) {
    window.clearTimeout(refreshDashboardDebounceTimer);
  }
  refreshDashboardDebounceTimer = window.setTimeout(() => {
    refreshDashboardDebounceTimer = null;
    void renderDraftList();
  }, 300);
}

function startDashboardAutoRefresh() {
  if (dashboardRefreshTimer) {
    window.clearInterval(dashboardRefreshTimer);
  }
  dashboardRefreshTimer = window.setInterval(() => {
    refreshDashboardIfVisible();
  }, DASHBOARD_REFRESH_INTERVAL_MS);
}

function initExportExcelModal() {
  const btn = document.getElementById("exportExcelBtn");
  if (!btn) return;

  const STATUS_OPTIONS = [
    ["", "Tous les statuts"],
    ["draft", "À compléter"],
    ["partial_assignment", "Attribution partielle"],
    ["awaiting_signature", "En attente de signature"],
    ["active", "Attribution active"],
    ["returned", "Restitution terminée"],
    ["partial_return", "Restitution partielle"],
    ["cancelled", "Dossier annulé"],
  ];

  const modal = document.createElement("div");
  modal.className = "export-filter-modal is-hidden";
  modal.id = "exportFilterModal";
  modal.innerHTML = `
    <div class="export-filter-modal__dialog">
      <h3>Exporter les dossiers (Excel)</h3>
      <div class="mb-3">
        <label class="form-label" for="exportFilterStatus">Statut</label>
        <select id="exportFilterStatus" class="form-select form-select-sm">
          ${STATUS_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label" for="exportFilterService">Service (contient)</label>
        <input id="exportFilterService" class="form-control form-control-sm" type="text" placeholder="ex : DSI, Bâtiment…">
      </div>
      <div class="export-filter-modal__row mb-3">
        <div>
          <label class="form-label" for="exportFilterDateFrom">Mis à jour depuis</label>
          <input id="exportFilterDateFrom" class="form-control form-control-sm" type="date">
        </div>
        <div>
          <label class="form-label" for="exportFilterDateTo">jusqu'au</label>
          <input id="exportFilterDateTo" class="form-control form-control-sm" type="date">
        </div>
      </div>
      <div class="export-filter-modal__actions">
        <button type="button" class="btn btn-outline-secondary btn-sm" id="exportFilterCancelBtn">Annuler</button>
        <button type="button" class="btn btn-primary btn-sm" id="exportFilterConfirmBtn">Exporter</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  btn.addEventListener("click", () => {
    modal.classList.remove("is-hidden");
    document.getElementById("exportFilterStatus").value = "";
    document.getElementById("exportFilterService").value = "";
    document.getElementById("exportFilterDateFrom").value = "";
    document.getElementById("exportFilterDateTo").value = "";
  });

  document.getElementById("exportFilterCancelBtn").addEventListener("click", () => {
    modal.classList.add("is-hidden");
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.add("is-hidden");
  });

  document.getElementById("exportFilterConfirmBtn").addEventListener("click", () => {
    const params = new URLSearchParams();
    const status = document.getElementById("exportFilterStatus").value;
    const service = document.getElementById("exportFilterService").value.trim();
    const dateFrom = document.getElementById("exportFilterDateFrom").value;
    const dateTo = document.getElementById("exportFilterDateTo").value;
    if (status) params.set("status", status);
    if (service) params.set("service", service);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const url = "/api/forms/export" + (params.toString() ? "?" + params.toString() : "");
    window.location.href = url;
    modal.classList.add("is-hidden");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  // Initialisation d'accueil : session, liste et masquage du hover au scroll.
  if (!document.getElementById("draftList") && !document.getElementById("historyList")) {
    return;
  }
  initExportExcelModal();
  dashboardPendingNewIds = loadPendingDashboardUpdates();
  renderDashboardSignatureLinkNotice();
  void getSessionInfo().then((user) => {
    // « Administration » et « Synthèse » sont ajoutés au menu du compte par ui.js (renderUserMenuFeatureLinks), sur toutes les pages.
    if (user && (user.permissions.includes("forms.export") || user.permissions.includes("*"))) {
      document.getElementById("exportMenu")?.classList.remove("d-none");
    }
    if (user && (user.permissions.includes("forms.create") || user.permissions.includes("*"))) {
      document.getElementById("newFormBtn")?.classList.remove("d-none");
      document.getElementById("emptyStateNewFormBtn")?.classList.remove("d-none");
    }
    if (user && (user.permissions.includes("forms.restitution") || user.permissions.includes("*"))) {
      document.getElementById("newRestitutionBtn")?.classList.remove("d-none");
      document.getElementById("emptyStateNewRestitutionBtn")?.classList.remove("d-none");
    }
    renderDashboardSignatureLinkNotice();
  });
  document.getElementById("newFormBtn")?.addEventListener("click", newForm);
  document.getElementById("emptyStateNewFormBtn")?.addEventListener("click", newForm);
  document.getElementById("newRestitutionBtn")?.addEventListener("click", () => { void openNewRestitutionModal(); });
  document.getElementById("emptyStateNewRestitutionBtn")?.addEventListener("click", () => { void openNewRestitutionModal(); });

  const DRAFT_ACTION_MAP = {
    editDraft, openRestitution, newAssignmentForPerson, exportDraftPdf, exportRestitutionPdf,
    shareSignatureLink, copyRestitutionSignatureLink,
    prepareAssignmentInfoEmail, prepareRestitutionInfoEmail,
    prepareDraftPdfEmail, prepareRestitutionPdfEmail,
    prepareAssignmentSignatureEmail, prepareRestitutionSignatureEmail,
    removeDraft
  };
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (btn) {
      const fn = DRAFT_ACTION_MAP[btn.dataset.action];
      if (fn) fn(btn.dataset.id);
      return;
    }
    const loadMoreBtn = e.target.closest("[data-load-more]");
    if (loadMoreBtn) {
      const group = loadMoreBtn.dataset.loadMore;
      if (group === "assignment") {
        assignmentDisplayCount += DASHBOARD_PAGE_SIZE;
      } else if (group === "restitution") {
        restitutionDisplayCount += DASHBOARD_PAGE_SIZE;
      } else if (group === "history") {
        historyDisplayCount += DASHBOARD_PAGE_SIZE;
      }
      void renderDraftList();
    }
  });

  renderDashboardTableHead("draftTableHead");
  renderDashboardNav(null);
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
