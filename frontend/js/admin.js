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

function syncResourceCodeFromLabel(force = false) {
  const labelInput = byId("resource_label");
  const codeInput = byId("resource_code");
  if (!labelInput || !codeInput) {
    return;
  }
  if (!force && codeInput.dataset.manual === "true") {
    return;
  }
  codeInput.value = slugifyFieldKey(labelInput.value);
}

function renderResourceIssuerOptions(selectedValue = "") {
  const select = byId("resource_issuer");
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

function syncResourceTrackingOptions() {
  const category = byId("resource_category")?.value || "materiel";
  const conditionInput = byId("resource_has_assignment_condition");
  const notesInput = byId("resource_has_assignment_notes");
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

function renderResourceDisplayOrderOptions(selectedValue = 60) {
  const select = byId("resource_display_order");
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
  if (pendingCount) {
    pendingCount.textContent = String(currentUsers.filter((user) => user.status === "pending").length);
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
  const cards = byId("groupCards");

  if (selector) {
    selector.innerHTML = Object.entries(groups).map(([key, group]) => `
      <label class="choice-chip">
        <input type="checkbox" value="${escapeHtml(key)}" class="admin-group-option">
        <span>${escapeHtml(group.label)}</span>
      </label>
    `).join("");
  }

  if (cards) {
    cards.innerHTML = Object.entries(groups).map(([key, group]) => `
      <div class="equipment-item">
        <div class="draft-title">${escapeHtml(group.label)}</div>
        <div class="draft-meta">${escapeHtml(group.description || "")}</div>
        <div class="mt-2"><span class="status-chip status-chip--${group.data_scope === "masked" ? "draft" : "active"}">${escapeHtml(group.data_scope)}</span></div>
        <ul class="print-list mt-3">
          ${(group.permissions || []).map((permission) => `<li>${escapeHtml(permission)}</li>`).join("")}
        </ul>
      </div>
    `).join("");
  }
}

function getSelectedGroups() {
  return Array.from(document.querySelectorAll(".admin-group-option:checked")).map((input) => input.value);
}

function setSelectedGroups(selectedGroups) {
  const selectedSet = new Set(selectedGroups || []);
  document.querySelectorAll(".admin-group-option").forEach((input) => {
    input.checked = selectedSet.has(input.value);
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
  setSelectedGroups([]);
}

function populateUserForm(username) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user || !byId("userFormTitle")) {
    return;
  }

  editingUsername = user.username;
  byId("userFormTitle").textContent = `Modifier le compte ${user.username}`;
  byId("saveUserBtn").textContent = "Enregistrer les modifications";
  byId("cancelUserEditBtn").classList.remove("d-none");
  setNotice(
    "userEditNotice",
    user.status === "pending"
      ? "Ce compte est en attente. Vous pouvez le valider ou ajuster ses groupes avant activation."
      : "Laissez le mot de passe vide si vous ne souhaitez pas le modifier.",
    true
  );
  byId("admin_username").value = user.username;
  byId("admin_username").disabled = true;
  byId("admin_password").value = "";
  byId("admin_password").placeholder = "Nouveau mot de passe (optionnel)";
  byId("admin_active").checked = user.status !== "disabled";
  setSelectedGroups(user.groups || []);
}

function createResourceFieldRow(field = {}) {
  const optionsValue = Array.isArray(field.options) ? field.options.join("\n") : "";
  const showOptions = field.type === "select";
  return `
    <div class="resource-field-row">
      <div class="row g-3 align-items-end">
        <div class="col-md-5">
          <label class="form-label">Libellé</label>
          <input class="form-control resource-field-label" value="${escapeHtml(field.label || "")}" placeholder="Numéro de série">
        </div>
        <div class="col-md-4">
          <label class="form-label">Type</label>
          <select class="form-select resource-field-type">
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
            <input class="form-check-input resource-field-required" type="checkbox" ${field.required ? "checked" : ""}>
            <span class="form-check-label">Champ obligatoire</span>
          </label>
        </div>
        <div class="col-12 resource-field-options ${showOptions ? "" : "d-none"}">
          <label class="form-label">Choix de la liste</label>
          <textarea class="form-control resource-field-options-input" rows="3" placeholder="Une option par ligne">${escapeHtml(optionsValue)}</textarea>
          <div class="form-text">Ajoutez une valeur par ligne pour la liste déroulante.</div>
        </div>
        <div class="col-12 d-flex justify-content-md-end">
          <button class="btn btn-outline-danger resource-field-remove" type="button">Suppr.</button>
        </div>
      </div>
    </div>
  `;
}

function bindResourceFieldRows() {
  document.querySelectorAll(".resource-field-row").forEach((row) => {
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
      row.remove();
    });
    row.dataset.bound = "true";
  });
}

function appendResourceFieldRow(field = {}) {
  const container = byId("resourceFieldRows");
  if (!container) {
    return;
  }
  container.insertAdjacentHTML("beforeend", createResourceFieldRow(field));
  bindResourceFieldRows();
}

function collectResourceFieldSchema() {
  return Array.from(document.querySelectorAll(".resource-field-row")).map((row, index) => {
    const label = row.querySelector(".resource-field-label")?.value.trim() || "";
    const key = slugifyFieldKey(label || `champ_${index + 1}`);
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
      options
    };
  }).filter((field) => field.label && field.key);
}

