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

let currentResources = [];
let draggedItemId = null;
let selectedServiceFilter = "__all__";

function setNotice(message = "", isVisible = false, isError = false) {
  const notice = byId("resourceOrderNotice");
  if (!notice) {
    return;
  }
  notice.textContent = message;
  notice.className = `alert ${isError ? "alert-danger" : "alert-info"}${isVisible ? "" : " d-none"}`;
}

function getCategoryLabel(category) {
  return category === "immateriel" ? "Immatériel" : "Matériel";
}

function getIssuerLabel(resource) {
  return String(resource?.issuer_service || "").trim() || "Sans service";
}

function updateCount(visibleCount = currentResources.length) {
  const count = byId("resourceOrderCount");
  if (count) {
    count.textContent = String(visibleCount);
  }
}

function buildServiceGroups(resources) {
  const groups = new Map();
  resources.forEach((resource) => {
    const label = getIssuerLabel(resource);
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label).push(resource);
  });
  return Array.from(groups.entries())
    .sort((left, right) => left[0].localeCompare(right[0], "fr"))
    .map(([label, items]) => ({ label, items }));
}

function getVisibleServiceGroups() {
  const source = selectedServiceFilter === "__all__"
    ? currentResources
    : currentResources.filter((resource) => getIssuerLabel(resource) === selectedServiceFilter);
  return buildServiceGroups(source);
}

function renderServiceFilters() {
  const container = byId("resourceOrderServiceFilters");
  if (!container) {
    return;
  }

  const serviceLabels = [...new Set(currentResources.map((resource) => getIssuerLabel(resource)))]
    .sort((left, right) => left.localeCompare(right, "fr"));

  if (selectedServiceFilter !== "__all__" && !serviceLabels.includes(selectedServiceFilter)) {
    selectedServiceFilter = "__all__";
  }

  const allOptions = [{ value: "__all__", label: "Tous les services" }, ...serviceLabels.map((label) => ({ value: label, label }))];
  container.innerHTML = allOptions.map((option) => `
    <label class="choice-chip">
      <input type="radio" name="resource_order_service_filter" value="${escapeHtml(option.value)}" ${selectedServiceFilter === option.value ? "checked" : ""}>
      <span>${escapeHtml(option.label)}</span>
    </label>
  `).join("");

  container.querySelectorAll('input[name="resource_order_service_filter"]').forEach((input) => {
    input.addEventListener("change", () => {
      selectedServiceFilter = input.value;
      renderResources();
    });
  });
}

function moveResourceBeforeTarget(draggedId, targetId) {
  const draggedIndex = currentResources.findIndex((resource) => resource.id === draggedId);
  const targetIndex = currentResources.findIndex((resource) => resource.id === targetId);
  if (draggedIndex < 0 || targetIndex < 0 || draggedIndex === targetIndex) {
    return false;
  }
  const [movedResource] = currentResources.splice(draggedIndex, 1);
  const adjustedTargetIndex = currentResources.findIndex((resource) => resource.id === targetId);
  currentResources.splice(adjustedTargetIndex, 0, movedResource);
  return true;
}

function bindDragAndDrop(root) {
  root.querySelectorAll(".resource-order-item").forEach((item) => {
    item.addEventListener("dragstart", (event) => {
      draggedItemId = item.dataset.resourceId || null;
      item.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", draggedItemId || "");
    });

    item.addEventListener("dragend", () => {
      draggedItemId = null;
      item.classList.remove("is-dragging");
      root.querySelectorAll(".resource-order-item").forEach((node) => node.classList.remove("is-drag-over"));
    });

    item.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!draggedItemId || draggedItemId === item.dataset.resourceId) {
        return;
      }
      item.classList.add("is-drag-over");
      event.dataTransfer.dropEffect = "move";
    });

    item.addEventListener("dragleave", () => {
      item.classList.remove("is-drag-over");
    });

    item.addEventListener("drop", (event) => {
      event.preventDefault();
      item.classList.remove("is-drag-over");
      const targetId = item.dataset.resourceId || "";
      if (!draggedItemId || !targetId || draggedItemId === targetId) {
        return;
      }
      if (moveResourceBeforeTarget(draggedItemId, targetId)) {
        renderResources();
        setNotice("L'ordre a été modifié localement. N'oubliez pas d'enregistrer.", true, false);
      }
    });
  });
}

