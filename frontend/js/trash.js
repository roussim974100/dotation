async function trashRequest(url, options = {}) {
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

let trashItems = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("fr-FR");
}

function formatTrashType(type) {
  const labels = {
    form: "Dossier",
    user: "Utilisateur",
    resource: "Ressource"
  };
  return labels[type] || type || "-";
}

function getFilteredTrash() {
  const search = (document.getElementById("trashSearchInput")?.value || "").trim().toLowerCase();
  const type = document.getElementById("trashTypeFilter")?.value || "";
  return trashItems.filter((item) => {
    const matchesType = !type || item.item_type === type;
    const haystack = [
      item.item_label,
      item.item_key,
      item.deleted_by,
      item.item_type
    ].join(" ").toLowerCase();
    const matchesSearch = !search || haystack.includes(search);
    return matchesType && matchesSearch;
  });
}

function renderTrash() {
  const rows = getFilteredTrash();
  document.getElementById("trashCount").textContent = String(rows.length);
  document.getElementById("trashEmptyState").classList.toggle("d-none", rows.length !== 0);
  document.getElementById("trashTableBody").innerHTML = rows.map((item) => `
    <tr class="draft-row">
      <td data-label="Date">${escapeHtml(formatDateTime(item.deleted_at))}</td>
      <td data-label="Type">${escapeHtml(formatTrashType(item.item_type))}</td>
      <td data-label="Élément">
        <div class="draft-title">${escapeHtml(item.item_label || item.item_key)}</div>
        <div class="draft-meta">${escapeHtml(item.item_key)}</div>
      </td>
      <td data-label="Supprimé par">${escapeHtml(item.deleted_by || "-")}</td>
      <td data-label="Actions" class="draft-actions-cell">
        <div class="draft-actions">
          <button class="btn btn-sm btn-outline-primary" type="button" onclick="restoreTrashItem('${escapeHtml(item.id)}')">Restaurer</button>
          <button class="btn btn-sm btn-outline-danger" type="button" onclick="deleteTrashItem('${escapeHtml(item.id)}')">Supprimer</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function loadTrash() {
  trashItems = await trashRequest("/api/admin/trash");
  renderTrash();
}

async function restoreTrashItem(trashId) {
  const confirmed = window.confirm("Restaurer cet élément depuis la corbeille ?");
  if (!confirmed) {
    return;
  }
  await trashRequest(`/api/admin/trash/${encodeURIComponent(trashId)}/restore`, {
    method: "POST"
  });
  await loadTrash();
}

async function deleteTrashItem(trashId) {
  const confirmed = window.confirm("Supprimer définitivement cet élément de la corbeille ? Cette action est irréversible.");
  if (!confirmed) {
    return;
  }
  await trashRequest(`/api/admin/trash/${encodeURIComponent(trashId)}`, {
    method: "DELETE"
  });
  await loadTrash();
}

async function emptyTrash() {
  if (!trashItems.length) {
    window.alert("La corbeille est déjà vide.");
    return;
  }
  const confirmed = window.confirm("Vider toute la corbeille ? Toutes les copies de restauration seront supprimées définitivement.");
  if (!confirmed) {
    return;
  }
  const result = await trashRequest("/api/admin/trash", {
    method: "DELETE"
  });
  await loadTrash();
  if (result.deleted_count) {
    window.alert(`Corbeille vidée : ${result.deleted_count} élément(s) supprimé(s) définitivement.`);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadTrash();
  } catch (error) {
    alert(`Impossible de charger la corbeille : ${error.message}`);
  }

  document.getElementById("trashSearchInput")?.addEventListener("input", renderTrash);
  document.getElementById("trashTypeFilter")?.addEventListener("change", renderTrash);
  document.getElementById("refreshTrashBtn")?.addEventListener("click", async () => {
    try {
      await loadTrash();
    } catch (error) {
      alert(`Impossible de rafraîchir la corbeille : ${error.message}`);
    }
  });
  document.getElementById("emptyTrashBtn")?.addEventListener("click", async () => {
    try {
      await emptyTrash();
    } catch (error) {
      alert(`Impossible de vider la corbeille : ${error.message}`);
    }
  });
});

// Gère la corbeille applicative :
// recherche, filtrage, restauration et suppression définitive des éléments supprimés.
