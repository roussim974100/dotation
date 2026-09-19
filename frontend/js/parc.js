// Page « Parc matériel » : liste des objets suivis, fiche avec frise chronologique, actions de gestion (parc.manage).
// Libelles et couleurs sont definis en objets (un seul endroit).

const PARC_STATUS = {
  in_stock: { label: "En stock", chip: "active" },
  assigned: { label: "Attribué", chip: "awaiting_signature" },
  degraded: { label: "Dégradé", chip: "draft" },
  maintenance: { label: "En réparation", chip: "partial_assignment" },
  lost: { label: "Perdu", chip: "cancelled" },
  retired: { label: "Réformé", chip: "cancelled" },
  unknown: { label: "À vérifier", chip: "draft" }
};

const PARC_EVENTS = {
  assigned: "Attribué", returned: "Restitué", returned_degraded: "Restitué dégradé", lost: "Perdu / non restitué",
  released: "Libéré", found: "Retrouvé", retired: "Réformé", repair_started: "Mis en réparation",
  repair_done: "Réparation terminée", verified: "Vérifié", correction: "Identifiant corrigé", merged: "Fusion", note: "Note"
};

const PARC_ANOMALIES = {
  double_attribution: "Attribué alors qu'il l'était déjà",
  assigned_while_lost: "Attribué alors qu'il était déclaré perdu",
  assigned_while_retired: "Attribué alors qu'il était réformé",
  lost_without_assignment: "Perte sans attribution connue"
};

// Actions de gestion : etats de depart (miroir du serveur, qui reste l'autorite), motif obligatoire ou non.
const PARC_ACTIONS = [
  { action: "lost", label: "Déclarer perdu", from: ["in_stock", "assigned", "degraded", "maintenance", "unknown"], note: true, tone: "btn-outline-danger" },
  { action: "found", label: "Retrouvé", from: ["lost"], tone: "btn-outline-success" },
  { action: "repair_start", label: "Mettre en réparation", from: ["in_stock", "degraded"], tone: "btn-outline-secondary" },
  { action: "repair_done", label: "Réparation terminée", from: ["maintenance"], tone: "btn-outline-success" },
  { action: "verify", label: "Confirmer : disponible", from: ["unknown"], tone: "btn-outline-success" },
  { action: "retire", label: "Réformer", from: ["in_stock", "degraded", "lost", "unknown", "maintenance"], note: true, tone: "btn-outline-danger" },
  { action: "note", label: "Ajouter une note", from: null, note: true, tone: "btn-outline-secondary" }
];

const PARC_ERRORS = {
  invalid_state: "Cette action n'est pas possible dans l'état actuel.", note_required: "Précisez le motif.",
  identifier_exists: "Une autre unité porte déjà cet identifiant : utilisez la fusion.", identifier_required: "Indiquez le nouvel identifiant.",
  different_resource: "Les deux unités doivent appartenir à la même ressource.", same_unit: "Choisissez une autre unité.",
  forbidden: "Vous n'avez pas le droit d'effectuer cette action."
};

let parcResources = [];
let parcCanManage = false;
let parcCurrent = null;

function parcEl(id) { return document.getElementById(id); }
function parcEsc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function parcDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function parcFieldLabel(code, key) {
  const resource = parcResources.find((item) => item.code === code);
  return (resource?.field_schema || []).find((field) => field.key === key)?.label || key;
}
function parcResourceLabel(code) { return parcResources.find((item) => item.code === code)?.label || code; }
function parcChip(status) {
  const meta = PARC_STATUS[status] || { label: status, chip: "draft" };
  return `<span class="status-chip status-chip--${meta.chip}">${parcEsc(meta.label)}</span>`;
}
async function parcCsrf() { return (await (await fetch("/api/csrf-token", { credentials: "same-origin" })).json()).token || ""; }

