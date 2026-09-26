// Ajustement d'un dossier actif (3.65.0) : ajouter / retirer des ressources et/ou changer le service d'une personne sur son
// dossier existant, avec une signature par geste. Chargé après storage.js (listes et fiche). Le serveur fait foi : toutes les
// règles (dossier actif, ressource détenue, ressource complète, verrou optimiste) sont revérifiées par
// PATCH /api/forms/<id>/ajustement ; ce fichier ne fait que les proposer et afficher les refus.

// Les modes de signature et les états de reprise sont décrits ici, une seule fois, puis générés.
const ADJUSTMENT_SIGNATURE_MODES = [
  { value: "presentiel", label: "En présentiel", hint: "La personne signe sur cet écran." },
  { value: "distance", label: "À distance", hint: "L'ajustement est enregistré « en attente » ; la signature est recueillie ensuite (Ajuster > Signer l'ajustement)." },
  { value: "impossible", label: "Signature impossible", hint: "Un responsable signe à la place : indiquez le motif, son nom et sa qualité." }
];
const ADJUSTMENT_RETURN_STATES = [["conforme", "Conforme"], ["degrade", "Dégradé"], ["autre", "Autre"]];
const ADJUSTMENT_CONDITIONS = [["", "Non précisé"], ["neuf", "Neuf"], ["bon_etat", "Bon état"], ["etat_usage", "État d'usage"], ["degrade", "Dégradé"]];
const ADJUSTMENT_STATUS_LABELS = { signed: "Signé", pending_signature: "Signature en attente", signed_by_substitute: "Signé par un responsable" };
const ADJUSTMENT_ERRORS = {
  form_conflict: "Le dossier a été modifié depuis son ouverture. Fermez cette fenêtre, rouvrez l'ajustement et recommencez.",
  forbidden: "Votre profil ne permet pas d'ajuster un dossier.",
  masked_scope_read_only: "Votre profil (données masquées) ne permet pas d'ajuster un dossier."
};

function adjEsc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function adjOptions(pairs, selected = "") {
  return pairs.map(([value, label]) => `<option value="${adjEsc(value)}"${value === selected ? " selected" : ""}>${adjEsc(label)}</option>`).join("");
}

