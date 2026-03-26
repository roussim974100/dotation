const STORAGE_KEY = "dotationDraftsCache";
const DASHBOARD_PENDING_UPDATES_KEY = "dashboardPendingUpdates";
const API_BASE = "/api/forms";
const PDF_BATCH_EXPORT_ENDPOINT = "/api/forms/export-pdf-batch";
const RESTITUTION_PDF_BATCH_EXPORT_ENDPOINT = "/api/forms/export-restitution-pdf-batch";
const DASHBOARD_REFRESH_INTERVAL_MS = 20000;
let sessionInfo = null;
let currentDraftRows = [];
let dashboardRefreshTimer = null;
let dashboardRefreshInFlight = false;
let dashboardLastUpdatedAt = "";
let dashboardKnownIds = new Set();
let dashboardPendingNewIds = new Set();
let dashboardSelectedIds = new Set();
let exportProgressFallbackTimer = null;
const dashboardFilters = {
  search: "",
  status: "",
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
    returnedAt: payload.restitution.returnedAt || "",
    updatedAt: now
  };
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
    draft: "Brouillon",
    partial_assignment: "Attribution partielle",
    active: "Attribution active",
    returned: "Restitution terminée",
    partial_return: "Restitution partielle",
    cancelled: "Dossier annulé"
  };
  return labels[status] || "Brouillon";
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

