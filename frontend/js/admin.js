async function adminRequest(url, options = {}) {
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
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }

  return response.json();
}

let groups = {};
let currentUsers = [];
let currentResources = [];
let editingUsername = null;
let editingResourceId = null;

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

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function slugifyFieldKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function renderGroups() {
  const selector = document.getElementById("groupSelector");
  const cards = document.getElementById("groupCards");

  selector.innerHTML = Object.entries(groups).map(([key, group]) => `
    <label class="choice-chip">
      <input type="checkbox" value="${escapeHtml(key)}" class="admin-group-option">
      <span>${escapeHtml(group.label)}</span>
    </label>
  `).join("");

  cards.innerHTML = Object.entries(groups).map(([key, group]) => `
    <div class="equipment-item">
      <div class="draft-title">${escapeHtml(group.label)}</div>
      <div class="draft-meta">${escapeHtml(group.description || "")}</div>
      <div class="mt-2"><span class="status-chip status-chip--${group.data_scope === "masked" ? "draft" : "active"}">${escapeHtml(group.data_scope)}</span></div>
      <ul class="print-list mt-3">
        ${group.permissions.map((permission) => `<li>${escapeHtml(permission)}</li>`).join("")}
      </ul>
    </div>
  `).join("");
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

function setNotice(elementId, message = "", visible = false) {
  const node = document.getElementById(elementId);
  if (!node) {
    return;
  }
  node.textContent = message;
  node.classList.toggle("d-none", !visible);
}

function createResourceFieldRow(field = {}) {
  return `
    <div class="resource-field-row">
      <div class="row g-3 align-items-end">
        <div class="col-md-4">
          <label class="form-label">Libellé</label>
          <input class="form-control resource-field-label" value="${escapeHtml(field.label || "")}" placeholder="Numéro de série">
        </div>
        <div class="col-md-3">
          <label class="form-label">Clé</label>
          <input class="form-control resource-field-key" value="${escapeHtml(field.key || "")}" placeholder="numero_serie">
        </div>
        <div class="col-md-3">
          <label class="form-label">Type</label>
          <select class="form-select resource-field-type">
            <option value="text" ${field.type === "text" ? "selected" : ""}>Texte</option>
            <option value="email" ${field.type === "email" ? "selected" : ""}>Email</option>
            <option value="tel" ${field.type === "tel" ? "selected" : ""}>Téléphone</option>
          </select>
        </div>
        <div class="col-md-2 d-flex justify-content-md-end">
          <button class="btn btn-outline-danger resource-field-remove" type="button">Suppr.</button>
        </div>
        <div class="col-md-6">
          <label class="form-label">Placeholder</label>
          <input class="form-control resource-field-placeholder" value="${escapeHtml(field.placeholder || "")}" placeholder="SN123456">
        </div>
        <div class="col-md-6">
          <label class="form-check">
            <input class="form-check-input resource-field-required" type="checkbox" ${field.required ? "checked" : ""}>
            <span class="form-check-label">Champ obligatoire</span>
          </label>
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
    const keyInput = row.querySelector(".resource-field-key");
    labelInput?.addEventListener("input", () => {
      if (!keyInput.dataset.manual || !keyInput.value.trim()) {
        keyInput.value = slugifyFieldKey(labelInput.value);
      }
    });
    keyInput?.addEventListener("input", () => {
      keyInput.dataset.manual = keyInput.value.trim() ? "true" : "";
      keyInput.value = slugifyFieldKey(keyInput.value);
    });
    row.querySelector(".resource-field-remove")?.addEventListener("click", () => {
      row.remove();
    });
    row.dataset.bound = "true";
  });
}

function appendResourceFieldRow(field = {}) {
  const container = document.getElementById("resourceFieldRows");
  container.insertAdjacentHTML("beforeend", createResourceFieldRow(field));
  bindResourceFieldRows();
}

function collectResourceFieldSchema() {
  return Array.from(document.querySelectorAll(".resource-field-row")).map((row, index) => {
    const label = row.querySelector(".resource-field-label")?.value.trim() || "";
    const keyInput = row.querySelector(".resource-field-key");
    const key = slugifyFieldKey(keyInput?.value || label || `champ_${index + 1}`);
    if (keyInput) {
      keyInput.value = key;
    }
    return {
      label,
      key,
      type: row.querySelector(".resource-field-type")?.value || "text",
      placeholder: row.querySelector(".resource-field-placeholder")?.value.trim() || "",
      required: Boolean(row.querySelector(".resource-field-required")?.checked)
    };
  }).filter((field) => field.label && field.key);
}

function renderResourceFieldSchema(fields = []) {
  const container = document.getElementById("resourceFieldRows");
  container.innerHTML = "";
  if (!fields.length) {
    appendResourceFieldRow();
    return;
  }
  fields.forEach((field) => appendResourceFieldRow(field));
}

function resetUserForm() {
  editingUsername = null;
  document.getElementById("userFormTitle").textContent = "Nouveau compte";
  document.getElementById("saveUserBtn").textContent = "Créer l'utilisateur";
  document.getElementById("cancelUserEditBtn").classList.add("d-none");
  setNotice("userEditNotice");
  document.getElementById("admin_username").value = "";
  document.getElementById("admin_username").disabled = false;
  document.getElementById("admin_password").value = "";
  document.getElementById("admin_password").placeholder = "Mot de passe temporaire";
  document.getElementById("admin_active").checked = true;
  setSelectedGroups([]);
}

function populateUserForm(username) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user) {
    return;
  }

  editingUsername = user.username;
  document.getElementById("userFormTitle").textContent = `Modifier le compte ${user.username}`;
  document.getElementById("saveUserBtn").textContent = "Enregistrer les modifications";
  document.getElementById("cancelUserEditBtn").classList.remove("d-none");
  setNotice("userEditNotice", "Laissez le mot de passe vide si vous ne souhaitez pas le modifier.", true);
  document.getElementById("admin_username").value = user.username;
  document.getElementById("admin_username").disabled = true;
  document.getElementById("admin_password").value = "";
  document.getElementById("admin_password").placeholder = "Nouveau mot de passe (optionnel)";
  document.getElementById("admin_active").checked = Boolean(user.is_active);
  if (user.status === "pending") {
    setNotice("userEditNotice", "Ce compte est en attente. Vous pouvez le valider ou ajuster ses groupes avant activation.", true);
  }
  setSelectedGroups(user.groups || []);
}

function resetResourceForm() {
  editingResourceId = null;
  document.getElementById("resourceFormTitle").textContent = "Ressources attribuables";
  document.getElementById("saveResourceBtn").textContent = "Ajouter la ressource";
  document.getElementById("cancelResourceEditBtn").classList.add("d-none");
  setNotice("resourceEditNotice");
  document.getElementById("resource_code").value = "";
  document.getElementById("resource_label").value = "";
  document.getElementById("resource_category").value = "materiel";
  document.getElementById("resource_issuer").value = "";
  document.getElementById("resource_requires_return").checked = true;
  document.getElementById("resource_active").checked = true;
  renderResourceFieldSchema([]);
}

function populateResourceForm(resourceId) {
  const resource = currentResources.find((item) => item.id === resourceId);
  if (!resource) {
    return;
  }

  editingResourceId = resource.id;
  document.getElementById("resourceFormTitle").textContent = `Modifier la ressource ${resource.label}`;
  document.getElementById("saveResourceBtn").textContent = "Enregistrer les modifications";
  document.getElementById("cancelResourceEditBtn").classList.remove("d-none");
  setNotice("resourceEditNotice", "Définissez ici les champs qui devront être renseignés quand la ressource est attribuée.", true);
  document.getElementById("resource_code").value = resource.code || "";
  document.getElementById("resource_label").value = resource.label || "";
  document.getElementById("resource_category").value = resource.category || "materiel";
  document.getElementById("resource_issuer").value = resource.issuer_service || "";
  document.getElementById("resource_requires_return").checked = Boolean(resource.requires_return);
  document.getElementById("resource_active").checked = Boolean(resource.is_active);
  renderResourceFieldSchema(resource.field_schema || []);
}

async function loadUsers() {
  currentUsers = await adminRequest("/api/admin/users");
  document.getElementById("userTableBody").innerHTML = currentUsers.map((user) => `
    <tr>
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(user.groups.join(", ") || "-")}</td>
      <td><span class="status-chip status-chip--${user.is_active ? "active" : "cancelled"}">${user.is_active ? "Actif" : "Désactivé"}</span></td>
      <td class="text-end">
        <div class="draft-actions">
          <button class="btn btn-sm btn-outline-primary" type="button" onclick="populateUserForm('${escapeHtml(user.username)}')">Modifier</button>
          <button class="btn btn-sm btn-outline-secondary" type="button" onclick="toggleUserState('${escapeHtml(user.username)}', ${user.is_active ? "false" : "true"})">${user.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteUser('${escapeHtml(user.username)}')">Supprimer</button>
        </div>
      </td>
    </tr>
  `).join("");
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
      is_active: nextState
    })
  });
  await loadUsers();
}

async function saveUser() {
  const username = document.getElementById("admin_username").value.trim();
  const password = document.getElementById("admin_password").value;
  const isActive = document.getElementById("admin_active").checked;
  const selectedGroups = getSelectedGroups();

  if (!editingUsername) {
    await adminRequest("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
        groups: selectedGroups,
        is_active: isActive
      })
    });
  } else {
    await adminRequest(`/api/admin/users/${encodeURIComponent(editingUsername)}`, {
      method: "PUT",
      body: JSON.stringify({
        groups: selectedGroups,
        is_active: isActive,
        password
      })
    });
  }

  resetUserForm();
  await loadUsers();
}

async function deleteUser(username) {
  const confirmed = window.confirm(`Supprimer définitivement le compte "${username}" ?`);
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

async function loadResources() {
  currentResources = await adminRequest("/api/admin/resources");
  document.getElementById("resourceTableBody").innerHTML = currentResources.map((resource) => `
    <tr>
      <td>
        <div class="draft-title">${escapeHtml(resource.label)}</div>
        <div class="draft-meta">${escapeHtml(resource.code)}</div>
      </td>
      <td>${escapeHtml(resource.category)}</td>
      <td>${escapeHtml(resource.issuer_service || "-")}</td>
      <td>${escapeHtml(String((resource.field_schema || []).length || 0))}</td>
      <td><span class="status-chip status-chip--${resource.is_active ? "active" : "cancelled"}">${resource.is_active ? "Active" : "Inactive"}</span></td>
      <td class="text-end">
        <div class="draft-actions">
          <button class="btn btn-sm btn-outline-primary" type="button" onclick="populateResourceForm('${escapeHtml(resource.id)}')">Modifier</button>
          <button class="btn btn-sm btn-outline-secondary" type="button" onclick="toggleResourceState('${escapeHtml(resource.id)}', ${resource.is_active ? "false" : "true"})">${resource.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteResource('${escapeHtml(resource.id)}')">Supprimer</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function saveResource() {
  const payload = {
    code: document.getElementById("resource_code").value.trim(),
    label: document.getElementById("resource_label").value.trim(),
    category: document.getElementById("resource_category").value,
    issuer_service: document.getElementById("resource_issuer").value.trim(),
    requires_return: document.getElementById("resource_requires_return").checked,
    is_active: document.getElementById("resource_active").checked,
    field_schema: collectResourceFieldSchema()
  };

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
    body: JSON.stringify({
      is_active: nextState
    })
  });
  await loadResources();
}

