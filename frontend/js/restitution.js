const restitutionLoader = document.getElementById("restitutionLoader");
const restitutionDetailList = document.getElementById("restitutionDetailList");

// Libellés affichés dans la page de restitution dédiée.
const restitutionLabels = {
  pending: "En attente",
  returned: "Restitué",
  returned_damaged: "Restitué abîmé",
  missing: "Non restitué",
  transferred: "Transféré"
};

function showRestitutionLoader() {
  restitutionLoader?.classList.remove("is-hidden");
}

function hideRestitutionLoader() {
  restitutionLoader?.classList.add("is-hidden");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function selectedDetail(details) {
  return Object.entries(details || {})
    .filter(([key, value]) => key !== "selected" && value)
    .map(([, value]) => value)
    .join(" - ");
}

function renderRestitutionItems(items, existingStates) {
  // Affiche une ligne par équipement attribué dans la fiche source.
  restitutionDetailList.innerHTML = items.map((item) => {
    const state = existingStates[item.itemKey] || {};
    return `
      <div class="restitution-row">
        <div>
          <div class="restitution-row__title">${escapeHtml(item.label)}</div>
          <div class="restitution-row__meta">${escapeHtml(selectedDetail(item.details) || "Aucun détail complémentaire")}</div>
        </div>
        <div>
          <label class="form-label" for="rest_state_${item.itemKey}">État</label>
          <select class="form-select" id="rest_state_${item.itemKey}">
            <option value="pending" ${state.state === "pending" ? "selected" : ""}>En attente</option>
            <option value="returned" ${state.state === "returned" ? "selected" : ""}>Restitué</option>
            <option value="returned_damaged" ${state.state === "returned_damaged" ? "selected" : ""}>Restitué abîmé</option>
            <option value="missing" ${state.state === "missing" ? "selected" : ""}>Non restitué</option>
            <option value="transferred" ${state.state === "transferred" ? "selected" : ""}>Transféré</option>
          </select>
        </div>
        <div>
          <label class="form-label" for="rest_date_${item.itemKey}">Date</label>
          <input class="form-control" type="date" id="rest_date_${item.itemKey}" value="${escapeHtml(state.returnedAt || "")}">
        </div>
        <div>
          <label class="form-label" for="rest_note_${item.itemKey}">Observation</label>
          <input class="form-control" id="rest_note_${item.itemKey}" value="${escapeHtml(state.notes || "")}" placeholder="État ou commentaire">
        </div>
      </div>
    `;
  }).join("");
}

function getItemStates(items) {
  // Relit les saisies écran pour produire le payload PATCH de restitution.
  const states = {};
  items.forEach((item) => {
    const state = document.getElementById(`rest_state_${item.itemKey}`)?.value || "pending";
    const returnedAt = document.getElementById(`rest_date_${item.itemKey}`)?.value || "";
    const notes = document.getElementById(`rest_note_${item.itemKey}`)?.value.trim() || "";
    states[item.itemKey] = {
      state,
      returned: ["returned", "returned_damaged", "transferred"].includes(state),
      returnedAt,
      condition: state,
      notes
    };
  });
  return states;
}

async function initRestitutionPage() {
  // Cette page ne s'ouvre que sur une fiche active.
  // On recharge d'abord la fiche, puis on autorise l'utilisateur à saisir les retours.
  showRestitutionLoader();
  const session = await getSessionInfo();
  const canRestitution = Boolean(session?.permissions?.includes("*") || session?.permissions?.includes("forms.restitution"));
  if (!canRestitution) {
    alert("Votre profil ne permet pas de saisir une restitution.");
    window.location.href = "index.html";
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) {
    alert("Aucune fiche sélectionnée.");
    window.location.href = "index.html";
    return;
  }

  const result = await getDraftById(id);
  if (!result?.data) {
    alert("Fiche introuvable.");
    window.location.href = "index.html";
    return;
  }

  if ((result.summary?.status || result.data?.workflow?.status) !== "active") {
    alert("La restitution est réservée aux attributions actives.");
    window.location.href = "index.html";
    return;
  }

  document.getElementById("restitutionTitle").textContent = `${result.data.beneficiaire.nom} ${result.data.beneficiaire.prenom}`;
  document.getElementById("restitutionSubtitle").textContent = result.data.beneficiaire.service || result.data.beneficiaire.mandat || "Fiche active";
  document.getElementById("global_returned_at").value = result.data.restitution?.returnedAt || "";
  document.getElementById("global_return_reason").value = result.data.restitution?.reason || "";
  document.getElementById("global_return_notes").value = result.data.restitution?.notes || "";
  document.getElementById("global_return_status").value = result.data.workflow?.status === "active" ? "returned" : result.data.workflow?.status || "returned";

  renderRestitutionItems(result.items || [], result.data.restitution?.items || {});

  document.getElementById("saveRestitutionBtn").addEventListener("click", async () => {
    const payload = {
      status: document.getElementById("global_return_status").value,
      returnedAt: document.getElementById("global_returned_at").value,
      reason: document.getElementById("global_return_reason").value,
      notes: document.getElementById("global_return_notes").value.trim(),
      items: getItemStates(result.items || [])
    };

    if (!payload.returnedAt) {
      alert("Veuillez renseigner la date de restitution.");
      return;
    }

    try {
      await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      alert("Restitution enregistrée.");
      window.location.href = "index.html";
    } catch (error) {
      alert("Impossible d'enregistrer la restitution.");
    }
  });

  requestAnimationFrame(() => {
    requestAnimationFrame(() => hideRestitutionLoader());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  void initRestitutionPage();
});
