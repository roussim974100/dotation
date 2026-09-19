// Assistant de creation de ressource (5 etapes, apercu en direct) et ecran « qualite du catalogue ».
// Objectif : que chaque ressource soit creee avec les bons champs pour obtenir un historique coherent.
// Les modeles sont FIXES (livres avec l'application) et definis en objet : ajouter un modele = ajouter une entree.
// S'appuie sur admin.js (currentServices, loadResources, populateResourceForm, byId, escapeHtml, showToast, getCsrfToken).

const WIZARD_TRACKING = [
  { mode: "unit", title: "Un objet individuel", category: "materiel", requiresReturn: true,
    text: "Chaque objet est reconnu par un identifiant (n° de série, immatriculation, n° de badge…). Permet l'historique de vie, la reprise du matériel restitué et la détection de doublons.",
    example: "Ordinateur, téléphone, badge télépéage, véhicule" },
  { mode: "none", title: "Sans suivi individuel", category: "materiel", requiresReturn: true,
    text: "On sait qu'une ressource a été remise, pas laquelle. Aucun historique par objet.",
    example: "Veste, chaussures de sécurité, jeu de clés" },
  { mode: "access", title: "Un accès numérique", category: "immateriel", requiresReturn: false,
    text: "Un compte ou un droit qu'on ouvre puis qu'on ferme, sans objet à rendre.",
    example: "VPN, messagerie, licence logicielle" }
];

// Champs : label, type, required, identifier (identifie l'objet), suggest (autocompletion depuis l'historique).
const WIZARD_TEMPLATES = [
  { id: "informatique", mode: "unit", label: "Matériel informatique", description: "Ordinateur, écran, tablette…",
    fields: [{ label: "Nom du poste", suggest: true }, { label: "Marque", required: true, suggest: true }, { label: "Modèle", required: true, suggest: true }, { label: "N° de série", required: true, identifier: true }] },
  { id: "telephone", mode: "unit", label: "Téléphone", description: "Mobile ou fixe, avec son IMEI ou son n° de série.",
    fields: [{ label: "Marque", required: true, suggest: true }, { label: "Modèle", required: true, suggest: true }, { label: "N° de série / IMEI", required: true, identifier: true }, { label: "N° de ligne" }] },
  { id: "vehicule", mode: "unit", label: "Véhicule", description: "Véhicule de service ou de fonction.",
    fields: [{ label: "Marque", required: true, suggest: true }, { label: "Modèle", required: true, suggest: true }, { label: "Immatriculation", required: true, identifier: true }] },
  { id: "badge", mode: "unit", label: "Badge (accès, télépéage)", description: "Badge d'accès aux locaux, badge autoroute…",
    fields: [{ label: "N° du badge", required: true, identifier: true }, { label: "Opérateur ou type" }, { label: "Date de fin de validité", type: "date" }] },
  { id: "vetement", mode: "none", label: "Vêtement / équipement", description: "Veste, chaussures, gilet…",
    fields: [{ label: "Taille" }] },
  { id: "cles", mode: "none", label: "Jeu de clés", description: "Liste des clés remises.",
    fields: [{ label: "Détail des clés", type: "textarea" }] },
  { id: "acces", mode: "access", label: "Accès numérique", description: "Compte, droit ou licence.",
    fields: [{ label: "Identifiant du compte", required: true }] },
  { id: "vide", mode: null, label: "Ressource vierge", description: "Je définis moi-même les champs.", fields: [] }
];

const WIZARD_FIELD_TYPES = [["text", "Texte"], ["textarea", "Texte long"], ["date", "Date"], ["number", "Nombre"], ["select", "Liste de choix"]];
const WIZARD_STEPS = ["Suivi", "Modèle", "Identité", "Champs", "Récapitulatif"];

const WIZARD_ISSUE_MESSAGES = {
  no_identifier: "Suivi par objet sans champ identifiant : aucun historique possible.",
  identifier_hidden: "Le champ identifiant est masqué.",
  identifier_optional: "Le champ identifiant doit être obligatoire.",
  unit_needs_material: "Le suivi par objet est réservé au matériel.",
  several_identifiers: "Un seul champ peut identifier l'objet.",
  duplicate_field: "Deux champs portent le même nom.",
  resource_exists: "Une ressource avec ce code existe déjà."
};