async function loadParc() {
  const params = new URLSearchParams({ limit: "500" });
  [["resource", "parcResource"], ["status", "parcStatus"], ["q", "parcSearch"]].forEach(([key, id]) => {
    const value = parcEl(id).value.trim();
    if (value) params.set(key, value);
  });
  const body = parcEl("parcBody");
  try {
    const response = await fetch(`/api/units?${params}`, { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    parcEl("parcCounts").innerHTML = Object.entries(PARC_STATUS).map(([status, meta]) => `
      <button type="button" class="btn btn-sm ${parcEl("parcStatus").value === status ? "btn-primary" : "btn-outline-secondary"}" data-parc-filter="${status}">
        ${parcEsc(meta.label)} <span class="dashboard-nav__count">${data.counts[status] || 0}</span></button>`).join("");
    body.innerHTML = data.units.length ? data.units.map((unit) => `
      <tr>
        <td data-label="Identifiant"><div class="draft-title">${parcEsc(unit.identifier)}</div>
          <div class="draft-meta">${parcEsc(Object.entries(unit.fields).filter(([, v]) => v !== unit.identifier).map(([, v]) => v).slice(0, 3).join(" · "))}</div></td>
        <td data-label="Ressource">${parcEsc(parcResourceLabel(unit.resource_code))}</td>
        <td data-label="État">${parcChip(unit.status)}</td>
        <td data-label="Détenteur">${parcEsc(unit.holder_label || "—")}</td>
        <td data-label="Mise à jour">${parcEsc(parcDate(unit.updated_at))}</td>
        <td data-label="Actions" class="text-end"><button class="btn btn-sm btn-outline-primary" type="button" data-parc-open="${parcEsc(unit.id)}">Fiche</button></td>
      </tr>`).join("") : `<tr><td colspan="6" class="text-muted">Aucune unité ne correspond.</td></tr>`;
    parcEl("parcTotal").textContent = data.units.length >= 500 ? "500+" : String(data.units.length);
  } catch (error) {
    body.innerHTML = `<tr><td colspan="6" class="text-danger">Impossible de charger le parc.</td></tr>`;
  }
}

function parcTimeline(unit) {
  return `<ol class="list-unstyled mb-0">${unit.events.slice().reverse().map((event) => `
    <li class="border-start ps-3 pb-3 ms-1">
      <strong>${parcEsc(PARC_EVENTS[event.event_type] || event.event_type)}</strong>
      <span class="small text-muted"> · ${parcEsc(parcDate(event.occurred_at))}</span>
      ${event.anomaly ? `<span class="status-chip status-chip--cancelled ms-1" title="Incohérence détectée">⚠ ${parcEsc(PARC_ANOMALIES[event.anomaly] || event.anomaly)}</span>` : ""}
      ${event.holder_label ? `<div class="small">${parcEsc(event.holder_label)}</div>` : ""}
      ${event.notes ? `<div class="small text-muted">${parcEsc(event.notes)}</div>` : ""}
      ${event.actor ? `<div class="small text-muted">par ${parcEsc(event.actor)}</div>` : ""}
    </li>`).join("")}</ol>`;
}

function parcActionsHtml(unit) {
  if (!parcCanManage) return "";
  const allowed = PARC_ACTIONS.filter((item) => item.from === null || item.from.includes(unit.status));
  return `<div class="border-top pt-3 mt-3">
      <p class="panel-eyebrow">Gestion</p>
      <label class="form-label" for="parcNote">Motif ou note</label>
      <input class="form-control mb-2" id="parcNote" autocomplete="off" placeholder="Obligatoire pour perdu, réformé et note">
      <div class="d-flex flex-wrap gap-2 mb-3">${allowed.map((item) => `<button class="btn btn-sm ${item.tone}" type="button" data-parc-action="${item.action}">${parcEsc(item.label)}</button>`).join("")}</div>
      <details><summary class="small fw-semibold">Corriger l'identifiant ou fusionner un doublon</summary>
        <div class="row g-2 mt-1 align-items-end">
          <div class="col-md-8"><label class="form-label small" for="parcNewId">Nouvel identifiant</label><input class="form-control" id="parcNewId" autocomplete="off"></div>
          <div class="col-md-4"><button class="btn btn-sm btn-outline-secondary w-100" type="button" data-parc-action="correct">Corriger</button></div>
          <div class="col-md-8"><label class="form-label small" for="parcMergeId">Fusionner dans l'unité (identifiant exact)</label><input class="form-control" id="parcMergeId" autocomplete="off" placeholder="Identifiant de l'unité à conserver"></div>
          <div class="col-md-4"><button class="btn btn-sm btn-outline-danger w-100" type="button" data-parc-action="merge">Fusionner</button></div>
        </div>
        <p class="form-text mb-0">Fusionner supprime cette fiche : tout son historique passe à l'unité conservée.</p>
      </details>
      <p class="text-danger small mt-2 mb-0 d-none" id="parcError" role="alert"></p>
    </div>`;
}

async function openParcUnit(unitId) {
  const response = await fetch(`/api/units/${encodeURIComponent(unitId)}`, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) return;
  parcCurrent = await response.json();
  renderParcDetail();
  const modal = parcEl("parcModal");
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
}

function renderParcDetail() {
  const unit = parcCurrent;
  parcEl("parcModalTitle").textContent = `${parcResourceLabel(unit.resource_code)} · ${unit.identifier}`;
  parcEl("parcModalBody").innerHTML = `
    <div class="mb-3">${parcChip(unit.status)} ${unit.holder_label ? `<span class="ms-2">Détenu par <strong>${parcEsc(unit.holder_label)}</strong></span>` : ""}</div>
    <dl class="row small">${Object.entries(unit.fields).map(([key, value]) => `<dt class="col-4 text-muted fw-normal">${parcEsc(parcFieldLabel(unit.resource_code, key))}</dt><dd class="col-8">${parcEsc(value)}</dd>`).join("")}</dl>
    ${unit.origin === "backfill_orphan" ? '<p class="alert alert-warning small">Reconstitué depuis un dossier supprimé : vérifiez le statut réel de cet objet.</p>' : ""}
    <p class="panel-eyebrow">Historique de vie</p>
    ${parcTimeline(unit)}
    ${parcActionsHtml(unit)}`;
}

function closeParcModal() {
  const modal = parcEl("parcModal");
  modal.classList.add("d-none");
  modal.setAttribute("aria-hidden", "true");
  parcCurrent = null;
}

async function runParcAction(action) {
  const errorBox = parcEl("parcError");
  const payload = { action, notes: parcEl("parcNote").value.trim() };
  if (action === "correct") payload.new_identifier = parcEl("parcNewId").value.trim();
  if (action === "merge") {
    const wanted = parcEl("parcMergeId").value.trim().toLowerCase();
    const response = await fetch(`/api/units?resource=${encodeURIComponent(parcCurrent.resource_code)}&q=${encodeURIComponent(wanted)}`, { credentials: "same-origin" });
    const found = (await response.json()).units.filter((unit) => unit.identifier.toLowerCase() === wanted && unit.id !== parcCurrent.id);
    if (!found.length) {
      errorBox.textContent = "Aucune autre unité de cette ressource ne porte cet identifiant exact.";
      errorBox.classList.remove("d-none");
      return;
    }
    if (!(await askConfirm(`Fusionner « ${parcCurrent.identifier} » dans « ${found[0].identifier} » ? Cette fiche sera supprimée, son historique conservé sur l'unité cible.`, { confirmLabel: "Fusionner", confirmClass: "btn-danger" }))) return;
    payload.target_unit_id = found[0].id;
  }
  if (["lost", "retire"].includes(action) && !(await askConfirm(action === "lost" ? "Déclarer cet objet perdu ?" : "Réformer cet objet ? Il ne sera plus proposé à l'attribution.", { confirmLabel: "Confirmer", confirmClass: "btn-danger" }))) return;
  const response = await fetch(`/api/units/${encodeURIComponent(parcCurrent.id)}/actions`, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": await parcCsrf() }, body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    errorBox.textContent = PARC_ERRORS[data.error] || data.message || `Erreur ${response.status}`;
    errorBox.classList.remove("d-none");
    return;
  }
  parcCurrent = data;
  renderParcDetail();
  loadParc();
  showToast("Action enregistrée.", "success");
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!parcEl("parcBody")) return;
  const [session, references] = await Promise.all([
    fetch("/api/session", { credentials: "same-origin" }).then((r) => r.json()).catch(() => ({})),
    fetch("/api/reference/resources", { credentials: "same-origin" }).then((r) => r.json()).catch(() => [])
  ]);
  parcCanManage = (session.permissions || []).includes("parc.manage") || (session.permissions || []).includes("*");
  parcResources = references;
  parcEl("parcResource").innerHTML = '<option value="">Toutes les ressources</option>' + references
    .filter((item) => item.identifier_key).map((item) => `<option value="${parcEsc(item.code)}">${parcEsc(item.label)}</option>`).join("");
  parcEl("parcStatus").innerHTML = '<option value="">Tous les états</option>' + Object.entries(PARC_STATUS)
    .map(([status, meta]) => `<option value="${status}">${parcEsc(meta.label)}</option>`).join("");

  ["parcResource", "parcStatus"].forEach((id) => parcEl(id).addEventListener("change", loadParc));
  let timer = null;
  parcEl("parcSearch").addEventListener("input", () => { window.clearTimeout(timer); timer = window.setTimeout(loadParc, 250); });
  document.addEventListener("click", (event) => {
    const filter = event.target.closest("[data-parc-filter]");
    if (filter) { parcEl("parcStatus").value = parcEl("parcStatus").value === filter.dataset.parcFilter ? "" : filter.dataset.parcFilter; return loadParc(); }
    const open = event.target.closest("[data-parc-open]");
    if (open) return openParcUnit(open.dataset.parcOpen);
    if (event.target.closest("[data-parc-close]")) return closeParcModal();
    const action = event.target.closest("[data-parc-action]");
    if (action && parcCurrent) return runParcAction(action.dataset.parcAction);
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && parcCurrent) closeParcModal(); });
  loadParc();
});
