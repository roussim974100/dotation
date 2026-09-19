// Destinations de sauvegarde : liste, ajout/edition, test, envoi manuel, historique.
// S'appuie sur admin-db.js et admin-backup.js (getCsrfToken, showDbResult, escapeHtml, backupRequest,
// backupErrorText, backupFormatSize, askConfirm).

const DESTINATION_ERROR_MESSAGES = {
  label_required: "Le nom de la destination est obligatoire.",
  path_required: "Le chemin est obligatoire.",
  path_not_absolute: "Le chemin doit être absolu.",
  path_forbidden: "Ce dossier est réservé à l'application : choisissez un dossier extérieur.",
  path_unreachable: "Dossier introuvable ou partage non monté sur le serveur.",
  path_not_writable: "Le dossier n'est pas inscriptible par le serveur.",
  write_failed: "Écriture impossible vers la destination.",
  verify_failed: "Vérification de la copie échouée.",
  already_exists: "Un fichier de même nom existe déjà.",
  destination_not_found: "Destination introuvable."
};

// Champs du formulaire, definis en objet (un seul endroit pour libelle, type et aide).
const DESTINATION_FIELDS = [
  { key: "label", label: "Nom", type: "text", col: "col-md-4", placeholder: "Ex. NAS de la mairie", required: true },
  { key: "protocol", label: "Type", type: "select", col: "col-md-3", options: [["smb", "Partage SMB / CIFS"], ["nfs", "Partage NFS"], ["local", "Dossier local"]] },
  { key: "path", label: "Chemin sur le serveur", type: "text", col: "col-md-5", placeholder: "/mnt/sauvegardes", required: true }
];

let destinationsState = [];
let destinationProtocols = {};
let destinationEditingId = null;

function destinationFieldHtml(field) {
  const id = `dest_${field.key}`;
  const control = field.type === "select"
    ? `<select class="form-select" id="${id}">${field.options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("")}</select>`
    : `<input class="form-control" id="${id}" type="text" placeholder="${escapeHtml(field.placeholder || "")}"${field.required ? " required" : ""} autocomplete="off">`;
  return `<div class="${field.col}"><label class="form-label" for="${id}">${escapeHtml(field.label)}${field.required ? " *" : ""}</label>${control}</div>`;
}

function destinationLastText(last) {
  if (!last) return '<span class="text-muted">Jamais</span>';
  const when = escapeHtml(new Date(last.ts).toLocaleString("fr-FR"));
  return last.ok
    ? `<span class="status-chip status-chip--active">Réussi</span> <span class="small text-muted">${when}</span>`
    : `<span class="status-chip status-chip--cancelled">Échec</span> <span class="small text-muted">${when}</span><div class="small text-danger">${escapeHtml(last.error || "")}</div>`;
}

function renderDestinations() {
  const body = document.getElementById("destTableBody");
  if (!body) return;
  if (!destinationsState.length) {
    body.innerHTML = `<tr><td colspan="5" class="text-muted">Aucune destination. Ajoutez un partage ou un dossier pour envoyer vos sauvegardes.</td></tr>`;
    return;
  }
  body.innerHTML = destinationsState.map((dest) => `
    <tr>
      <td data-label="Destination"><div class="draft-title">${escapeHtml(dest.label)}</div></td>
      <td data-label="Type">${escapeHtml(destinationProtocols[dest.protocol] || dest.protocol)}</td>
      <td data-label="Chemin"><code>${escapeHtml(dest.path)}</code></td>
      <td data-label="Dernier envoi">${destinationLastText(dest.last)}</td>
      <td data-label="Actions" class="text-end">
        <div class="draft-actions">
          <button class="btn btn-sm btn-primary" type="button" data-dest-action="send" data-id="${escapeHtml(dest.id)}">Envoyer maintenant</button>
          <details class="draft-actions__menu">
            <summary class="btn btn-sm btn-outline-secondary" aria-label="Plus d'actions">⋯</summary>
            <div class="draft-actions__menu-panel">
              <div class="draft-actions__menu-section">
                <button class="btn btn-sm btn-outline-secondary" type="button" data-dest-action="test" data-id="${escapeHtml(dest.id)}">Tester l'accès</button>
                <button class="btn btn-sm btn-outline-secondary" type="button" data-dest-action="edit" data-id="${escapeHtml(dest.id)}">Modifier</button>
              </div>
              <div class="draft-actions__menu-section">
                <button class="btn btn-sm btn-outline-danger" type="button" data-dest-action="delete" data-id="${escapeHtml(dest.id)}">Supprimer</button>
              </div>
            </div>
          </details>
        </div>
      </td>
    </tr>`).join("");
}