async function deleteResource(resourceId) {
  const resource = currentResources.find((item) => item.id === resourceId);
  const label = resource?.label || "cette ressource";
  const confirmed = window.confirm(`Supprimer définitivement la ressource "${label}" ?`);
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

function validatePasswordComplexity(password) {
  if (!password) {
    return null;
  }
  if (password.length < 12) {
    return "Le mot de passe doit contenir au moins 12 caracteres.";
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
    return "Le mot de passe doit contenir au moins un caractere special.";
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
    publier: {
      first: ["Publier", "Leman", "Mairie", "Alpes", "Geneve", "Rive", "Port", "Chablais"],
      second: ["lac", "maison", "service", "rivage", "commune", "montagne", "horizon", "village"]
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

function initPasswordGeneratorModal(options) {
  const modal = document.getElementById("passwordGeneratorModal");
  if (!modal) {
    return;
  }

  const themeSelect = document.getElementById("passwordThemeSelect");
  const valueField = document.getElementById("generatedPasswordValue");
  const refreshBtn = document.getElementById("refreshGeneratedPasswordBtn");
  const copyBtn = document.getElementById("copyGeneratedPasswordBtn");
  const applyBtn = document.getElementById("applyGeneratedPasswordBtn");
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
    options.onApply(currentPassword);
    closeModal();
  });
  modal.querySelectorAll("[data-password-modal-close='true']").forEach((element) => {
    element.addEventListener("click", closeModal);
  });

  document.getElementById("generateAdminPasswordBtn")?.addEventListener("click", openModal);
}

async function loadUsers() {
  currentUsers = await adminRequest("/api/admin/users");
  document.getElementById("userTableBody").innerHTML = currentUsers.map((user) => {
    const statusMeta = getUserStatusMeta(user);
    const statusAction = user.status === "pending"
      ? `<button class="btn btn-sm btn-outline-success" type="button" onclick="approveUser('${escapeHtml(user.username)}')">Valider</button>`
      : `<button class="btn btn-sm btn-outline-secondary" type="button" onclick="toggleUserState('${escapeHtml(user.username)}', ${user.is_active ? "false" : "true"})">${user.is_active ? "Desactiver" : "Activer"}</button>`;

    return `
      <tr>
        <td>${escapeHtml(user.username)}</td>
        <td>${escapeHtml(user.groups.join(", ") || "-")}</td>
        <td><span class="status-chip status-chip--${statusMeta.code}">${statusMeta.label}</span></td>
        <td class="text-end">
          <div class="draft-actions">
            <button class="btn btn-sm btn-outline-primary" type="button" onclick="populateUserForm('${escapeHtml(user.username)}')">Modifier</button>
            ${statusAction}
            <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteUser('${escapeHtml(user.username)}')">Supprimer</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function populateUserForm(username) {
  const user = currentUsers.find((item) => item.username === username);
  if (!user) {
    return;
  }

  editingUsername = user.username;
  document.getElementById("userFormTitle").textContent = `Modifier le compte ${user.username}`;
  document.getElementById("saveUserBtn").textContent = "Enregistrer les modifications";
  document.getElementById("cancelUserEditBtn").classList.remove("d-none");
  setNotice(
    "userEditNotice",
    user.status === "pending"
      ? "Ce compte est en attente. Vous pouvez le valider ou ajuster ses groupes avant activation."
      : "Laissez le mot de passe vide si vous ne souhaitez pas le modifier.",
    true
  );
  document.getElementById("admin_username").value = user.username;
  document.getElementById("admin_username").disabled = true;
  document.getElementById("admin_password").value = "";
  document.getElementById("admin_password").placeholder = "Nouveau mot de passe (optionnel)";
  document.getElementById("admin_active").checked = user.status !== "disabled";
  setSelectedGroups(user.groups || []);
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

async function saveUser() {
  const username = document.getElementById("admin_username").value.trim();
  const password = document.getElementById("admin_password").value;
  const isActive = document.getElementById("admin_active").checked;
  const selectedGroups = getSelectedGroups();
  const passwordError = validatePasswordComplexity(password);

  if (!editingUsername && !password) {
    window.alert("Le mot de passe est obligatoire.");
    return;
  }
  if (passwordError) {
    window.alert(passwordError);
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

document.addEventListener("DOMContentLoaded", async () => {
  groups = await adminRequest("/api/admin/groups");
  renderGroups();
  resetUserForm();
  resetResourceForm();
  await Promise.all([loadUsers(), loadResources()]);

  document.getElementById("addResourceFieldBtn").addEventListener("click", () => {
    appendResourceFieldRow();
  });

  document.getElementById("saveUserBtn").addEventListener("click", async () => {
    const wasEditingUser = Boolean(editingUsername);
    try {
      await saveUser();
      alert(wasEditingUser ? "Compte mis à jour." : "Utilisateur créé.");
    } catch (error) {
      alert(`Impossible d'enregistrer le compte : ${error.message}`);
    }
  });

  document.getElementById("cancelUserEditBtn").addEventListener("click", () => {
    resetUserForm();
  });

  initPasswordGeneratorModal({
    onApply(password) {
      document.getElementById("admin_password").value = password;
    }
  });

  document.getElementById("saveResourceBtn").addEventListener("click", async () => {
    const wasEditingResource = Boolean(editingResourceId);
    try {
      await saveResource();
      alert(wasEditingResource ? "Ressource mise à jour." : "Ressource ajoutée.");
    } catch (error) {
      alert(`Impossible d'enregistrer la ressource : ${error.message}`);
    }
  });

  document.getElementById("cancelResourceEditBtn").addEventListener("click", () => {
    resetResourceForm();
  });
});