function renderResourceFieldSchema(fields = []) {
  const container = byId("resourceFieldRows");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  fields.forEach((field) => appendResourceFieldRow(field));
}

function resetServiceForm() {
  if (!byId("serviceFormTitle")) {
    return;
  }
  editingServiceId = null;
  byId("serviceFormTitle").textContent = "Services";
  byId("saveServiceBtn").textContent = "Ajouter le service";
  byId("cancelServiceEditBtn").classList.add("d-none");
  setNotice("serviceEditNotice");
  byId("service_label").value = "";
  byId("service_active").checked = true;
}

function populateServiceForm(serviceId) {
  const service = currentServices.find((item) => item.id === serviceId);
  if (!service || !byId("serviceFormTitle")) {
    return;
  }
  editingServiceId = service.id;
  byId("serviceFormTitle").textContent = `Modifier le service ${service.label}`;
  byId("saveServiceBtn").textContent = "Enregistrer les modifications";
  byId("cancelServiceEditBtn").classList.remove("d-none");
  setNotice("serviceEditNotice", "Mettez à jour le libellé ou désactivez le service sans perdre l'historique des dossiers.", true);
  byId("service_label").value = service.label || "";
  byId("service_active").checked = Boolean(service.is_active);
}

function resetResourceForm() {
  if (!byId("resourceFormTitle")) {
    return;
  }
  editingResourceId = null;
  byId("resourceFormTitle").textContent = "Ressources attribuables";
  byId("saveResourceBtn").textContent = "Ajouter la ressource";
  byId("cancelResourceEditBtn").classList.add("d-none");
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
  if (!resource || !byId("resourceFormTitle")) {
    return;
  }
  editingResourceId = resource.id;
  byId("resourceFormTitle").textContent = `Modifier la ressource ${resource.label}`;
  byId("saveResourceBtn").textContent = "Enregistrer les modifications";
  byId("cancelResourceEditBtn").classList.remove("d-none");
  setNotice("resourceEditNotice", "Définissez ici les champs qui devront être renseignés quand la ressource est attribuée.", true);
  byId("resource_code").value = resource.code || "";
  byId("resource_code").dataset.manual = "true";
  byId("resource_label").value = resource.label || "";
  byId("resource_category").value = resource.category || "materiel";
  renderResourceIssuerOptions(resource.issuer_service || "");
  byId("resource_description").value = resource.description || "";
  renderResourceDisplayOrderOptions(resource.display_order || 60);
  byId("resource_requires_return").checked = Boolean(resource.requires_return);
  byId("resource_active").checked = Boolean(resource.is_active);
  byId("resource_has_assignment_date").checked = resource.has_assignment_date !== false;
  byId("resource_has_assignment_condition").checked = Boolean(resource.has_assignment_condition);
  byId("resource_has_assignment_notes").checked = resource.has_assignment_notes !== false;
  syncResourceTrackingOptions();
  renderResourceFieldSchema(resource.field_schema || []);
}