function buildDraftActionButtons(draft, options) {
  const actions = [];
  actions.push(`<button class="btn btn-sm btn-primary" type="button" onclick="editDraft('${draft.id}')">Ouvrir</button>`);

  if (options.canRestitution && ["active", "partial_return"].includes(draft.status || "draft")) {
    actions.push(`<button class="btn btn-sm btn-outline-primary" type="button" onclick="openRestitution('${draft.id}')">Restitution</button>`);
  }

  const documentActions = [];
  if (options.canExport) {
    documentActions.push(`<button class="btn btn-sm btn-outline-success" type="button" onclick="exportDraftPdf('${draft.id}')">PDF dossier</button>`);
  }
  if (options.canExport && hasRestitutionData(draft)) {
    documentActions.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="exportRestitutionPdf('${draft.id}')">PDF restitution</button>`);
  }
  if (documentActions.length) {
    actions.push(`<div class="draft-actions__group draft-actions__group--documents">${documentActions.join("")}</div>`);
  }

  if (options.canDelete) {
    actions.push(`<button class="btn btn-sm btn-outline-danger" type="button" onclick="removeDraft('${draft.id}')">Supprimer</button>`);
  }

  return actions.join("");
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function getDraftSearchText(draft) {
  return [
    draft.title || (draft.data ? buildDraftTitle(draft.data) : ""),
    draft.nom || draft.data?.beneficiaire?.nom || "",
    draft.prenom || draft.data?.beneficiaire?.prenom || "",
    draft.service || draft.data?.beneficiaire?.service || "",
    draft.fonction || draft.data?.beneficiaire?.fonction || "",
    draft.mandat || draft.data?.beneficiaire?.mandat || ""
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
    const matchesQualite = !dashboardFilters.qualite || getDraftQualiteValue(draft) === dashboardFilters.qualite;
    const matchesService = !dashboardFilters.service || getDraftServiceValue(draft) === dashboardFilters.service;
    return matchesSearch && matchesStatus && matchesQualite && matchesService;
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
  // - calcule le compteur des fiches encore modifiables
  // - affiche les actions selon les droits de l'utilisateur
  const draftList = document.getElementById("draftList");
  const draftCount = document.getElementById("draftCount");
  const emptyState = document.getElementById("emptyState");

  if (!draftList) {
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
    const editableDrafts = filteredDrafts.filter((draft) => ["draft", "partial_assignment"].includes(draft.status || "draft"));

    if (draftCount) {
      draftCount.textContent = editableDrafts.length.toString();
    }

    if (filteredDrafts.length === 0) {
      draftList.innerHTML = "";
      dashboardSelectedIds = new Set();
      emptyState.classList.remove("d-none");
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
    draftList.innerHTML = filteredDrafts.map((draft) => `
    <tr class="draft-row ${dashboardPendingNewIds.has(draft.id) ? "draft-row--new" : ""}">
      <td class="draft-check-col">
        ${(canExport || canDelete) ? `<input class="form-check-input draft-select" type="checkbox" value="${draft.id}" aria-label="Sélectionner ${escapeHtml(draft.title || buildDraftTitle(draft.data))}">` : ""}
      </td>
      <td data-label="Dossier">
        <div class="draft-title">${escapeHtml(draft.title || (draft.data ? buildDraftTitle(draft.data) : "Dossier"))}</div>
        <div class="draft-meta">${escapeHtml(formatDossierTypeLabel(draft.dossierType || draft.data?.dossier?.type || ""))}</div>
        <div class="draft-meta">${escapeHtml(draft.nom || draft.data?.beneficiaire?.nom || "")} ${escapeHtml(draft.prenom || draft.data?.beneficiaire?.prenom || "")}</div>
      </td>
      <td data-label="Qualité">${escapeHtml(formatQualiteLabel(draft))}</td>
      <td data-label="État"><span class="status-chip status-chip--${escapeHtml(draft.status || "draft")}" data-status-preview-id="${draft.id}">${escapeHtml(formatStatusLabel(draft.status || "draft"))}</span></td>
      <td data-label="Dernière modification">${escapeHtml(formatDate(draft.updatedAt))}</td>
      <td data-label="Actions" class="draft-actions-cell">
        <div class="draft-actions">
          ${buildDraftActionButtons(draft, { canExport, canDelete, canRestitution })}
        </div>
      </td>
    </tr>
    `).join("");

    dashboardLastUpdatedAt = new Date().toISOString();
    updateDashboardRefreshInfo();
    setDashboardUpdateNotice();
    bindStatusPreviews();
    bindSelectionActions(canExport, canDelete);
    restoreDashboardSelection();
  } finally {
    dashboardRefreshInFlight = false;
  }
}

function triggerDownload(url) {
  const link = document.createElement("a");
  link.href = url;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
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

async function exportDraftPdf(id) {
  // Export unitaire : téléchargement direct d'un PDF généré par le backend.
  triggerDownload(`${API_BASE}/${encodeURIComponent(id)}/pdf`);
}

async function exportRestitutionPdf(id) {
  triggerDownload(`${API_BASE}/${encodeURIComponent(id)}/restitution-pdf`);
}

function setExportLoaderProgress(value) {
  const normalized = Math.max(0, Math.min(100, Math.round(value)));
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
  setExportLoaderProgress(0);
  overlay?.classList.remove("is-hidden");
}

function hideExportLoader() {
  if (exportProgressFallbackTimer) {
    window.clearInterval(exportProgressFallbackTimer);
    exportProgressFallbackTimer = null;
  }
  document.getElementById("exportLoader")?.classList.add("is-hidden");
}

function startFallbackExportProgress() {
  if (exportProgressFallbackTimer) {
    window.clearInterval(exportProgressFallbackTimer);
  }
  let value = 8;
  setExportLoaderProgress(value);
  exportProgressFallbackTimer = window.setInterval(() => {
    value = Math.min(value + 6, 90);
    setExportLoaderProgress(value);
  }, 350);
}

async function fetchDownloadWithProgress(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const contentLength = Number(response.headers.get("Content-Length") || 0);
  if (!response.body || !contentLength) {
    startFallbackExportProgress();
    const blob = await response.blob();
    setExportLoaderProgress(100);
    return { response, blob };
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
    setExportLoaderProgress((received / contentLength) * 100);
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
  const qualiteFilter = document.getElementById("qualiteFilter");
  const serviceFilter = document.getElementById("serviceFilter");
  const resetButton = document.getElementById("resetFiltersBtn");

  searchInput.addEventListener("input", (event) => {
    dashboardFilters.search = event.target.value.trim();
    void renderDraftList();
  });

  statusFilter.addEventListener("change", (event) => {
    dashboardFilters.status = event.target.value;
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
    dashboardFilters.qualite = "";
    dashboardFilters.service = "";
    if (searchInput) {
      searchInput.value = "";
    }
    if (statusFilter) {
      statusFilter.value = "";
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
  dashboardPendingNewIds = loadPendingDashboardUpdates();
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
