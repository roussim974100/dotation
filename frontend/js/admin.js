// Module principal des écrans d'administration :
// comptes, groupes, services et ressources.
async function adminRequest(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const csrfHeaders = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && typeof getCsrfToken === "function") {
    csrfHeaders["X-CSRF-Token"] = await getCsrfToken();
  }
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaders,
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
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }

  return response.json();
}

let groups = {};
let currentUsers = [];
let currentServices = [];
let currentResources = [];
let editingUsername = null;
let editingServiceId = null;
let editingResourceId = null;
const RESOURCE_DISPLAY_ORDER_OPTIONS = [
  { value: 10, label: "Tout en haut" },
  { value: 30, label: "Début de liste" },
  { value: 60, label: "Position standard" },
  { value: 90, label: "Plus bas" },
  { value: 120, label: "Fin de liste" }
];

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Sérialise une valeur pour usage dans un attribut onclick inline.
// JSON.stringify produit un littéral de chaîne JS correctement échappé ;
// on échappe ensuite les guillemets doubles pour l'attribut HTML.
function jsStr(value) {
  return JSON.stringify(String(value ?? "")).replace(/"/g, "&quot;");
}

function slugifyFieldKey(value) {
  return String(value || "")
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function syncResourceCodeFromLabel(force = false, labelInput = byId("resource_label"), codeInput = byId("resource_code")) {
  if (!labelInput || !codeInput) {
    return;
  }
  if (!force && codeInput.dataset.manual === "true") {
    return;
  }
  codeInput.value = slugifyFieldKey(labelInput.value);
}

function renderResourceIssuerOptions(selectedValue = "", select = byId("resource_issuer")) {
  if (!select) {
    return;
  }
  const activeServices = currentServices
    .filter((service) => service.is_active)
    .map((service) => service.label);
  const options = [...new Set(activeServices)];
  const normalizedSelectedValue = String(selectedValue || "").trim();
  if (normalizedSelectedValue && !options.includes(normalizedSelectedValue)) {
    options.push(normalizedSelectedValue);
  }
  options.sort((left, right) => left.localeCompare(right, "fr"));
  select.innerHTML = `
    <option value="">Sélectionner un service</option>
    ${options.map((label) => `<option value="${escapeHtml(label)}">${escapeHtml(label)}</option>`).join("")}
  `;
  select.value = normalizedSelectedValue;
}

function syncResourceTrackingOptions(categoryInput = byId("resource_category"), conditionInput = byId("resource_has_assignment_condition"), notesInput = byId("resource_has_assignment_notes")) {
  const category = categoryInput?.value || "materiel";
  if (!conditionInput || !notesInput) {
    return;
  }
  if (category === "immateriel") {
    conditionInput.checked = false;
    conditionInput.disabled = true;
  } else {
    conditionInput.disabled = false;
  }
}

function formatResourceTrackingSummary(resource) {
  const labels = [];
  if (resource.has_assignment_date) {
    labels.push("date");
  }
  if (resource.has_assignment_condition) {
    labels.push("état");
  }
  if (resource.has_assignment_notes) {
    labels.push("observation");
  }
  return labels.length ? labels.join(", ") : "Aucun suivi";
}

function renderResourceDisplayOrderOptions(selectedValue = 60, select = byId("resource_display_order")) {
  if (!select) {
    return;
  }
  const normalizedValue = Number.parseInt(String(selectedValue || 60), 10) || 60;
  const options = [...RESOURCE_DISPLAY_ORDER_OPTIONS];
  if (!options.some((option) => option.value === normalizedValue)) {
    options.push({ value: normalizedValue, label: `Position actuelle (${normalizedValue})` });
  }
  options.sort((left, right) => left.value - right.value);
  select.innerHTML = options.map((option) => `
    <option value="${option.value}">${escapeHtml(option.label)}</option>
  `).join("");
  select.value = String(normalizedValue);
}

function setNotice(elementId, message = "", visible = false) {
  const node = byId(elementId);
  if (!node) {
    return;
  }
  node.textContent = message;
  node.classList.toggle("d-none", !visible);
}

function getUserStatusMeta(user) {
  const status = user.status || (user.is_active ? "active" : "disabled");
  if (status === "pending") {
    return { code: "draft", label: "En attente" };
  }
  if (status === "disabled" || !user.is_active) {
    return { code: "cancelled", label: "Desactive" };
  }
  return { code: "active", label: "Actif" };
}

function updateAdminMetrics() {
  const usersCount = byId("adminUsersCount");
  const pendingCount = byId("adminPendingCount");
  const servicesCount = byId("adminServicesCount");
  const resourcesCount = byId("adminResourcesCount");

  if (usersCount) {
    usersCount.textContent = String(currentUsers.length);
  }
  const pendingTotal = currentUsers.filter((user) => user.status === "pending").length;
  if (pendingCount) {
    pendingCount.textContent = String(pendingTotal);
  }
  const pendingBanner = byId("pendingAccountsBanner");
  if (pendingBanner) {
    pendingBanner.classList.toggle("d-none", pendingTotal === 0);
    const text = byId("pendingAccountsText");
    if (text) text.textContent = `${pendingTotal} compte${pendingTotal > 1 ? "s" : ""} en attente de validation.`;
  }
  if (servicesCount) {
    servicesCount.textContent = String(currentServices.filter((service) => service.is_active).length);
  }
  if (resourcesCount) {
    resourcesCount.textContent = String(currentResources.filter((resource) => resource.is_active).length);
  }
}

function renderGroups() {
  const selector = byId("groupSelector");
  const modalSelector = byId("modalGroupSelector");
  const cards = byId("groupCards");

  if (selector) {
    selector.innerHTML = Object.entries(groups).map(([key, group]) => `
      <label class="choice-chip">
        <input type="radio" name="admin_group" value="${escapeHtml(key)}" class="admin-group-option">
        <span>${escapeHtml(group.label)}</span>
      </label>
    `).join("");
  }

  if (modalSelector) {
    modalSelector.innerHTML = Object.entries(groups).map(([key, group]) => `
      <label class="choice-chip">
        <input type="radio" name="modal_group" value="${escapeHtml(key)}" class="modal-group-option">
        <span>${escapeHtml(group.label)}</span>
      </label>
    `).join("");
  }

  if (cards) {
    cards.innerHTML = Object.entries(groups).map(([key, group]) => {
      const isAdmin = (group.permissions || []).includes("*");
      const hasUnc = (group.permissions || []).includes("unc.view_all");
      const uncToggle = isAdmin
        ? `<span class="status-chip status-chip--active mt-2">Accès UNC complet (admin)</span>`
        : `<div class="form-check form-switch mt-2">
             <input class="form-check-input" type="checkbox" role="switch" id="unc_${escapeHtml(key)}" ${hasUnc ? "checked" : ""}
               data-admin-action="toggleGroupUnc" data-group-key="${escapeHtml(key)}" data-current="${hasUnc}">
             <label class="form-check-label" for="unc_${escapeHtml(key)}">Accès UNC complet</label>
           </div>`;
      return `
        <div class="equipment-item">
          <div class="draft-title">${escapeHtml(group.label)}</div>
          <div class="draft-meta">${escapeHtml(group.description || "")}</div>
          <div class="mt-2"><span class="status-chip status-chip--${group.data_scope === "masked" ? "draft" : "active"}">${escapeHtml(group.data_scope)}</span></div>
          <ul class="print-list mt-3">
            ${(group.permissions || []).map((permission) => `<li>${escapeHtml(permission)}</li>`).join("")}
          </ul>
          ${uncToggle}
        </div>
      `;
    }).join("");
  }
}

function getSelectedGroups() {
  const checked = document.querySelector(".admin-group-option:checked");
  return checked ? [checked.value] : [];
}

function setSelectedGroups(selectedGroups) {
  document.querySelectorAll(".admin-group-option").forEach((input) => {
    input.checked = selectedGroups && selectedGroups[0] === input.value;
  });
}

function getSelectedGroupsFromModal() {
  const checked = document.querySelector(".modal-group-option:checked");
  return checked ? [checked.value] : [];
}

function setSelectedGroupsInModal(selectedGroups) {
  document.querySelectorAll(".modal-group-option").forEach((input) => {
    input.checked = selectedGroups && selectedGroups[0] === input.value;
  });
}

function validatePasswordComplexity(password) {
  if (!password) {
    return null;
  }
  if (password.length < 12) {
    return "Le mot de passe doit contenir au moins 12 caractères.";
  }
  if (!/[A-Z]/.test(password)) {
    return "Le mot de passe doit contenir au moins une majuscule.";
  }
  if (!/[a-z]/.test(password)) {
    return "Le mot de passe doit contenir au moins une minuscule.";
  }
  if (!/\d/.test(password)) {
    return "Le mot de passe doit contenir au moins un chiffre.";
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    return "Le mot de passe doit contenir au moins un caractère spécial.";
  }
  return null;
}

function generateThemedPassword(theme = "licorne") {
  const themes = {
    licorne: {
      first: ["Licorne", "Arcane", "Cristal", "Aurore", "Etoile", "Nuage", "Paillet", "Corail"],
      second: ["violet", "sucre", "soie", "nacre", "brume", "velours", "lumiere", "satin"]
    },
    starwars: {
      first: ["Jedi", "Yoda", "Leia", "Andor", "Lando", "Ahsoka", "Rey", "Kenobi"],
      second: ["galaxie", "sabre", "force", "etoile", "rebel", "nebuleuse", "holo", "hyper"]
    },
    marvel: {
      first: ["Marvel", "Stark", "Thor", "Vision", "Loki", "Wanda", "Rocket", "Panther"],
      second: ["vibranium", "quantum", "cosmos", "hero", "arc", "multivers", "storm", "shield"]
    },
    film_francais: {
      first: ["Amelie", "Belmondo", "Truffaut", "Renoir", "Tautou", "Noiret", "Depardieu", "Audiard"],
      second: ["cinema", "paris", "camera", "dialogue", "lumiere", "ecran", "replique", "studio"]
    },
    local: {
      first: ["Bureau", "Equipe", "Projet", "Campus", "Atelier", "Agence", "Siege", "Centre"],
      second: ["reseau", "bureau", "dossier", "service", "espace", "portail", "accueil", "support"]
    }
  };
  const symbols = ["!", "@", "#", "$", "%"];
  const source = themes[theme] || themes.licorne;
  const left = source.first[Math.floor(Math.random() * source.first.length)];
  const right = source.second[Math.floor(Math.random() * source.second.length)];
  const digits = String(Math.floor(10 + Math.random() * 90));
  const symbol = symbols[Math.floor(Math.random() * symbols.length)];
  return `${left}-${right}${digits}${symbol}`;
}

function initPasswordGeneratorModal() {
  const modal = byId("passwordGeneratorModal");
  const trigger = byId("generateAdminPasswordBtn");
  if (!modal || !trigger) {
    return;
  }

  const themeSelect = byId("passwordThemeSelect");
  const valueField = byId("generatedPasswordValue");
  const refreshBtn = byId("refreshGeneratedPasswordBtn");
  const copyBtn = byId("copyGeneratedPasswordBtn");
  const applyBtn = byId("applyGeneratedPasswordBtn");
  let currentPassword = "";

  const refreshPassword = () => {
    currentPassword = generateThemedPassword(themeSelect?.value || "licorne");
    if (valueField) {
      valueField.value = currentPassword;
    }
  };

  const closeModal = () => {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  };

  const openModal = () => {
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
    refreshPassword();
  };

  themeSelect?.addEventListener("change", refreshPassword);
  refreshBtn?.addEventListener("click", refreshPassword);
  copyBtn?.addEventListener("click", async () => {
    if (!currentPassword) {
      refreshPassword();
    }
    await navigator.clipboard.writeText(currentPassword);
  });
  applyBtn?.addEventListener("click", () => {
    if (!currentPassword) {
      refreshPassword();
    }
    const passwordField = byId("admin_password");
    if (passwordField) {
      passwordField.value = currentPassword;
    }
    closeModal();
  });
  modal.querySelectorAll("[data-password-modal-close='true']").forEach((element) => {
    element.addEventListener("click", closeModal);
  });
  trigger.addEventListener("click", openModal);
}

function resetUserForm() {
  if (!byId("userFormTitle")) {
    return;
  }
  editingUsername = null;
  byId("userFormTitle").textContent = "Nouveau compte";
  byId("saveUserBtn").textContent = "Créer l'utilisateur";
  byId("cancelUserEditBtn").classList.add("d-none");
  setNotice("userEditNotice");
  byId("admin_username").value = "";
  byId("admin_username").disabled = false;
  byId("admin_password").value = "";
  byId("admin_password").placeholder = "Mot de passe temporaire";
  byId("admin_active").checked = true;
  if (byId("admin_service")) byId("admin_service").value = "";
  if (byId("admin_email")) byId("admin_email").value = "";
  if (byId("admin_db_manage")) byId("admin_db_manage").checked = false;
  setSelectedGroups([]);
}

function populateUserForm(username) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user) {
    return;
  }

  editingUsername = user.username;
  byId("modalAdminUsername").value = user.username;
  byId("modalAdminPassword").value = "";
  byId("modalAdminActive").checked = user.status !== "disabled";
  if (byId("modalAdminService")) byId("modalAdminService").value = user.service || "";
  if (byId("modalAdminEmail")) byId("modalAdminEmail").value = user.email || "";
  if (byId("modalAdminDbManage")) byId("modalAdminDbManage").checked = Boolean(user.db_manage);
  setSelectedGroupsInModal(user.groups || []);

  openUserEditModal();
}