async function loadDestinations() {
  try {
    const response = await fetch("/api/admin/backup/destinations", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    destinationsState = data.destinations;
    destinationProtocols = data.protocols;
    renderDestinations();
  } catch (error) {
    showDbResult("destResult", "error", "Impossible de charger les destinations.", "");
  }
}

async function loadBackupHistory() {
  const host = document.getElementById("backupHistoryList");
  if (!host) return;
  try {
    const response = await fetch("/api/admin/backup/history", { credentials: "same-origin", cache: "no-store" });
    const data = await response.json();
    host.innerHTML = data.history.length
      ? `<ul class="list-unstyled mb-0">${data.history.slice(0, 12).map((entry) => `
          <li>${entry.ok ? "✔" : "✖"} ${escapeHtml(new Date(entry.ts).toLocaleString("fr-FR"))} · ${entry.trigger === "scheduled" ? "planifié" : "manuel"} · ${escapeHtml(entry.destination || "")}
            ${entry.ok ? `· <code>${escapeHtml(entry.filename)}</code> · ${backupFormatSize(entry.size)}${entry.encrypted ? " · protégée" : ""}` : `· <span class="text-danger">${escapeHtml(entry.error || "échec")}</span>`}</li>`).join("")}</ul>`
      : "Aucun envoi pour l'instant.";
  } catch (error) {
    host.textContent = "Historique indisponible.";
  }
}

async function saveDestinations(list) {
  const response = await backupRequest("/api/admin/backup/destinations", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ destinations: list.map(({ id, label, protocol, path, enabled }) => ({ id, label, protocol, path, enabled })) })
  });
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch (error) { /* corps non JSON */ }
    throw new Error(DESTINATION_ERROR_MESSAGES[data?.error] || data?.message || `Erreur ${response.status}`);
  }
  const data = await response.json();
  destinationsState = data.destinations;
  renderDestinations();
}

function openDestinationForm(dest) {
  destinationEditingId = dest?.id || null;
  const form = document.getElementById("destForm");
  DESTINATION_FIELDS.forEach((field) => {
    document.getElementById(`dest_${field.key}`).value = dest?.[field.key] ?? (field.key === "protocol" ? "smb" : "");
  });
  document.getElementById("destFormError").classList.add("d-none");
  form.classList.remove("d-none");
  document.getElementById("dest_label").focus();
}

function closeDestinationForm() {
  document.getElementById("destForm").classList.add("d-none");
  destinationEditingId = null;
}

// Modale d'envoi : mot de passe optionnel. Retourne null (annule) ou { password }.
function askSendOptions(destLabel) {
  return new Promise((resolve) => {
    let modal = document.getElementById("backupSendModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.className = "password-generator-modal d-none";
      modal.id = "backupSendModal";
      modal.setAttribute("aria-hidden", "true");
      modal.innerHTML = `
        <div class="password-generator-modal__backdrop" data-send-close="true"></div>
        <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="backupSendTitle">
          <div class="password-generator-modal__header">
            <div><p class="panel-eyebrow">Envoi manuel</p><h2 class="section-title" id="backupSendTitle">Envoyer une sauvegarde</h2></div>
            <button class="btn btn-outline-secondary btn-sm" type="button" data-send-close="true">Fermer</button>
          </div>
          <div class="password-generator-modal__content">
            <p class="mb-0" id="backupSendTarget"></p>
            <div class="form-check"><input class="form-check-input" type="checkbox" id="backupSendProtect" checked><label class="form-check-label" for="backupSendProtect">Protéger par un mot de passe</label></div>
            <div id="backupSendPwdFields" class="row g-3">
              <div class="col-12"><label class="form-label" for="backupSendPassword">Mot de passe</label><input class="form-control" id="backupSendPassword" type="password" autocomplete="new-password"></div>
              <div class="col-12"><label class="form-label" for="backupSendPasswordConfirm">Confirmation</label><input class="form-control" id="backupSendPasswordConfirm" type="password" autocomplete="new-password"></div>
            </div>
            <p class="text-danger small d-none mb-0" id="backupSendError" role="alert"></p>
          </div>
          <div class="password-generator-modal__actions">
            <button class="btn btn-outline-secondary" type="button" data-send-close="true">Annuler</button>
            <button class="btn btn-primary" type="button" id="backupSendConfirm">Envoyer</button>
          </div>
        </div>`;
      document.body.appendChild(modal);
    }
    const protect = modal.querySelector("#backupSendProtect");
    const fields = modal.querySelector("#backupSendPwdFields");
    const error = modal.querySelector("#backupSendError");
    modal.querySelector("#backupSendTarget").textContent = `Destination : ${destLabel}`;
    protect.checked = true;
    fields.classList.remove("d-none");
    modal.querySelector("#backupSendPassword").value = "";
    modal.querySelector("#backupSendPasswordConfirm").value = "";
    error.classList.add("d-none");
    protect.onchange = () => fields.classList.toggle("d-none", !protect.checked);
    const close = (value) => {
      modal.classList.add("d-none");
      modal.setAttribute("aria-hidden", "true");
      resolve(value);
    };
    modal.querySelectorAll("[data-send-close]").forEach((btn) => { btn.onclick = () => close(null); });
    modal.querySelector("#backupSendConfirm").onclick = () => {
      const password = protect.checked ? modal.querySelector("#backupSendPassword").value : "";
      const minLength = Number(document.getElementById("backupMinLength")?.textContent || 8);
      if (protect.checked && password.length < minLength) {
        error.textContent = `Mot de passe trop court (minimum ${minLength} caractères).`;
        error.classList.remove("d-none");
        return;
      }
      if (protect.checked && password !== modal.querySelector("#backupSendPasswordConfirm").value) {
        error.textContent = "Les deux mots de passe ne correspondent pas.";
        error.classList.remove("d-none");
        return;
      }
      close({ password });
    };
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
    modal.querySelector("#backupSendPassword").focus();
  });
}