// ── Signature manuscrite minimale (canvas), indépendante de celles de la fiche et de la restitution ──
function createAdjustmentSignaturePad(canvas) {
  const context = canvas.getContext("2d");
  let drawing = false;
  let dirty = false;
  const resize = () => {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.round((canvas.clientWidth || 400) * ratio);
    const height = Math.round((canvas.clientHeight || 160) * ratio);
    // Redimensionner efface le dessin : on ne le fait que si la taille change, et l'indicateur « dessiné » suit.
    if (canvas.width === width && canvas.height === height) return;
    canvas.width = width;
    canvas.height = height;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.lineWidth = 2;
    context.lineCap = "round";
    context.strokeStyle = "#111";
    dirty = false;
  };
  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };
  canvas.addEventListener("pointerdown", (event) => {
    drawing = true;
    canvas.setPointerCapture?.(event.pointerId);
    const { x, y } = point(event);
    context.beginPath();
    context.moveTo(x, y);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const { x, y } = point(event);
    context.lineTo(x, y);
    context.stroke();
    dirty = true;
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((name) => canvas.addEventListener(name, () => { drawing = false; }));
  resize();
  return {
    isEmpty: () => !dirty,
    clear: () => { context.clearRect(0, 0, canvas.width, canvas.height); dirty = false; },
    toDataUrl: () => (dirty ? canvas.toDataURL("image/png") : ""),
    resize
  };
}

// ── Droits et lecture de l'historique ──
function getAdjustments(draft) {
  const events = draft?.data?.ajustements ?? draft?.ajustements;
  return Array.isArray(events) ? events : [];
}

function getPendingAdjustment(draft) {
  return getAdjustments(draft).find((event) => event.status === "pending_signature") || null;
}

function describeAdjustment(event) {
  const parts = [];
  (event.ajouts || []).forEach((item) => parts.push(`+ ${item.label}`));
  (event.retraits || []).forEach((item) => parts.push(`− ${item.label}`));
  if (event.service) parts.push(`Service : ${event.service.from || "—"} → ${event.service.to}`);
  return parts;
}

function renderAdjustmentHistory(container, events) {
  if (!container) return;
  const list = Array.isArray(events) ? events : [];
  container.classList.toggle("d-none", !list.length);
  if (!list.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
    <p class="panel-eyebrow mb-1">Historique des ajustements</p>
    <ul class="list-group">
      ${list.slice().reverse().map((event) => {
        const when = event.at ? new Date(event.at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "";
        const substitute = event.signature?.substitute ? ` — ${adjEsc(event.signature.substitute.name)} (${adjEsc(event.signature.substitute.quality || "responsable")})` : "";
        return `<li class="list-group-item">
          <div class="d-flex justify-content-between gap-2"><strong>${adjEsc(when)}</strong><span class="badge text-bg-secondary">${adjEsc(ADJUSTMENT_STATUS_LABELS[event.status] || event.status)}${substitute}</span></div>
          <div class="small">${describeAdjustment(event).map(adjEsc).join("<br>")}</div>
          <div class="small text-muted">par ${adjEsc(event.by || "—")}</div>
        </li>`;
      }).join("")}
    </ul>`;
}

// ── Champs d'une ressource ajoutée (mêmes types que la fiche : texte, nombre, date, liste, choix, case à cocher, liste de valeurs) ──
function buildAdjustmentFieldInput(resource, field) {
  const id = `adj_${resource.id}_${field.key}`;
  const label = `<label class="form-label" for="${adjEsc(id)}">${adjEsc(field.label)}${field.required ? " *" : ""}</label>`;
  const attrs = `id="${adjEsc(id)}" data-adj-field="${adjEsc(field.key)}" data-adj-type="${adjEsc(field.type || "text")}"${field.required ? " required" : ""}`;
  if (field.type === "textarea" || field.type === "list") {
    const help = field.type === "list" ? '<div class="form-text">Une valeur par ligne.</div>' : "";
    return `<div class="mb-2">${label}<textarea class="form-control" rows="2" ${attrs}></textarea>${help}</div>`;
  }
  if (field.type === "select") {
    const options = (Array.isArray(field.options) ? field.options : []).map((option) => [option, option]);
    return `<div class="mb-2">${label}<select class="form-select" ${attrs}><option value="">Sélectionner</option>${adjOptions(options)}</select></div>`;
  }
  if (field.type === "checkbox") {
    return `<div class="mb-2"><label class="form-check"><input class="form-check-input" type="checkbox" ${attrs}><span class="form-check-label">${adjEsc(field.label)}</span></label></div>`;
  }
  const inputType = ["number", "date"].includes(field.type) ? field.type : "text";
  return `<div class="mb-2">${label}<input class="form-control" type="${inputType}" ${attrs}></div>`;
}

function buildAdjustmentAdditionBlock(resource) {
  const visible = (Array.isArray(resource.field_schema) ? resource.field_schema : []).filter((field) => !field.hidden);
  const fields = visible.length
    ? visible.map((field) => buildAdjustmentFieldInput(resource, field)).join("")
    : `<div class="mb-2"><label class="form-label" for="adj_${adjEsc(resource.id)}_details">Précision / détails</label><input class="form-control" id="adj_${adjEsc(resource.id)}_details" data-adj-details="true" placeholder="Numéro de série, taille, couleur…"></div>`;
  const condition = resource.has_assignment_condition
    ? `<div class="mb-2"><label class="form-label">État à la remise</label><select class="form-select" data-adj-condition="true">${adjOptions(ADJUSTMENT_CONDITIONS)}</select></div>` : "";
  return `<div class="border rounded p-3 mb-2" data-adj-addition="${adjEsc(resource.id)}">
    <div class="d-flex justify-content-between align-items-start mb-2"><strong>+ ${adjEsc(resource.label)}</strong>
      <button type="button" class="btn btn-sm btn-outline-secondary" data-adj-remove-addition="${adjEsc(resource.id)}">Annuler l'ajout</button></div>
    ${fields}${condition}</div>`;
}

function readAdjustmentAddition(block, resource) {
  const fields = {};
  block.querySelectorAll("[data-adj-field]").forEach((input) => {
    const type = input.dataset.adjType;
    let value = input.type === "checkbox" ? (input.checked ? "Oui" : "") : input.value.trim();
    if (type === "list") value = value.split("\n").map((line) => line.trim()).filter(Boolean);
    if (Array.isArray(value) ? value.length : value) fields[input.dataset.adjField] = value;
  });
  const missing = (Array.isArray(resource.field_schema) ? resource.field_schema : [])
    .filter((field) => !field.hidden && field.required && !String(fields[field.key] ?? "").trim());
  if (missing.length) {
    throw new Error(`« ${resource.label} » : renseignez ${missing.map((field) => `« ${field.label} »`).join(", ")}.`);
  }
  const details = block.querySelector("[data-adj-details]")?.value.trim() || "";
  if (!(Array.isArray(resource.field_schema) && resource.field_schema.length) && !details) {
    throw new Error(`« ${resource.label} » : précisez le détail de la ressource.`);
  }
  return {
    id: resource.id, code: resource.code, label: resource.label, description: resource.description || "", category: resource.category,
    issuerService: resource.issuer_service, requiresReturn: Boolean(resource.requires_return),
    hasAssignmentDate: Boolean(resource.has_assignment_date), hasAssignmentCondition: Boolean(resource.has_assignment_condition),
    hasAssignmentNotes: Boolean(resource.has_assignment_notes), fieldSchema: resource.field_schema || [], fields, details,
    conditionAttribution: block.querySelector("[data-adj-condition]")?.value || ""
  };
}

// ── Fenêtre d'ajustement ──
function ensureAdjustmentModal() {
  let modal = document.getElementById("adjustmentModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "password-generator-modal d-none";
    modal.id = "adjustmentModal";
    modal.setAttribute("aria-hidden", "true");
    document.body.appendChild(modal);
  }
  return modal;
}

function closeAdjustmentModal() {
  const modal = document.getElementById("adjustmentModal");
  if (!modal) return;
  modal.classList.add("d-none");
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = "";
}

function buildAdjustmentSignatureSection(prefix) {
  return `<fieldset class="mb-3"><legend class="form-label fs-6">Signature</legend>
    ${ADJUSTMENT_SIGNATURE_MODES.map((mode, index) => `
      <div class="form-check"><input class="form-check-input" type="radio" name="${prefix}_mode" id="${prefix}_mode_${mode.value}" value="${mode.value}"${index === 0 ? " checked" : ""}>
      <label class="form-check-label" for="${prefix}_mode_${mode.value}">${adjEsc(mode.label)} <span class="text-muted small">— ${adjEsc(mode.hint)}</span></label></div>`).join("")}
    <div class="mt-2" id="${prefix}_presentiel"><canvas id="${prefix}_canvas" class="signature-box" style="width:100%;height:160px"></canvas>
      <button type="button" class="btn btn-sm btn-outline-secondary mt-1" id="${prefix}_clear">Effacer la signature</button></div>
    <div class="mt-2 d-none" id="${prefix}_impossible">
      <label class="form-label" for="${prefix}_reason">Motif *</label><input class="form-control mb-2" id="${prefix}_reason" placeholder="Pourquoi la signature est impossible">
      <div class="row g-2"><div class="col-sm-6"><label class="form-label" for="${prefix}_sub_name">Nom du responsable *</label><input class="form-control" id="${prefix}_sub_name"></div>
      <div class="col-sm-6"><label class="form-label" for="${prefix}_sub_quality">Qualité</label><input class="form-control" id="${prefix}_sub_quality" placeholder="Responsable de service"></div></div>
    </div></fieldset>`;
}

function bindAdjustmentSignatureSection(modal, prefix, allowedModes) {
  const pad = createAdjustmentSignaturePad(modal.querySelector(`#${prefix}_canvas`));
  const refresh = () => {
    const mode = modal.querySelector(`input[name="${prefix}_mode"]:checked`)?.value;
    modal.querySelector(`#${prefix}_presentiel`).classList.toggle("d-none", mode !== "presentiel");
    modal.querySelector(`#${prefix}_impossible`).classList.toggle("d-none", mode !== "impossible");
    if (mode === "presentiel") pad.resize();
  };
  modal.querySelectorAll(`input[name="${prefix}_mode"]`).forEach((radio) => {
    if (allowedModes && !allowedModes.includes(radio.value)) radio.closest(".form-check").classList.add("d-none");
    radio.addEventListener("change", refresh);
  });
  modal.querySelector(`#${prefix}_clear`).addEventListener("click", () => pad.clear());
  refresh();
  return () => {
    const mode = modal.querySelector(`input[name="${prefix}_mode"]:checked`)?.value;
    if (mode === "presentiel") {
      if (pad.isEmpty()) throw new Error("La signature est obligatoire en présentiel.");
      return { mode, signatureDataUrl: pad.toDataUrl() };
    }
    if (mode === "impossible") {
      const reason = modal.querySelector(`#${prefix}_reason`).value.trim();
      const name = modal.querySelector(`#${prefix}_sub_name`).value.trim();
      if (!reason) throw new Error("Précisez pourquoi la signature est impossible.");
      if (!name) throw new Error("Indiquez qui signe à la place (nom du responsable).");
      return { mode, reason, substitute: { name, quality: modal.querySelector(`#${prefix}_sub_quality`).value.trim() } };
    }
    return { mode };
  };
}

function adjustmentErrorMessage(error) {
  return ADJUSTMENT_ERRORS[error?.message] || error?.serverMessage || error?.message || "L'ajustement n'a pas pu être enregistré.";
}

async function adjustmentRequest(url, method, body) {
  const response = await fetch(url, {
    method, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": typeof getCsrfToken === "function" ? await getCsrfToken() : "" },
    body: JSON.stringify(body)
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.serverMessage = payload.message;
    throw error;
  }
  return payload;
}

function afterAdjustment(message) {
  showToast(message, "success");
  closeAdjustmentModal();
  if (document.getElementById("draftList") && typeof renderDraftList === "function") {
    void renderDraftList();
  } else {
    window.location.reload();
  }
}

async function openAdjustment(id) {
  let dossier;
  let catalog = [];
  let services = [];
  try {
    dossier = await requestJson(`/api/forms/${encodeURIComponent(id)}`);
    [catalog, services] = await Promise.all([
      requestJson("/api/reference/resources").catch(() => []),
      requestJson("/api/reference/services").catch(() => [])
    ]);
  } catch (error) {
    showToast("Impossible de charger le dossier.", "error");
    return;
  }
  if ((dossier.summary?.status || dossier.data?.workflow?.status) !== "active") {
    showToast("Seul un dossier actif peut être ajusté.", "warning");
    return;
  }
  const data = dossier.data || {};
  const held = (dossier.items || []).filter((item) => item.assigned && !item.returned);
  const heldKeys = new Set(held.map((item) => item.itemKey));
  const addable = (Array.isArray(catalog) ? catalog : []).filter((resource) => !heldKeys.has(resource.code));
  const currentService = data.beneficiaire?.service || "";
  const serviceNames = [...new Set([currentService, ...(Array.isArray(services) ? services : []).map((service) => service.name || service.label || service)].filter(Boolean))];
  const baseSavedAt = data.meta?.savedAt || dossier.summary?.updatedAt || "";
  const title = `${data.beneficiaire?.prenom || ""} ${data.beneficiaire?.nom || ""}`.trim() || "Dossier";

  const modal = ensureAdjustmentModal();
  modal.innerHTML = `
    <div class="password-generator-modal__backdrop" data-adj-close="true"></div>
    <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="adjustmentTitle">
      <div class="password-generator-modal__header">
        <div><p class="panel-eyebrow">Dossier actif</p><h2 class="section-title" id="adjustmentTitle">Ajuster : ${adjEsc(title)}</h2></div>
        <button class="btn btn-outline-secondary btn-sm" type="button" data-adj-close="true">Fermer</button>
      </div>
      <form class="password-generator-modal__content" id="adjustmentForm" novalidate>
        <fieldset class="mb-3"><legend class="form-label fs-6">Ressources à retirer</legend>
          ${held.length ? held.map((item, index) => `
            <div class="border rounded p-2 mb-2" data-adj-held="${adjEsc(item.itemKey)}">
              <label class="form-check"><input class="form-check-input" type="checkbox" id="adj_held_${index}" data-adj-withdraw="${adjEsc(item.itemKey)}"><span class="form-check-label">${adjEsc(item.label)}</span></label>
              <div class="row g-2 mt-1 d-none" data-adj-withdraw-details>
                <div class="col-sm-4"><select class="form-select form-select-sm" data-adj-state aria-label="État à la reprise">${adjOptions(ADJUSTMENT_RETURN_STATES)}</select></div>
                <div class="col-sm-8"><input class="form-control form-control-sm" data-adj-notes placeholder="Remarque (facultatif)"></div>
              </div>
            </div>`).join("") : '<p class="text-muted small mb-0">Aucune ressource détenue.</p>'}
        </fieldset>
        <fieldset class="mb-3"><legend class="form-label fs-6">Ressource à ajouter</legend>
          <select class="form-select mb-2" id="adjAddResource" aria-label="Ajouter une ressource"><option value="">Ajouter une ressource…</option>
            ${adjOptions(addable.map((resource) => [String(resource.id), `${resource.label}${resource.category ? ` (${resource.category})` : ""}`]))}</select>
          <div id="adjAdditions"></div>
        </fieldset>
        <div class="mb-3"><label class="form-label" for="adjService">Service</label>
          <select class="form-select" id="adjService">${adjOptions(serviceNames.map((name) => [name, name]), currentService)}</select></div>
        ${buildAdjustmentSignatureSection("adjSig")}
        <p class="text-danger small d-none" id="adjustmentError" role="alert"></p>
        <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
          <button class="btn btn-outline-secondary" type="button" data-adj-close="true">Annuler</button>
          <button class="btn btn-primary" type="submit" id="adjustmentSubmit">Enregistrer l'ajustement</button>
        </div>
        <div class="mt-3" id="adjustmentHistory"></div>
      </form>
    </div>`;
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  renderAdjustmentHistory(modal.querySelector("#adjustmentHistory"), data.ajustements);

  const readSignature = bindAdjustmentSignatureSection(modal, "adjSig");
  const errorNode = modal.querySelector("#adjustmentError");
  const showError = (message) => { errorNode.textContent = message; errorNode.classList.toggle("d-none", !message); };
  modal.querySelectorAll("[data-adj-close]").forEach((button) => button.addEventListener("click", closeAdjustmentModal));
  modal.querySelectorAll("[data-adj-withdraw]").forEach((box) => box.addEventListener("change", () => {
    box.closest("[data-adj-held]").querySelector("[data-adj-withdraw-details]").classList.toggle("d-none", !box.checked);
  }));
  const additions = modal.querySelector("#adjAdditions");
  const chooser = modal.querySelector("#adjAddResource");
  chooser.addEventListener("change", () => {
    const resource = addable.find((entry) => String(entry.id) === chooser.value);
    chooser.value = "";
    if (!resource || additions.querySelector(`[data-adj-addition="${CSS.escape(String(resource.id))}"]`)) return;
    additions.insertAdjacentHTML("beforeend", buildAdjustmentAdditionBlock(resource));
    const block = additions.lastElementChild;
    block.querySelector("[data-adj-remove-addition]").addEventListener("click", () => block.remove());
  });

  modal.querySelector("#adjustmentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const submit = modal.querySelector("#adjustmentSubmit");
    try {
      const withdrawals = [...modal.querySelectorAll("[data-adj-withdraw]:checked")].map((box) => {
        const row = box.closest("[data-adj-held]");
        return { key: box.dataset.adjWithdraw, state: row.querySelector("[data-adj-state]").value, notes: row.querySelector("[data-adj-notes]").value.trim() };
      });
      const newResources = [...additions.querySelectorAll("[data-adj-addition]")].map((block) =>
        readAdjustmentAddition(block, addable.find((entry) => String(entry.id) === block.dataset.adjAddition)));
      const service = modal.querySelector("#adjService").value;
      const serviceChanged = service && service !== currentService;
      if (!withdrawals.length && !newResources.length && !serviceChanged) {
        throw new Error("Rien à ajuster : retirez ou ajoutez une ressource, ou changez le service.");
      }
      const signature = readSignature();
      submit.disabled = true;
      const result = await adjustmentRequest(`/api/forms/${encodeURIComponent(id)}/ajustement`, "PATCH",
        { ajouts: newResources, retraits: withdrawals, service: serviceChanged ? service : "", signature, baseSavedAt });
      afterAdjustment(result.ajustement?.status === "pending_signature"
        ? "Ajustement enregistré : la signature reste à recueillir." : "Ajustement enregistré.");
    } catch (error) {
      submit.disabled = false;
      showError(adjustmentErrorMessage(error));
    }
  });
}

// ── Recueillir la signature d'un ajustement resté « en attente » (mode à distance) ──
async function openAdjustmentSignature(id) {
  let dossier;
  try {
    dossier = await requestJson(`/api/forms/${encodeURIComponent(id)}`);
  } catch (error) {
    showToast("Impossible de charger le dossier.", "error");
    return;
  }
  const pending = getPendingAdjustment(dossier);
  if (!pending) {
    showToast("Aucun ajustement en attente de signature.", "info");
    return;
  }
  const modal = ensureAdjustmentModal();
  modal.innerHTML = `
    <div class="password-generator-modal__backdrop" data-adj-close="true"></div>
    <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="adjustmentTitle">
      <div class="password-generator-modal__header">
        <div><p class="panel-eyebrow">Ajustement en attente</p><h2 class="section-title" id="adjustmentTitle">Recueillir la signature</h2></div>
        <button class="btn btn-outline-secondary btn-sm" type="button" data-adj-close="true">Fermer</button>
      </div>
      <form class="password-generator-modal__content" id="adjustmentForm" novalidate>
        <div class="mb-3">${describeAdjustment(pending).map(adjEsc).join("<br>")}</div>
        ${buildAdjustmentSignatureSection("adjSign")}
        <p class="text-danger small d-none" id="adjustmentError" role="alert"></p>
        <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
          <button class="btn btn-outline-secondary" type="button" data-adj-close="true">Annuler</button>
          <button class="btn btn-primary" type="submit" id="adjustmentSubmit">Enregistrer la signature</button>
        </div>
      </form>
    </div>`;
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  const readSignature = bindAdjustmentSignatureSection(modal, "adjSign", ["presentiel", "impossible"]);
  modal.querySelector('input[name="adjSign_mode"][value="presentiel"]').checked = true;
  modal.querySelector('input[name="adjSign_mode"][value="presentiel"]').dispatchEvent(new Event("change"));
  const errorNode = modal.querySelector("#adjustmentError");
  modal.querySelectorAll("[data-adj-close]").forEach((button) => button.addEventListener("click", closeAdjustmentModal));
  modal.querySelector("#adjustmentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    errorNode.classList.add("d-none");
    const submit = modal.querySelector("#adjustmentSubmit");
    try {
      const signature = readSignature();
      submit.disabled = true;
      await adjustmentRequest(`/api/forms/${encodeURIComponent(id)}/ajustement/${encodeURIComponent(pending.id)}/signature`, "POST", signature);
      afterAdjustment("Signature de l'ajustement enregistrée.");
    } catch (error) {
      submit.disabled = false;
      errorNode.textContent = adjustmentErrorMessage(error);
      errorNode.classList.remove("d-none");
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.getElementById("adjustmentModal")?.classList.contains("d-none") === false) closeAdjustmentModal();
});