function openUserEditModal() {
  const modal = byId("userEditModal");
  if (modal) {
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeUserEditModal() {
  const modal = byId("userEditModal");
  if (modal) {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  }
  editingUsername = null;
}

async function saveUserFromModal() {
  const username = byId("modalAdminUsername")?.value.trim() || "";
  const password = byId("modalAdminPassword")?.value || "";
  const isActive = Boolean(byId("modalAdminActive")?.checked);
  const selectedGroups = getSelectedGroupsFromModal();
  const passwordError = password ? validatePasswordComplexity(password) : null;

  if (passwordError) {
    showToast(passwordError, "error");
    return;
  }

  if (!editingUsername) {
    showToast("Erreur : aucun utilisateur en cours d'édition", "error");
    return;
  }

  const service = byId("modalAdminService")?.value.trim() || "";
  const email = byId("modalAdminEmail")?.value.trim() || "";
  const dbManage = Boolean(byId("modalAdminDbManage")?.checked);

  try {
    await adminRequest(`/api/admin/users/${encodeURIComponent(editingUsername)}`, {
      method: "PUT",
      body: JSON.stringify({
        groups: selectedGroups, is_active: isActive,
        status: isActive ? "active" : "disabled",
        password, service, email, db_manage: dbManage
      })
    });
    showToast("Compte mis à jour.");
    closeUserEditModal();
    await loadUsers();
  } catch (error) {
    showToast(`Impossible d'enregistrer le compte : ${error.message}`, "error");
  }
}

function createResourceFieldRow(field = {}) {
  const optionsValue = Array.isArray(field.options) ? field.options.join("\n") : "";
  const showOptions = field.type === "select";
  const isHidden = Boolean(field.hidden);
  // data-field-key fige la cle technique d'un champ existant : reformuler le libelle
  // (correction, traduction...) ne doit plus regenerer la cle et orpheliner les valeurs
  // deja enregistrees dans les dossiers. Vide pour un champ nouvellement ajoute : sa cle
  // sera derivee du libelle a la sauvegarde, comme avant.
  // data-field-hidden : champ masque (cf resource-field-remove) - reste dans le schema
  // (donc toujours resoluble en label pour les dossiers existants) mais disparait du
  // formulaire de dossier, alternative a la suppression reelle pour ne pas perdre les
  // valeurs deja saisies.
  return `
    <div class="resource-field-row ${isHidden ? "resource-field-row--hidden" : ""}" data-field-key="${escapeHtml(field.key || "")}" data-field-hidden="${isHidden ? "true" : "false"}">
      <div class="row g-3 align-items-end">
        <div class="col-md-5">
          <label class="form-label">Libellé</label>
          <input class="form-control resource-field-label" aria-label="Libellé du champ" value="${escapeHtml(field.label || "")}" placeholder="Numéro de série" ${isHidden ? "disabled" : ""}>
        </div>
        <div class="col-md-4">
          <label class="form-label">Type</label>
          <select class="form-select resource-field-type" aria-label="Type du champ" ${isHidden ? "disabled" : ""}>
            <option value="text" ${field.type === "text" ? "selected" : ""}>Texte</option>
            <option value="textarea" ${field.type === "textarea" ? "selected" : ""}>Texte long</option>
            <option value="select" ${field.type === "select" ? "selected" : ""}>Liste déroulante</option>
            <option value="date" ${field.type === "date" ? "selected" : ""}>Date</option>
            <option value="number" ${field.type === "number" ? "selected" : ""}>Nombre</option>
            <option value="checkbox" ${field.type === "checkbox" ? "selected" : ""}>Case à cocher</option>
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-check">
            <input class="form-check-input resource-field-required" type="checkbox" ${field.required ? "checked" : ""} ${isHidden ? "disabled" : ""}>
            <span class="form-check-label">Champ obligatoire</span>
          </label>
        </div>
        <div class="col-12 resource-field-options ${showOptions ? "" : "d-none"}">
          <label class="form-label">Choix de la liste</label>
          <textarea class="form-control resource-field-options-input" rows="3" placeholder="Une option par ligne" ${isHidden ? "disabled" : ""}>${escapeHtml(optionsValue)}</textarea>
          <div class="form-text">Ajoutez une valeur par ligne pour la liste déroulante.</div>
        </div>
        <div class="col-12 resource-field-hidden-banner ${isHidden ? "" : "d-none"}">
          <span class="status-pill">Champ masqué — conserve les données déjà saisies, retiré du formulaire de dossier</span>
        </div>
        <div class="col-12 d-flex justify-content-md-end gap-2">
          <button class="btn btn-outline-secondary resource-field-unhide ${isHidden ? "" : "d-none"}" type="button">Réafficher</button>
          <button class="btn btn-outline-danger resource-field-remove" type="button">Suppr.</button>
        </div>
      </div>
    </div>
  `;
}

async function handleResourceFieldRemove(row) {
  const label = row.querySelector(".resource-field-label")?.value.trim() || "ce champ";
  const existingKey = row.dataset.fieldKey || "";
  // Champ pas encore enregistre (nouvelle ligne) : rien a perdre, on retire directement.
  if (!existingKey || !editingResourceId) {
    row.remove();
    return;
  }
  let count = 0;
  try {
    const usage = await adminRequest(`/api/admin/resources/${encodeURIComponent(editingResourceId)}/fields/${encodeURIComponent(existingKey)}/usage`);
    count = Number(usage?.count) || 0;
  } catch (error) {
    // Impossible de verifier l'usage : on reste prudent et on demande confirmation simple.
    count = -1;
  }
  if (count === 0) {
    const confirmed = await askConfirm(`Aucun dossier n'utilise "${label}". Le supprimer ?`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" });
    if (confirmed) {
      row.remove();
    }
    return;
  }
  const usageText = count > 0 ? `est utilisé par ${count} dossier(s)` : "est peut-être déjà utilisé (vérification impossible)";
  const preferHide = await askConfirm(
    `Le champ "${label}" ${usageText}. Le masquer conserve les données déjà saisies et le retire simplement du formulaire — recommandé plutôt qu'une suppression définitive.`,
    { title: "Champ utilisé", confirmLabel: "Masquer le champ", confirmClass: "btn-warning", cancelLabel: "Autre option" }
  );
  if (preferHide) {
    row.dataset.fieldHidden = "true";
    row.classList.add("resource-field-row--hidden");
    row.querySelectorAll(".resource-field-label, .resource-field-type, .resource-field-required, .resource-field-options-input").forEach((el) => {
      el.disabled = true;
    });
    row.querySelector(".resource-field-hidden-banner")?.classList.remove("d-none");
    row.querySelector(".resource-field-unhide")?.classList.remove("d-none");
    return;
  }
  const confirmedDelete = await askConfirm(
    `Supprimer définitivement "${label}" ? Les données déjà saisies pour ce champ seront perdues au prochain enregistrement des dossiers concernés.`,
    { confirmLabel: "Supprimer définitivement", confirmClass: "btn-danger" }
  );
  if (confirmedDelete) {
    row.remove();
  }
}

function bindResourceFieldRows(containerId = "resourceFieldRows") {
  byId(containerId)?.querySelectorAll(".resource-field-row").forEach((row) => {
    if (row.dataset.bound === "true") {
      return;
    }
    const labelInput = row.querySelector(".resource-field-label");
    const typeInput = row.querySelector(".resource-field-type");
    const optionsWrap = row.querySelector(".resource-field-options");
    labelInput?.addEventListener("input", () => {
      labelInput.dataset.key = slugifyFieldKey(labelInput.value);
    });
    typeInput?.addEventListener("change", () => {
      optionsWrap?.classList.toggle("d-none", typeInput.value !== "select");
    });
    row.querySelector(".resource-field-remove")?.addEventListener("click", () => {
      void handleResourceFieldRemove(row);
    });
    row.querySelector(".resource-field-unhide")?.addEventListener("click", () => {
      row.dataset.fieldHidden = "false";
      row.classList.remove("resource-field-row--hidden");
      row.querySelectorAll(".resource-field-label, .resource-field-type, .resource-field-required, .resource-field-options-input").forEach((el) => {
        el.disabled = false;
      });
      row.querySelector(".resource-field-hidden-banner")?.classList.add("d-none");
      row.querySelector(".resource-field-unhide")?.classList.add("d-none");
    });
    row.dataset.bound = "true";
  });
}

function appendResourceFieldRow(field = {}, containerId = "resourceFieldRows") {
  const container = byId(containerId);
  if (!container) {
    return;
  }
  container.insertAdjacentHTML("beforeend", createResourceFieldRow(field));
  bindResourceFieldRows(containerId);
}

function collectResourceFieldSchema(containerId = "resourceFieldRows") {
  const container = byId(containerId);
  if (!container) {
    return [];
  }
  return Array.from(container.querySelectorAll(".resource-field-row")).map((row, index) => {
    const label = row.querySelector(".resource-field-label")?.value.trim() || "";
    // Cle figee a la creation du champ (cf. createResourceFieldRow) : on ne re-derive
    // du libelle que si le champ est nouveau (pas encore de cle enregistree).
    const existingKey = row.dataset.fieldKey || "";
    const key = existingKey || slugifyFieldKey(label || `champ_${index + 1}`);
    const type = row.querySelector(".resource-field-type")?.value || "text";
    const options = type === "select"
      ? String(row.querySelector(".resource-field-options-input")?.value || "")
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean)
      : [];
    return {
      label,
      key,
      type,
      placeholder: "",
      required: Boolean(row.querySelector(".resource-field-required")?.checked),
      hidden: row.dataset.fieldHidden === "true",
      options
    };
  }).filter((field) => field.label && field.key);
}

function renderResourceFieldSchema(fields = [], containerId = "resourceFieldRows") {
  const container = byId(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = "";
  fields.forEach((field) => appendResourceFieldRow(field, containerId));
}

function resetServiceForm() {
  if (!byId("serviceFormTitle")) {
    return;
  }
  editingServiceId = null;
  setNotice("serviceEditNotice");
  byId("service_label").value = "";
  byId("service_active").checked = true;
}

function populateServiceForm(serviceId) {
  const service = currentServices.find((item) => item.id === serviceId);
  if (!service) {
    return;
  }
  editingServiceId = service.id;
  byId("modalServiceLabel").value = service.label || "";
  byId("modalServiceActive").checked = Boolean(service.is_active);
  openServiceEditModal();
}

function openServiceEditModal() {
  const modal = byId("serviceEditModal");
  if (modal) {
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeServiceEditModal() {
  const modal = byId("serviceEditModal");
  if (modal) {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  }
  editingServiceId = null;
}

async function saveServiceFromModal() {
  const label = byId("modalServiceLabel")?.value.trim() || "";
  const isActive = Boolean(byId("modalServiceActive")?.checked);
  if (!label) {
    showToast("Le libellé du service est obligatoire.", "error");
    return;
  }
  if (!editingServiceId) {
    showToast("Erreur : aucun service en cours d'édition", "error");
    return;
  }
  try {
    await adminRequest(`/api/admin/services/${encodeURIComponent(editingServiceId)}`, {
      method: "PUT",
      body: JSON.stringify({ label, is_active: isActive })
    });
    showToast("Service mis à jour.");
    closeServiceEditModal();
    await loadServices();
  } catch (error) {
    showToast(`Impossible d'enregistrer le service : ${error.message}`, "error");
  }
}

function resetResourceForm() {
  if (!byId("resourceFormTitle")) {
    return;
  }
  editingResourceId = null;
  setNotice("resourceEditNotice");
  byId("resource_code").value = "";
  byId("resource_code").dataset.manual = "";
  byId("resource_label").value = "";
  byId("resource_category").value = "materiel";
  renderResourceIssuerOptions("");
  byId("resource_description").value = "";
  renderResourceDisplayOrderOptions(60);
  byId("resource_requires_return").checked = true;
  byId("resource_active").checked = true;
  byId("resource_has_assignment_date").checked = true;
  byId("resource_has_assignment_condition").checked = true;
  byId("resource_has_assignment_notes").checked = true;
  syncResourceTrackingOptions();
  renderResourceFieldSchema([]);
}

function populateResourceForm(resourceId) {
  const resource = currentResources.find((item) => item.id === resourceId);
  if (!resource) {
    return;
  }
  editingResourceId = resource.id;
  const modalLabel = byId("modalResourceLabel");
  const modalCode = byId("modalResourceCode");
  const modalCategory = byId("modalResourceCategory");
  const modalIssuer = byId("modalResourceIssuer");
  const modalCondition = byId("modalResourceHasAssignmentCondition");
  const modalNotes = byId("modalResourceHasAssignmentNotes");
  modalCode.value = resource.code || "";
  modalCode.dataset.manual = "true";
  modalLabel.value = resource.label || "";
  modalCategory.value = resource.category || "materiel";
  renderResourceIssuerOptions(resource.issuer_service || "", modalIssuer);
  byId("modalResourceDescription").value = resource.description || "";
  renderResourceDisplayOrderOptions(resource.display_order || 60, byId("modalResourceDisplayOrder"));
  byId("modalResourceRequiresReturn").checked = Boolean(resource.requires_return);
  byId("modalResourceActive").checked = Boolean(resource.is_active);
  byId("modalResourceHasAssignmentDate").checked = resource.has_assignment_date !== false;
  modalCondition.checked = Boolean(resource.has_assignment_condition);
  modalNotes.checked = resource.has_assignment_notes !== false;
  syncResourceTrackingOptions(modalCategory, modalCondition, modalNotes);
  renderResourceFieldSchema(resource.field_schema || [], "modalResourceFieldRows");
  openResourceEditModal();
}

function openResourceEditModal() {
  const modal = byId("resourceEditModal");
  if (modal) {
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeResourceEditModal() {
  const modal = byId("resourceEditModal");
  if (modal) {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  }
  editingResourceId = null;
}

async function saveResourceFromModal() {
  syncResourceCodeFromLabel(false, byId("modalResourceLabel"), byId("modalResourceCode"));
  const payload = {
    code: byId("modalResourceCode")?.value.trim() || "",
    label: byId("modalResourceLabel")?.value.trim() || "",
    description: byId("modalResourceDescription")?.value.trim() || "",
    category: byId("modalResourceCategory")?.value || "materiel",
    issuer_service: byId("modalResourceIssuer")?.value || "",
    requires_return: Boolean(byId("modalResourceRequiresReturn")?.checked),
    has_assignment_date: Boolean(byId("modalResourceHasAssignmentDate")?.checked),
    has_assignment_condition: Boolean(byId("modalResourceHasAssignmentCondition")?.checked),
    has_assignment_notes: Boolean(byId("modalResourceHasAssignmentNotes")?.checked),
    display_order: Number.parseInt(byId("modalResourceDisplayOrder")?.value || "100", 10) || 100,
    is_active: Boolean(byId("modalResourceActive")?.checked),
    field_schema: collectResourceFieldSchema("modalResourceFieldRows")
  };
  if (!payload.label) {
    showToast("Le libellé de la ressource est obligatoire.", "error");
    return;
  }
  if (!payload.code) {
    showToast("Le code de la ressource n'a pas pu être généré automatiquement.", "error");
    return;
  }
  if (!editingResourceId) {
    showToast("Erreur : aucune ressource en cours d'édition", "error");
    return;
  }
  try {
    await adminRequest(`/api/admin/resources/${encodeURIComponent(editingResourceId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    showToast("Ressource mise à jour.");
    closeResourceEditModal();
    await loadResources();
  } catch (error) {
    showToast(`Impossible d'enregistrer la ressource : ${error.message}`, "error");
  }
}

// Ligne admin : action principale visible + menu "Plus" (desactiver / supprimer en dernier, en rouge).
function renderAdminRowMenu(items, dangerItem) {
  const button = (item, tone) => `<button class="btn btn-sm ${tone}" type="button" ${item.attrs}>${item.label}</button>`;
  return `
    <details class="draft-actions__menu">
      <summary class="btn btn-sm btn-outline-secondary" aria-label="Plus d'actions">⋯</summary>
      <div class="draft-actions__menu-panel">
        ${items.length ? `<div class="draft-actions__menu-section">${items.map((item) => button(item, "btn-outline-secondary")).join("")}</div>` : ""}
        <div class="draft-actions__menu-section">${button(dangerItem, "btn-outline-danger")}</div>
      </div>
    </details>`;
}

function renderUserTable() {
  const table = byId("userTableBody");
  if (!table) {
    return;
  }
  table.innerHTML = sortAdminTable("user", currentUsers).map((user) => {
    const statusMeta = getUserStatusMeta(user);
    const username = escapeHtml(user.username);
    const approveButton = user.status === "pending"
      ? `<button class="btn btn-sm btn-success" type="button" data-admin-action="approveUser" data-username="${username}">Valider</button>`
      : "";
    const menuItems = user.status === "pending"
      ? []
      : [{ label: user.is_active ? "Désactiver" : "Activer", attrs: `data-admin-action="toggleUserState" data-username="${username}" data-active="${user.is_active ? "false" : "true"}"` }];
    const rowMenu = renderAdminRowMenu(menuItems, { label: "Supprimer", attrs: `data-admin-action="deleteUser" data-username="${username}"` });
    return `
      <tr>
        <td data-label="Utilisateur">${escapeHtml(user.username)}${user.email ? `<div class="draft-meta">${escapeHtml(user.email)}</div>` : ""}</td>
        <td data-label="Groupes">${escapeHtml((user.groups || []).join(", ") || "-")}</td>
        <td data-label="Service">${escapeHtml(user.service || "—")}</td>
        <td data-label="État"><span class="status-chip status-chip--${statusMeta.code}">${statusMeta.label}</span></td>
        <td data-label="Actions" class="text-end">
          <div class="draft-actions">
            ${approveButton}
            <button class="btn btn-sm btn-outline-primary" type="button" data-admin-action="populateUserForm" data-username="${username}">Modifier</button>
            ${rowMenu}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function loadUsers() {
  currentUsers = await adminRequest("/api/admin/users");
  bindAdminSortableHeaders("user", "userTableBody", renderUserTable);
  renderUserTable();
  updateAdminMetrics();
}

async function saveUser() {
  const username = byId("admin_username")?.value.trim() || "";
  const password = byId("admin_password")?.value || "";
  const isActive = Boolean(byId("admin_active")?.checked);
  const selectedGroups = getSelectedGroups();
  const passwordError = validatePasswordComplexity(password);

  if (!editingUsername && !password) {
    showToast("Le mot de passe est obligatoire.", "error");
    return;
  }
  if (passwordError) {
    showToast(passwordError, "error");
    return;
  }

  const service = byId("admin_service")?.value.trim() || "";
  const email = byId("admin_email")?.value.trim() || "";
  const dbManage = Boolean(byId("admin_db_manage")?.checked);
  if (!editingUsername) {
    await adminRequest("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username, password, groups: selectedGroups,
        is_active: isActive, status: isActive ? "active" : "disabled",
        service, email, db_manage: dbManage
      })
    });
  } else {
    await adminRequest(`/api/admin/users/${encodeURIComponent(editingUsername)}`, {
      method: "PUT",
      body: JSON.stringify({
        groups: selectedGroups, is_active: isActive,
        status: isActive ? "active" : "disabled",
        password, service, email, db_manage: dbManage
      })
    });
  }

  resetUserForm();
  await loadUsers();
}

async function toggleUserState(username, nextState) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user) {
    return;
  }
  await adminRequest(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PUT",
    body: JSON.stringify({
      groups: user.groups,
      is_active: nextState,
      status: nextState ? "active" : "disabled"
    })
  });
  await loadUsers();
}

async function approveUser(username) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user) {
    return;
  }
  await adminRequest(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PUT",
    body: JSON.stringify({
      groups: user.groups,
      is_active: true,
      status: "active"
    })
  });
  await loadUsers();
}

async function deleteUser(username) {
  const confirmed = await askConfirm(`Supprimer définitivement le compte "${username}" ?`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" });
  if (!confirmed) {
    return;
  }
  await adminRequest(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "DELETE"
  });
  if (editingUsername === username) {
    resetUserForm();
  }
  await loadUsers();
}

function populateServiceSelect() {
  const sel = byId("admin_service");
  const modalSel = byId("modalAdminService");

  if (!sel && !modalSel) return;

  if (sel) {
    const current = sel.value;
    sel.innerHTML = '<option value="">— Aucun service —</option>';
    (currentServices || []).filter((s) => s.is_active).forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.label;
      opt.textContent = s.label;
      sel.appendChild(opt);
    });
    sel.value = current;
  }

  if (modalSel) {
    const current = modalSel.value;
    modalSel.innerHTML = '<option value="">— Aucun service —</option>';
    (currentServices || []).filter((s) => s.is_active).forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.label;
      opt.textContent = s.label;
      modalSel.appendChild(opt);
    });
    modalSel.value = current;
  }
}

async function loadServices() {
  currentServices = await adminRequest("/api/admin/services");
  renderResourceIssuerOptions(byId("resource_issuer")?.value || "");
  populateServiceSelect();
  const table = byId("serviceTableBody");
  if (!table) {
    updateAdminMetrics();
    return;
  }
  table.innerHTML = currentServices.map((service) => `
    <tr>
      <td data-label="Service">
        <div class="draft-title">${escapeHtml(service.label)}</div>
      </td>
      <td data-label="État"><span class="status-chip status-chip--${service.is_active ? "active" : "cancelled"}">${service.is_active ? "Actif" : "Inactif"}</span></td>
      <td data-label="Actions" class="text-end">
        <div class="draft-actions">
          <button class="btn btn-sm btn-outline-primary" type="button" data-admin-action="populateServiceForm" data-id="${escapeHtml(String(service.id))}">Modifier</button>
          ${renderAdminRowMenu(
            [{ label: service.is_active ? "Désactiver" : "Activer", attrs: `data-admin-action="toggleServiceState" data-id="${escapeHtml(String(service.id))}" data-active="${service.is_active ? "false" : "true"}"` }],
            { label: "Supprimer", attrs: `data-admin-action="deleteService" data-id="${escapeHtml(String(service.id))}"` }
          )}
        </div>
      </td>
    </tr>
  `).join("");
  updateAdminMetrics();
}

async function saveService() {
  const payload = {
    label: byId("service_label")?.value.trim() || "",
    is_active: Boolean(byId("service_active")?.checked)
  };
  if (!payload.label) {
    showToast("Le libellé du service est obligatoire.", "error");
    return;
  }
  await adminRequest("/api/admin/services", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  resetServiceForm();
  await loadServices();
}

async function toggleServiceState(serviceId, nextState) {
  await adminRequest(`/api/admin/services/${encodeURIComponent(serviceId)}`, {
    method: "PUT",
    body: JSON.stringify({ is_active: nextState })
  });
  await loadServices();
}

async function deleteService(serviceId) {
  const service = currentServices.find((item) => item.id === serviceId);
  const label = service?.label || "ce service";
  const confirmed = await askConfirm(`Supprimer définitivement le service "${label}" ?`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" });
  if (!confirmed) {
    return;
  }
  await adminRequest(`/api/admin/services/${encodeURIComponent(serviceId)}`, {
    method: "DELETE"
  });
  if (editingServiceId === serviceId) {
    closeServiceEditModal();
  }
  await loadServices();
}

async function handleServiceCsvImport() {
  const fileInput = byId("csvFileInput");
  const modeSelect = byId("csvImportMode");
  const feedback = byId("csvImportFeedback");
  if (!fileInput?.files?.length) {
    showCsvFeedback(feedback, "Veuillez sélectionner un fichier CSV.", true);
    return;
  }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("mode", modeSelect?.value || "append");
  try {
    const response = await fetch("/api/admin/services/import-csv", {
      method: "POST",
      credentials: "same-origin",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      const msgs = {
        no_file: "Aucun fichier reçu.",
        invalid_encoding: "Encodage du fichier invalide (UTF-8 attendu).",
        missing_label_column: "Colonne « label » manquante dans le fichier.",
      };
      showCsvFeedback(feedback, msgs[data.error] || data.error, true);
      return;
    }
    showCsvFeedback(feedback, `Import terminé : ${data.imported} ajouté(s), ${data.skipped} existant(s) ignoré(s).`, false);
    fileInput.value = "";
    await loadServices();
  } catch (_) {
    showCsvFeedback(feedback, "Erreur de connexion au serveur.", true);
  }
}

function showCsvFeedback(el, msg, isError) {
  if (!el) return;
  el.textContent = msg;
  el.className = "alert " + (isError ? "alert-danger" : "alert-success");
  el.classList.remove("d-none");
}

// Tri des tableaux admin (ressources / comptes) : trie un tableau deja en memoire et
// re-rend sans re-fetcher le serveur - meme principe que le tri par en-tete du dashboard
// (storage.js applyDashboardSort) mais adapte a des listes chargees une fois.
const adminTableSortState = {
  resource: { field: null, direction: "asc" },
  user: { field: null, direction: "asc" },
};

const ADMIN_SORT_GETTERS = {
  resource: {
    label: (r) => (r.label || "").toLocaleLowerCase("fr"),
    category: (r) => (r.category || "").toLocaleLowerCase("fr"),
    service: (r) => (r.issuer_service || "").toLocaleLowerCase("fr"),
    fields: (r) => (r.field_schema || []).length || 0,
    active: (r) => (r.is_active ? 1 : 0),
  },
  user: {
    username: (u) => (u.username || "").toLocaleLowerCase("fr"),
    service: (u) => (u.service || "").toLocaleLowerCase("fr"),
    status: (u) => (u.status || "").toLocaleLowerCase("fr"),
  },
};

function sortAdminTable(table, items) {
  const state = adminTableSortState[table];
  const getValue = state.field && ADMIN_SORT_GETTERS[table][state.field];
  if (!getValue) {
    return items;
  }
  const sorted = [...items];
  sorted.sort((a, b) => {
    const va = getValue(a);
    const vb = getValue(b);
    const cmp = typeof va === "string" ? va.localeCompare(vb, "fr") : (va || 0) - (vb || 0);
    return state.direction === "asc" ? cmp : -cmp;
  });
  return sorted;
}

function bindAdminSortableHeaders(table, tableBodyId, onSortChange) {
  const thead = byId(tableBodyId)?.closest("table")?.querySelector("thead");
  if (!thead || thead.dataset.sortBound === "true") {
    return;
  }
  thead.addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort-field]");
    if (!th) {
      return;
    }
    const field = th.dataset.sortField;
    const state = adminTableSortState[table];
    state.direction = state.field === field ? (state.direction === "asc" ? "desc" : "asc") : "asc";
    state.field = field;
    thead.querySelectorAll("th[data-sort-field]").forEach((h) => {
      const active = h.dataset.sortField === field;
      h.classList.toggle("is-sorted-asc", active && state.direction === "asc");
      h.classList.toggle("is-sorted-desc", active && state.direction === "desc");
      h.setAttribute("aria-sort", active ? (state.direction === "asc" ? "ascending" : "descending") : "none");
    });
    onSortChange();
  });
  thead.dataset.sortBound = "true";
}

function renderResourceTable() {
  const table = byId("resourceTableBody");
  if (!table) {
    return;
  }
  table.innerHTML = sortAdminTable("resource", currentResources).map((resource) => `
    <tr>
      <td data-label="Ressource">
        <div class="draft-title">${escapeHtml(resource.label)}</div>
        <div class="draft-meta">${escapeHtml(resource.code)}</div>
      </td>
      <td data-label="Catégorie">${escapeHtml(resource.category)}</td>
      <td data-label="Service">${escapeHtml(resource.issuer_service || "-")}</td>
      <td data-label="Suivi">${escapeHtml(formatResourceTrackingSummary(resource))}</td>
      <td data-label="Champs">${escapeHtml(String((resource.field_schema || []).length || 0))}</td>
      <td data-label="État"><span class="status-chip status-chip--${resource.is_active ? "active" : "cancelled"}">${resource.is_active ? "Active" : "Inactive"}</span></td>
      <td data-label="Actions" class="text-end">
        <div class="draft-actions">
          <button class="btn btn-sm btn-outline-primary" type="button" data-admin-action="populateResourceForm" data-id="${escapeHtml(String(resource.id))}">Modifier</button>
          ${renderAdminRowMenu(
            [{ label: resource.is_active ? "Désactiver" : "Activer", attrs: `data-admin-action="toggleResourceState" data-id="${escapeHtml(String(resource.id))}" data-active="${resource.is_active ? "false" : "true"}"` }],
            { label: "Supprimer", attrs: `data-admin-action="deleteResource" data-id="${escapeHtml(String(resource.id))}"` }
          )}
        </div>
      </td>
    </tr>
  `).join("");
}

async function loadResources() {
  currentResources = await adminRequest("/api/admin/resources");
  bindAdminSortableHeaders("resource", "resourceTableBody", renderResourceTable);
  renderResourceTable();
  updateAdminMetrics();
}

async function saveResource() {
  syncResourceCodeFromLabel();
  const payload = {
    code: byId("resource_code")?.value.trim() || "",
    label: byId("resource_label")?.value.trim() || "",
    description: byId("resource_description")?.value.trim() || "",
    category: byId("resource_category")?.value || "materiel",
    issuer_service: byId("resource_issuer")?.value || "",
    requires_return: Boolean(byId("resource_requires_return")?.checked),
    has_assignment_date: Boolean(byId("resource_has_assignment_date")?.checked),
    has_assignment_condition: Boolean(byId("resource_has_assignment_condition")?.checked),
    has_assignment_notes: Boolean(byId("resource_has_assignment_notes")?.checked),
    display_order: Number.parseInt(byId("resource_display_order")?.value || "100", 10) || 100,
    is_active: Boolean(byId("resource_active")?.checked),
    field_schema: collectResourceFieldSchema()
  };
  if (!payload.label) {
    showToast("Le libellé de la ressource est obligatoire.", "error");
    return;
  }
  if (!payload.code) {
    showToast("Le code de la ressource n'a pas pu être généré automatiquement.", "error");
    return;
  }
  await adminRequest("/api/admin/resources", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  resetResourceForm();
  await loadResources();
}

async function toggleResourceState(resourceId, nextState) {
  await adminRequest(`/api/admin/resources/${encodeURIComponent(resourceId)}`, {
    method: "PUT",
    body: JSON.stringify({ is_active: nextState })
  });
  await loadResources();
}

async function deleteResource(resourceId) {
  const resource = currentResources.find((item) => item.id === resourceId);
  const label = resource?.label || "cette ressource";
  const confirmed = await askConfirm(`Supprimer définitivement la ressource "${label}" ?`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" });
  if (!confirmed) {
    return;
  }
  await adminRequest(`/api/admin/resources/${encodeURIComponent(resourceId)}`, {
    method: "DELETE"
  });
  if (editingResourceId === resourceId) {
    closeResourceEditModal();
  }
  await loadResources();
}

async function toggleGroupUnc(groupKey, currentValue) {
  const label = groups[groupKey]?.label || groupKey;
  const enabling = !currentValue;
  const msg = enabling
    ? `Accorder l'accès UNC complet au groupe "${label}" ?`
    : `Retirer l'accès UNC complet au groupe "${label}" ?`;
  const confirmed = await askConfirm(msg, {
    confirmLabel: enabling ? "Accorder" : "Retirer",
    confirmClass: enabling ? "btn-success" : "btn-danger"
  });
  if (!confirmed) return;
  const updated = await adminRequest(`/api/admin/groups/${encodeURIComponent(groupKey)}`, {
    method: "PUT",
    body: JSON.stringify({ "unc.view_all": enabling })
  });
  if (updated) {
    groups = updated;
    renderGroups();
    showToast(enabling ? `Accès UNC accordé au groupe "${label}".` : `Accès UNC retiré au groupe "${label}".`, "success");
  }
}

// Creation "a la demande" : la liste passe en premier, le formulaire s'ouvre via "+ Nouveau ...".
// [data-create-panel] = bloc de champs a replier ; [data-create-section] = carte entiere a replier.
function initAdminCreatePanels() {
  document.querySelectorAll("[data-create-panel], [data-create-section]").forEach((target) => {
    const card = target.closest(".content-card");
    const heading = card?.querySelector(".section-heading");
    if (!card || !heading || heading.querySelector("[data-create-trigger-btn]")) return;
    const isSection = target.hasAttribute("data-create-section");
    const label = target.dataset.createTrigger || "+ Nouveau";
    const trigger = document.createElement("button");
    const isOpen = () => (isSection ? !target.classList.contains("is-collapsed") : !target.classList.contains("d-none"));
    const setOpen = (open) => {
      if (isSection) target.classList.toggle("is-collapsed", !open);
      else target.classList.toggle("d-none", !open);
      trigger.textContent = open ? "Fermer" : label;
      trigger.setAttribute("aria-expanded", String(open));
      if (open) target.querySelector("input, select, textarea")?.focus();
    };
    trigger.type = "button";
    trigger.className = "btn btn-primary ms-auto";
    trigger.dataset.createTriggerBtn = "true";
    trigger.addEventListener("click", () => setOpen(!isOpen()));
    (heading.querySelector(".header-actions") || heading).appendChild(trigger);
    setOpen(false);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initAdminCreatePanels();
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-admin-action]");
    if (!btn) return;
    // Interrupteur : l'etat visuel ne change qu'apres confirmation et enregistrement (re-rendu de la liste).
    if (btn.type === "checkbox") e.preventDefault();
    btn.closest("details.draft-actions__menu")?.removeAttribute("open");
    const action = btn.dataset.adminAction;
    const id = btn.dataset.id;
    const username = btn.dataset.username;
    const active = btn.dataset.active;
    if (action === "approveUser") approveUser(username);
    else if (action === "toggleUserState") toggleUserState(username, active === "true");
    else if (action === "populateUserForm") populateUserForm(username);
    else if (action === "deleteUser") deleteUser(username);
    else if (action === "populateServiceForm") populateServiceForm(id);
    else if (action === "toggleServiceState") toggleServiceState(id, active === "true");
    else if (action === "deleteService") deleteService(id);
    else if (action === "populateResourceForm") populateResourceForm(id);
    else if (action === "toggleResourceState") toggleResourceState(id, active === "true");
    else if (action === "deleteResource") deleteResource(id);
    else if (action === "toggleGroupUnc") toggleGroupUnc(btn.dataset.groupKey, btn.dataset.current === "true");
  });

  try {
    groups = await adminRequest("/api/admin/groups");
    renderGroups();

    if (byId("userFormTitle")) {
      resetUserForm();
    }
    if (byId("serviceFormTitle")) {
      resetServiceForm();
    }
    if (byId("resourceFormTitle")) {
      resetResourceForm();
    }

    await Promise.all([loadUsers(), loadServices(), loadResources()]);

    byId("resource_label")?.addEventListener("input", () => {
      syncResourceCodeFromLabel();
    });
    byId("resource_category")?.addEventListener("change", () => {
      syncResourceTrackingOptions();
    });

    byId("addResourceFieldBtn")?.addEventListener("click", () => {
      appendResourceFieldRow();
    });

    byId("saveUserBtn")?.addEventListener("click", async () => {
      const wasEditingUser = Boolean(editingUsername);
      try {
        await saveUser();
        alert(wasEditingUser ? "Compte mis à jour." : "Utilisateur créé.");
      } catch (error) {
        alert(`Impossible d'enregistrer le compte : ${error.message}`);
      }
    });

    byId("cancelUserEditBtn")?.addEventListener("click", () => {
      resetUserForm();
    });

    // Modal listeners
    byId("modalSaveUserBtn")?.addEventListener("click", async () => {
      await saveUserFromModal();
    });

    document.querySelectorAll("[data-user-modal-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeUserEditModal();
      });
    });

    byId("saveServiceBtn")?.addEventListener("click", async () => {
      try {
        await saveService();
        alert("Service ajouté.");
      } catch (error) {
        alert(`Impossible d'enregistrer le service : ${error.message}`);
      }
    });

    byId("modalSaveServiceBtn")?.addEventListener("click", async () => {
      await saveServiceFromModal();
    });

    document.querySelectorAll("[data-service-modal-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeServiceEditModal();
      });
    });

    byId("csvImportBtn")?.addEventListener("click", () => {
      handleServiceCsvImport();
    });

    byId("saveResourceBtn")?.addEventListener("click", async () => {
      try {
        await saveResource();
        alert("Ressource ajoutée.");
      } catch (error) {
        alert(`Impossible d'enregistrer la ressource : ${error.message}`);
      }
    });

    byId("modalAddResourceFieldBtn")?.addEventListener("click", () => {
      appendResourceFieldRow({}, "modalResourceFieldRows");
    });

    byId("modalResourceCategory")?.addEventListener("change", () => {
      syncResourceTrackingOptions(byId("modalResourceCategory"), byId("modalResourceHasAssignmentCondition"), byId("modalResourceHasAssignmentNotes"));
    });

    byId("modalSaveResourceBtn")?.addEventListener("click", async () => {
      await saveResourceFromModal();
    });

    document.querySelectorAll("[data-resource-modal-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeResourceEditModal();
      });
    });

    initPasswordGeneratorModal();
  } catch (error) {
    console.error(error);
    alert(`Impossible de charger l'administration : ${error.message}`);
  }
});