let wizardState = null;

function wizardSlug(value) {
  return String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function wizardNewState() {
  return { step: 1, mode: null, templateId: null, label: "", code: "", codeTouched: false, description: "", issuer: "",
    requiresReturn: true, hasCondition: true, fields: [] };
}

function wizardField(field) {
  return { label: field.label, type: field.type || "text", required: Boolean(field.required), identifier: Boolean(field.identifier),
    suggest: Boolean(field.suggest), options: field.options || "" };
}

// Meme logique que le serveur (models/resource_rules.py) pour guider avant l'envoi ; le serveur reste l'autorite.
function wizardIssues(state) {
  const issues = [];
  if (!state.label.trim()) issues.push({ level: "error", text: "Donnez un nom à la ressource." });
  if (state.mode === "unit") {
    const identifier = state.fields.find((field) => field.identifier);
    if (!identifier) issues.push({ level: "error", text: "Choisissez le champ qui identifie l'objet (n° de série, immatriculation, n° de badge…)." });
    if (!state.hasCondition) issues.push({ level: "warning", text: "Activez « état à la remise » : il alimente l'historique." });
    if (!state.requiresReturn) issues.push({ level: "warning", text: "Non restituable : l'historique ne verra jamais de restitution." });
  }
  const labels = state.fields.map((field) => wizardSlug(field.label));
  if (state.fields.some((field) => !field.label.trim())) issues.push({ level: "error", text: "Un champ n'a pas de nom." });
  if (new Set(labels).size !== labels.length) issues.push({ level: "error", text: "Deux champs portent le même nom." });
  if (!state.issuer) issues.push({ level: "warning", text: "Aucun service émetteur : personne ne saura qui doit l'attribuer." });
  return issues;
}

function wizardPreview(state) {
  const tracking = WIZARD_TRACKING.find((item) => item.mode === state.mode);
  const fieldsHtml = state.fields.filter((field) => field.label.trim()).map((field) => `
    <div class="mb-2">
      <label class="form-label">${escapeHtml(field.label)}${field.required ? ' <span class="progress-required-badge">Requis</span>' : ""}${field.identifier ? ' <span class="status-chip status-chip--active">Identifie l\'objet</span>' : ""}</label>
      <input class="form-control" disabled placeholder="${escapeHtml(field.type === "date" ? "jj/mm/aaaa" : field.label)}">
    </div>`).join("");
  const history = state.mode === "unit"
    ? (state.fields.some((field) => field.identifier) ? '<span class="status-chip status-chip--active">Historique de vie activé</span>' : '<span class="status-chip status-chip--cancelled">Historique impossible</span>')
    : (state.mode ? '<span class="status-chip status-chip--draft">Pas d\'historique par objet</span>' : "");
  const issues = wizardIssues(state);
  return `
    <p class="panel-eyebrow">Aperçu dans le formulaire d'attribution</p>
    <div class="equipment-item">
      <div class="equipment-item__header">
        <label class="equipment-toggle"><input type="checkbox" disabled checked><span>${escapeHtml(state.label || "Nom de la ressource")}</span></label>
        <span class="equipment-item__hint">${escapeHtml(state.issuer || "Service non renseigné")} · ${tracking ? (tracking.category === "materiel" ? "Matériel" : "Numérique") : "—"}</span>
      </div>
      ${state.description ? `<p class="equipment-item__desc">${escapeHtml(state.description)}</p>` : ""}
      <div class="equipment-item__body">${fieldsHtml || '<p class="form-text mb-0">Aucun champ pour l\'instant.</p>'}</div>
    </div>
    <div class="mt-3">${history}</div>
    ${issues.length ? `<ul class="list-unstyled small mt-3 mb-0">${issues.map((issue) => `<li class="${issue.level === "error" ? "text-danger" : "text-warning"}">${issue.level === "error" ? "✖" : "⚠"} ${escapeHtml(issue.text)}</li>`).join("")}</ul>` : ""}`;
}

function wizardStepBody(state) {
  if (state.step === 1) {
    return `<p class="panel-text">Que voulez-vous suivre ? Ce choix détermine ce que l'application saura de chaque ressource.</p>
      <div class="d-grid gap-2">${WIZARD_TRACKING.map((item) => `
        <button type="button" class="btn text-start border p-3 ${state.mode === item.mode ? "border-primary" : ""}" data-wizard-mode="${item.mode}" aria-pressed="${state.mode === item.mode}">
          <strong>${escapeHtml(item.title)}</strong><span class="d-block small text-muted">${escapeHtml(item.text)}</span>
          <span class="d-block small mt-1">Exemples : ${escapeHtml(item.example)}</span>
        </button>`).join("")}</div>`;
  }
  if (state.step === 2) {
    const list = WIZARD_TEMPLATES.filter((tpl) => tpl.mode === null || tpl.mode === state.mode);
    return `<p class="panel-text">Partez d'un modèle : il préremplit les champs adaptés. Vous pourrez tout modifier ensuite.</p>
      <div class="d-grid gap-2">${list.map((tpl) => `
        <button type="button" class="btn text-start border p-3 ${state.templateId === tpl.id ? "border-primary" : ""}" data-wizard-template="${tpl.id}" aria-pressed="${state.templateId === tpl.id}">
          <strong>${escapeHtml(tpl.label)}</strong><span class="d-block small text-muted">${escapeHtml(tpl.description)}</span>
        </button>`).join("")}</div>`;
  }
  if (state.step === 3) {
    const services = (typeof currentServices !== "undefined" ? currentServices : []).filter((service) => service.is_active);
    return `<div class="mb-3"><label class="form-label" for="wz_label">Nom de la ressource *</label>
        <input class="form-control" id="wz_label" value="${escapeHtml(state.label)}" autocomplete="off"></div>
      <div class="mb-3"><label class="form-label" for="wz_code">Code technique</label>
        <input class="form-control" id="wz_code" value="${escapeHtml(state.code)}" autocomplete="off">
        <div class="form-text">Généré depuis le nom. Il ne pourra plus changer dès qu'un dossier utilisera la ressource.</div></div>
      <div class="mb-3"><label class="form-label" for="wz_description">Description (facultatif)</label>
        <input class="form-control" id="wz_description" value="${escapeHtml(state.description)}"></div>
      <div class="mb-3"><label class="form-label" for="wz_issuer">Service émetteur</label>
        <select class="form-select" id="wz_issuer"><option value="">— À définir —</option>${services.map((service) => `<option value="${escapeHtml(service.label)}"${service.label === state.issuer ? " selected" : ""}>${escapeHtml(service.label)}</option>`).join("")}</select>
        <div class="form-text">Le service qui attribue et récupère cette ressource.</div></div>
      ${state.mode !== "access" ? `<div class="form-check mb-2"><input class="form-check-input" type="checkbox" id="wz_return"${state.requiresReturn ? " checked" : ""}><label class="form-check-label" for="wz_return">La ressource doit être restituée</label></div>` : ""}
      ${state.mode === "unit" ? `<div class="form-check"><input class="form-check-input" type="checkbox" id="wz_condition"${state.hasCondition ? " checked" : ""}><label class="form-check-label" for="wz_condition">Noter l'état à la remise (neuf, bon état…) — recommandé pour l'historique</label></div>` : ""}`;
  }
  if (state.step === 4) {
    const unit = state.mode === "unit";
    return `<p class="panel-text">${unit ? "Choisissez <strong>le champ qui identifie l'objet</strong> : il sert à retrouver son historique. Il est obligatoire." : "Définissez les informations demandées à l'attribution."}</p>
      <div id="wz_fields">${state.fields.map((field, index) => `
        <div class="border rounded p-2 mb-2" data-wizard-field="${index}">
          <div class="row g-2 align-items-center">
            <div class="col-md-5"><input class="form-control" data-wz="label" aria-label="Nom du champ" value="${escapeHtml(field.label)}" placeholder="Nom du champ"></div>
            <div class="col-md-3"><select class="form-select" data-wz="type" aria-label="Type">${WIZARD_FIELD_TYPES.map(([value, text]) => `<option value="${value}"${field.type === value ? " selected" : ""}>${text}</option>`).join("")}</select></div>
            <div class="col-md-4 d-flex flex-wrap gap-2 align-items-center justify-content-end">
              <label class="form-check mb-0"><input class="form-check-input" type="checkbox" data-wz="required" ${field.required || field.identifier ? "checked" : ""} ${field.identifier ? "disabled" : ""}> Obligatoire</label>
              ${unit ? `<label class="form-check mb-0"><input class="form-check-input" type="radio" name="wz_identifier" data-wz="identifier" ${field.identifier ? "checked" : ""}> Identifie l'objet</label>` : ""}
              <button class="btn btn-sm btn-outline-danger" type="button" data-wz="remove" aria-label="Retirer ce champ">✕</button>
            </div>
          </div>
          ${field.type === "select" ? `<textarea class="form-control mt-2" data-wz="options" rows="2" placeholder="Une valeur par ligne">${escapeHtml(field.options)}</textarea>` : ""}
        </div>`).join("")}</div>
      <button class="btn btn-sm btn-outline-secondary" type="button" id="wz_addField">+ Ajouter un champ</button>`;
  }
  const issues = wizardIssues(state);
  return `<p class="panel-text">Vérifiez l'aperçu, puis créez la ressource.</p>
    <dl class="row small mb-0">
      <dt class="col-4">Nom</dt><dd class="col-8">${escapeHtml(state.label)}</dd>
      <dt class="col-4">Suivi</dt><dd class="col-8">${escapeHtml(WIZARD_TRACKING.find((item) => item.mode === state.mode)?.title || "")}</dd>
      <dt class="col-4">Service</dt><dd class="col-8">${escapeHtml(state.issuer || "à définir")}</dd>
      <dt class="col-4">Champs</dt><dd class="col-8">${state.fields.length}</dd>
    </dl>
    ${issues.some((issue) => issue.level === "error") ? '<p class="text-danger mt-3 mb-0">Corrigez les points en rouge avant de créer.</p>' : ""}
    <p class="text-danger small mt-2 mb-0 d-none" id="wz_serverError" role="alert"></p>`;
}

function wizardCanContinue(state) {
  if (state.step === 1) return Boolean(state.mode);
  if (state.step === 2) return Boolean(state.templateId);
  if (state.step === 3) return Boolean(state.label.trim());
  if (state.step === 4) return !wizardIssues(state).some((issue) => issue.level === "error" && issue.text !== "Donnez un nom à la ressource.");
  return !wizardIssues(state).some((issue) => issue.level === "error");
}

function renderWizard() {
  const modal = byId("resourceWizardModal");
  if (!modal || !wizardState) return;
  const state = wizardState;
  modal.querySelector("#wzProgress").innerHTML = WIZARD_STEPS.map((name, index) =>
    `<li class="restitution-steps__item${index + 1 === state.step ? " is-current" : ""}"><span${index + 1 === state.step ? ' aria-current="step"' : ""}><span class="restitution-steps__num">${index + 1}</span> ${escapeHtml(name)}</span></li>`).join("");
  modal.querySelector("#wzBody").innerHTML = wizardStepBody(state);
  modal.querySelector("#wzPreview").innerHTML = wizardPreview(state);
  modal.querySelector("#wzBack").classList.toggle("d-none", state.step === 1);
  modal.querySelector("#wzNext").classList.toggle("d-none", state.step === 5);
  modal.querySelector("#wzCreate").classList.toggle("d-none", state.step !== 5);
  modal.querySelector("#wzNext").disabled = !wizardCanContinue(state);
  modal.querySelector("#wzCreate").disabled = !wizardCanContinue(state);
}

function wizardApplyTemplate(templateId) {
  const template = WIZARD_TEMPLATES.find((item) => item.id === templateId);
  wizardState.templateId = templateId;
  wizardState.fields = template.fields.map(wizardField);
  if (template.id !== "vide" && !wizardState.label) {
    wizardState.label = template.label === "Matériel informatique" ? "" : template.label;
  }
}

async function wizardSubmit() {
  const state = wizardState;
  const errorBox = byId("wz_serverError");
  const button = byId("wzCreate");
  const tracking = WIZARD_TRACKING.find((item) => item.mode === state.mode);
  const nextOrder = (typeof currentResources !== "undefined" ? currentResources : []).reduce((max, item) => Math.max(max, Number(item.display_order) || 0), 0) + 10;
  const payload = {
    code: state.code || wizardSlug(state.label), label: state.label.trim(), description: state.description.trim(),
    category: tracking.category, issuer_service: state.issuer, requires_return: state.mode === "access" ? false : state.requiresReturn,
    has_assignment_date: true, has_assignment_condition: state.mode === "unit" ? state.hasCondition : state.mode !== "access",
    has_assignment_notes: true, display_order: nextOrder, is_active: true, tracking_mode: state.mode,
    field_schema: state.fields.filter((field) => field.label.trim()).map((field) => ({
      key: wizardSlug(field.label), label: field.label.trim(), type: field.type, required: field.required || field.identifier, identifier: field.identifier,
      suggest: field.suggest, options: field.type === "select" ? field.options.split(/\r?\n/).map((value) => value.trim()).filter(Boolean) : []
    }))
  };
  button.disabled = true;
  try {
    const response = await fetch("/api/admin/resources", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const messages = (data.issues || []).map((issue) => issue.message).concat(data.error && !data.issues ? [WIZARD_ISSUE_MESSAGES[data.error] || data.error] : []);
      errorBox.textContent = messages.join(" ") || `Erreur ${response.status}`;
      errorBox.classList.remove("d-none");
      button.disabled = false;
      return;
    }
    closeResourceWizard();
    showToast(`Ressource « ${payload.label} » créée.`, "success");
    await loadResources();
    loadCatalogQuality();
  } catch (error) {
    errorBox.textContent = "Erreur de connexion au serveur.";
    errorBox.classList.remove("d-none");
    button.disabled = false;
  }
}

function closeResourceWizard() {
  const modal = byId("resourceWizardModal");
  if (modal) {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  }
  wizardState = null;
}

function openResourceWizard() {
  let modal = byId("resourceWizardModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "password-generator-modal d-none";
    modal.id = "resourceWizardModal";
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <div class="password-generator-modal__backdrop" data-wz-close="true"></div>
      <div class="password-generator-modal__dialog wizard-dialog" role="dialog" aria-modal="true" aria-labelledby="wzTitle">
        <div class="password-generator-modal__header">
          <div><p class="panel-eyebrow">Assistant</p><h2 class="section-title" id="wzTitle">Nouvelle ressource</h2></div>
          <button class="btn btn-outline-secondary btn-sm" type="button" data-wz-close="true">Fermer</button>
        </div>
        <ol class="restitution-steps__list mb-3" id="wzProgress" aria-label="Étapes"></ol>
        <div class="row g-4">
          <div class="col-lg-6" id="wzBody"></div>
          <div class="col-lg-6"><div class="border rounded p-3 wizard-preview" id="wzPreview" aria-live="polite"></div></div>
        </div>
        <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
          <button class="btn btn-outline-secondary" type="button" id="wzBack">Précédent</button>
          <button class="btn btn-primary" type="button" id="wzNext">Suivant</button>
          <button class="btn btn-primary d-none" type="button" id="wzCreate">Créer la ressource</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.addEventListener("click", (event) => {
      if (event.target.closest("[data-wz-close]")) return closeResourceWizard();
      const state = wizardState;
      const mode = event.target.closest("[data-wizard-mode]");
      if (mode) { state.mode = mode.dataset.wizardMode; state.templateId = null; state.fields = []; state.requiresReturn = state.mode !== "access"; return renderWizard(); }
      const template = event.target.closest("[data-wizard-template]");
      if (template) { wizardApplyTemplate(template.dataset.wizardTemplate); return renderWizard(); }
      if (event.target.closest("#wz_addField")) { state.fields.push(wizardField({ label: "" })); return renderWizard(); }
      const remove = event.target.closest('[data-wz="remove"]');
      if (remove) { state.fields.splice(Number(remove.closest("[data-wizard-field]").dataset.wizardField), 1); return renderWizard(); }
      if (event.target.closest("#wzBack")) { state.step -= 1; return renderWizard(); }
      if (event.target.closest("#wzNext") && wizardCanContinue(state)) {
        if (state.step === 2 && !state.label) { const tpl = WIZARD_TEMPLATES.find((item) => item.id === state.templateId); if (tpl && tpl.id !== "vide" && tpl.label !== "Matériel informatique") state.label = tpl.label; }
        state.step += 1;
        if (state.step === 3 && !state.codeTouched) state.code = wizardSlug(state.label);
        return renderWizard();
      }
      if (event.target.closest("#wzCreate") && wizardCanContinue(state)) return wizardSubmit();
    });
    modal.addEventListener("input", (event) => {
      const state = wizardState;
      const target = event.target;
      if (target.id === "wz_label") { state.label = target.value; if (!state.codeTouched) { state.code = wizardSlug(state.label); const code = byId("wz_code"); if (code) code.value = state.code; } }
      else if (target.id === "wz_code") { state.code = wizardSlug(target.value); state.codeTouched = true; }
      else if (target.id === "wz_description") state.description = target.value;
      else if (target.id === "wz_issuer") state.issuer = target.value;
      else if (target.id === "wz_return") state.requiresReturn = target.checked;
      else if (target.id === "wz_condition") state.hasCondition = target.checked;
      else if (target.dataset.wz) {
        const row = target.closest("[data-wizard-field]");
        const field = state.fields[Number(row.dataset.wizardField)];
        if (target.dataset.wz === "label") field.label = target.value;
        else if (target.dataset.wz === "type") { field.type = target.value; return renderWizard(); }
        else if (target.dataset.wz === "required") field.required = target.checked;
        else if (target.dataset.wz === "options") field.options = target.value;
        else if (target.dataset.wz === "identifier") { state.fields.forEach((item) => { item.identifier = false; }); field.identifier = true; field.required = true; return renderWizard(); }
      }
      // Aperçu et boutons se mettent à jour sans refaire le corps (pas de perte de focus pendant la frappe).
      modal.querySelector("#wzPreview").innerHTML = wizardPreview(state);
      modal.querySelector("#wzNext").disabled = !wizardCanContinue(state);
      modal.querySelector("#wzCreate").disabled = !wizardCanContinue(state);
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && wizardState) closeResourceWizard(); });
  }
  wizardState = wizardNewState();
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  renderWizard();
}