async function loadUsers() {
  if (!byId("userTableBody")) {
    currentUsers = await adminRequest("/api/admin/users");
    updateAdminMetrics();
    return;
  }
  currentUsers = await adminRequest("/api/admin/users");
  byId("userTableBody").innerHTML = currentUsers.map((user) => {
    const statusMeta = getUserStatusMeta(user);
    const statusAction = user.status === "pending"
      ? `<button class="btn btn-sm btn-outline-success" type="button" data-admin-action="approveUser" data-username="${escapeHtml(user.username)}">Valider</button>`
      : `<button class="btn btn-sm btn-outline-secondary" type="button" data-admin-action="toggleUserState" data-username="${escapeHtml(user.username)}" data-active="${user.is_active ? "false" : "true"}">${user.is_active ? "Desactiver" : "Activer"}</button>`;
    return `
      <tr>
        <td data-label="Utilisateur">${escapeHtml(user.username)}</td>
        <td data-label="Groupes">${escapeHtml((user.groups || []).join(", ") || "-")}</td>
        <td data-label="État"><span class="status-chip status-chip--${statusMeta.code}">${statusMeta.label}</span></td>
        <td data-label="Actions" class="text-end">
          <div class="draft-actions">
            <button class="btn btn-sm btn-outline-primary" type="button" data-admin-action="populateUserForm" data-username="${escapeHtml(user.username)}">Modifier</button>
            ${statusAction}
            <button class="btn btn-sm btn-outline-danger" type="button" data-admin-action="deleteUser" data-username="${escapeHtml(user.username)}">Supprimer</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
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

  if (!editingUsername) {
    await adminRequest("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
        groups: selectedGroups,
        is_active: isActive,
        status: isActive ? "active" : "disabled"
      })
    });
  } else {
    await adminRequest(`/api/admin/users/${encodeURIComponent(editingUsername)}`, {
      method: "PUT",
      body: JSON.stringify({
        groups: selectedGroups,
        is_active: isActive,
        status: isActive ? "active" : "disabled",
        password
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

async function loadServices() {
  currentServices = await adminRequest("/api/admin/services");
  renderResourceIssuerOptions(byId("resource_issuer")?.value || "");
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
          <button class="btn btn-sm btn-outline-secondary" type="button" data-admin-action="toggleServiceState" data-id="${escapeHtml(String(service.id))}" data-active="${service.is_active ? "false" : "true"}">${service.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn btn-sm btn-outline-danger" type="button" data-admin-action="deleteService" data-id="${escapeHtml(String(service.id))}">Supprimer</button>
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
  if (!editingServiceId) {
    await adminRequest("/api/admin/services", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  } else {
    await adminRequest(`/api/admin/services/${encodeURIComponent(editingServiceId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  }
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
    resetServiceForm();
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

async function loadResources() {
  currentResources = await adminRequest("/api/admin/resources");
  const table = byId("resourceTableBody");
  if (!table) {
    updateAdminMetrics();
    return;
  }
  table.innerHTML = currentResources.map((resource) => `
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
          <button class="btn btn-sm btn-outline-secondary" type="button" data-admin-action="toggleResourceState" data-id="${escapeHtml(String(resource.id))}" data-active="${resource.is_active ? "false" : "true"}">${resource.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn btn-sm btn-outline-danger" type="button" data-admin-action="deleteResource" data-id="${escapeHtml(String(resource.id))}">Supprimer</button>
        </div>
      </td>
    </tr>
  `).join("");
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
  if (!editingResourceId) {
    await adminRequest("/api/admin/resources", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  } else {
    await adminRequest(`/api/admin/resources/${encodeURIComponent(editingResourceId)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  }
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
    resetResourceForm();
  }
  await loadResources();
}

document.addEventListener("DOMContentLoaded", async () => {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-admin-action]");
    if (!btn) return;
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

    byId("saveServiceBtn")?.addEventListener("click", async () => {
      const wasEditingService = Boolean(editingServiceId);
      try {
        await saveService();
        alert(wasEditingService ? "Service mis à jour." : "Service ajouté.");
      } catch (error) {
        alert(`Impossible d'enregistrer le service : ${error.message}`);
      }
    });

    byId("cancelServiceEditBtn")?.addEventListener("click", () => {
      resetServiceForm();
    });

    byId("csvImportBtn")?.addEventListener("click", () => {
      handleServiceCsvImport();
    });

    byId("saveResourceBtn")?.addEventListener("click", async () => {
      const wasEditingResource = Boolean(editingResourceId);
      try {
        await saveResource();
        alert(wasEditingResource ? "Ressource mise à jour." : "Ressource ajoutée.");
      } catch (error) {
        alert(`Impossible d'enregistrer la ressource : ${error.message}`);
      }
    });

    byId("cancelResourceEditBtn")?.addEventListener("click", () => {
      resetResourceForm();
    });

    initPasswordGeneratorModal();
  } catch (error) {
    console.error(error);
    alert(`Impossible de charger l'administration : ${error.message}`);
  }
});