function renderResources() {
  const list = byId("resourceOrderList");
  const emptyState = byId("resourceOrderEmpty");
  if (!list || !emptyState) {
    return;
  }

  const groups = getVisibleServiceGroups();
  const visibleCount = groups.reduce((total, group) => total + group.items.length, 0);
  updateCount(visibleCount);

  if (!visibleCount) {
    list.innerHTML = "";
    emptyState.classList.remove("d-none");
    return;
  }

  emptyState.classList.add("d-none");
  list.innerHTML = groups.map((group) => `
    <section class="resource-order-group">
      <div class="resource-order-group__header">
        <div>
          <p class="panel-eyebrow">${escapeHtml(group.label)}</p>
          <h3 class="section-title">Ressources du service ${escapeHtml(group.label)}</h3>
        </div>
        <span class="status-pill">${group.items.length} ressource(s)</span>
      </div>
      <div class="resource-order-group__list">
        ${group.items.map((resource, index) => `
          <div class="resource-order-item" draggable="true" data-resource-id="${escapeHtml(resource.id)}">
            <div class="resource-order-item__handle" aria-hidden="true">::</div>
            <div class="resource-order-item__position">${index + 1}</div>
            <div class="resource-order-item__content">
              <div class="draft-title">${escapeHtml(resource.label)}</div>
              <div class="draft-meta">${escapeHtml(getCategoryLabel(resource.category))} · ${escapeHtml(resource.description || "Sans description")}</div>
            </div>
            <div class="resource-order-item__status">
              <span class="status-chip status-chip--${resource.is_active ? "active" : "cancelled"}">${resource.is_active ? "Active" : "Inactive"}</span>
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `).join("");

  bindDragAndDrop(list);
}

async function loadResources() {
  currentResources = await adminRequest("/api/admin/resources");
  renderServiceFilters();
  renderResources();
}

function buildUpdatePayload(resource, displayOrder) {
  return {
    code: resource.code,
    label: resource.label,
    description: resource.description || "",
    category: resource.category || "materiel",
    issuer_service: resource.issuer_service || "",
    requires_return: Boolean(resource.requires_return),
    has_assignment_date: resource.has_assignment_date !== false,
    has_assignment_condition: Boolean(resource.has_assignment_condition),
    has_assignment_notes: resource.has_assignment_notes !== false,
    display_order: displayOrder,
    is_active: Boolean(resource.is_active),
    field_schema: Array.isArray(resource.field_schema) ? resource.field_schema : []
  };
}

async function saveOrder() {
  const button = byId("saveResourceOrderBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "Enregistrement...";
  }

  try {
    for (let index = 0; index < currentResources.length; index += 1) {
      const resource = currentResources[index];
      const displayOrder = (index + 1) * 10;
      await adminRequest(`/api/admin/resources/${encodeURIComponent(resource.id)}`, {
        method: "PUT",
        body: JSON.stringify(buildUpdatePayload(resource, displayOrder))
      });
      resource.display_order = displayOrder;
    }
    setNotice("L'ordre d'affichage des ressources a été enregistré.", true, false);
    renderResources();
  } catch (error) {
    setNotice(error.message || "Impossible d'enregistrer l'ordre des ressources.", true, true);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Enregistrer l'ordre";
    }
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadResources();
    byId("saveResourceOrderBtn")?.addEventListener("click", saveOrder);
  } catch (error) {
    setNotice(error.message || "Impossible de charger les ressources.", true, true);
  }
});