// ---- Ecran « qualite du catalogue » ---------------------------------------------------------------
async function loadCatalogQuality() {
  const host = byId("catalogQuality");
  if (!host) return;
  try {
    const response = await fetch("/api/admin/catalog/quality", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (!data.resources.length) {
      host.innerHTML = `<p class="text-success mb-0">✔ Toutes les ressources actives sont correctement configurées (${data.total} contrôlées).</p>`;
      return;
    }
    host.innerHTML = `<p class="small text-muted">${data.resources.length} ressource(s) sur ${data.total} à corriger pour obtenir un historique fiable.</p>
      <ul class="list-group">${data.resources.map((resource) => `
        <li class="list-group-item d-flex justify-content-between align-items-start gap-3">
          <div><strong>${escapeHtml(resource.label)}</strong> <span class="small text-muted">(${escapeHtml(resource.code)})</span>
            <ul class="small mb-0 mt-1">${resource.issues.map((issue) => `<li class="${issue.level === "error" ? "text-danger" : "text-warning"}">${escapeHtml(issue.message)}</li>`).join("")}</ul></div>
          <button class="btn btn-sm btn-outline-primary" type="button" data-quality-fix="${escapeHtml(resource.id)}">Corriger</button>
        </li>`).join("")}</ul>`;
  } catch (error) {
    host.textContent = "Contrôle indisponible.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  byId("resourceWizardBtn")?.addEventListener("click", openResourceWizard);
  byId("catalogQuality")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quality-fix]");
    if (button) { populateResourceForm(button.dataset.qualityFix); }
  });
  loadCatalogQuality();
});