async function runDestinationAction(action, id) {
  const dest = destinationsState.find((item) => item.id === id);
  if (!dest) return;
  document.querySelectorAll("#destTableBody details[open]").forEach((menu) => menu.removeAttribute("open"));
  if (action === "edit") {
    openDestinationForm(dest);
  } else if (action === "delete") {
    if (!(await askConfirm(`Supprimer la destination « ${dest.label} » ? Les sauvegardes déjà envoyées ne sont pas effacées.`, { confirmLabel: "Supprimer", confirmClass: "btn-danger" }))) return;
    try {
      await saveDestinations(destinationsState.filter((item) => item.id !== id));
      showDbResult("destResult", "ok", "Destination supprimée.", "");
    } catch (error) {
      showDbResult("destResult", "error", error.message, "");
    }
  } else if (action === "test") {
    const response = await backupRequest(`/api/admin/backup/destinations/${encodeURIComponent(id)}/test`, { method: "POST" });
    if (!response.ok) {
      showDbResult("destResult", "error", await backupErrorText(response), "");
      return;
    }
    const result = await response.json();
    showDbResult("destResult", "ok", `Accès validé : « ${dest.label} » est atteignable et inscriptible.`,
      `${result.free_bytes != null ? `Espace libre : ${backupFormatSize(result.free_bytes)} · ` : ""}${result.latency_ms} ms`);
  } else if (action === "send") {
    const options = await askSendOptions(dest.label);
    if (!options) return;
    if (!options.password && !(await askConfirm("Envoyer sans mot de passe ? L'archive contiendra les comptes et toutes les données personnelles en clair sur le partage.", { confirmLabel: "Envoyer sans protection", confirmClass: "btn-danger" }))) return;
    showDbResult("destResult", "info", "Envoi en cours…", "");
    const response = await backupRequest(`/api/admin/backup/destinations/${encodeURIComponent(id)}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: options.password })
    });
    if (!response.ok) {
      showDbResult("destResult", "error", DESTINATION_ERROR_MESSAGES[(await response.clone().json().catch(() => ({}))).error] || await backupErrorText(response), "");
    } else {
      const entry = await response.json();
      showDbResult("destResult", "ok", `Sauvegarde envoyée vers « ${entry.destination} ».`,
        `<code>${escapeHtml(entry.filename)}</code> · ${backupFormatSize(entry.size)}${entry.encrypted ? " · protégée par mot de passe" : ""}`);
    }
    loadDestinations();
    loadBackupHistory();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("destForm");
  if (!form) return;
  document.getElementById("destFormFields").innerHTML = DESTINATION_FIELDS.map(destinationFieldHtml).join("");
  document.getElementById("destAddBtn").addEventListener("click", () => openDestinationForm(null));
  document.getElementById("destCancelBtn").addEventListener("click", closeDestinationForm);
  document.getElementById("destTableBody").addEventListener("click", (event) => {
    const button = event.target.closest("[data-dest-action]");
    if (button) runDestinationAction(button.dataset.destAction, button.dataset.id);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = (key) => document.getElementById(`dest_${key}`).value.trim();
    const entry = { id: destinationEditingId || "", label: value("label"), protocol: value("protocol"), path: value("path"), enabled: true };
    const list = destinationEditingId
      ? destinationsState.map((item) => (item.id === destinationEditingId ? entry : item))
      : [...destinationsState, entry];
    const errorEl = document.getElementById("destFormError");
    try {
      await saveDestinations(list);
      closeDestinationForm();
      showDbResult("destResult", "ok", "Destination enregistrée.", "Utilisez « Tester l'accès » pour vérifier qu'elle est atteignable.");
    } catch (error) {
      errorEl.textContent = error.message;
      errorEl.classList.remove("d-none");
    }
  });
  loadDestinations();
  loadBackupHistory();
});
