// Assistant d'organisation (Administration > Personnalisation) : type d'organisation, bénéficiaires, ressources à activer,
// réglages de départ, puis aperçu et application. Le serveur reste l'autorité : il fournit le catalogue de suggestions
// (GET /api/admin/org-presets), calcule le plan (POST /api/admin/org-wizard/preview) et n'applique que le plan aperçu.
// Tout est une SUGGESTION modifiable : structure quelconque, y compris hors France (libellés libres, contexte « autre »).
// Ajout seulement : rien d'utilisé n'est supprimé.

const ORG_WIZARD_STEPS = ["Organisation", "Bénéficiaires", "Ressources", "Réglages", "Récapitulatif"];

const ORG_WIZARD_SETTINGS_FIELDS = [
  { key: "support_name", label: "Contact support (nom)", type: "text" },
  { key: "support_email", label: "Contact support (e-mail)", type: "email" },
  { key: "support_role", label: "Contact support (fonction)", type: "text" },
  { key: "email_domains", label: "Domaines e-mail autorisés", type: "text", help: "Séparés par des virgules (ex. exemple.org). Vide : tous." },
  { key: "parc_retention_years", label: "Conservation des anciens détenteurs (années)", type: "number", help: "Au-delà, les noms sont anonymisés. À adapter à la réglementation de votre pays." },
  { key: "timing_warning_days", label: "Alerte de délai (jours)", type: "number" },
  { key: "restitution_phase1_unlock_days", label: "Délai avant la restitution phase 2 (jours)", type: "number" }
];

let orgWizard = null;

function orgWzEsc(value) {
  return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

async function orgWzFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json" };
  if (method !== "GET") {
    const tokenResponse = await fetch("/api/csrf-token", { credentials: "same-origin" });
    headers["X-CSRF-Token"] = (await tokenResponse.json()).token || "";
  }
  const response = await fetch(url, { credentials: "same-origin", ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Erreur ${response.status}`);
    error.code = data.code;
    throw error;
  }
  return data;
}

function orgWzParseTypes(raw) {
  return String(raw || "").split(",").map((part) => part.trim()).filter(Boolean).map((part) => {
    const index = part.indexOf(":");
    return { value: part.slice(0, index).trim(), label: part.slice(index + 1).trim() };
  });
}

function orgWzNewState(catalog) {
  const current = catalog.current;
  return {
    step: 1, catalog, plan: null, confirmed: false, error: "", busy: false, done: null,
    context: current.org_context || "public_collectivite",
    settings: Object.fromEntries(["org_name", "dpo_email", ...ORG_WIZARD_SETTINGS_FIELDS.map((f) => f.key)].map((key) => [key, current[key] || ""])),
    types: orgWzParseTypes(current.beneficiary_types),
    usedTypes: new Set(catalog.used_beneficiary_types || []),
    toggles: Object.fromEntries(catalog.resources.map((resource) => [resource.code, Boolean(resource.is_active)])),
    templates: {},
    custom: []
  };
}

function orgWzPayload(state) {
  const settings = { org_context: state.context, beneficiary_types: state.types.filter((t) => t.value || t.label).map((t) => `${t.value.trim()}:${t.label.trim()}`).join(",") };
  Object.entries(state.settings).forEach(([key, value]) => { settings[key] = value; });
  const activate = [], deactivate = [];
  state.catalog.resources.forEach((resource) => {
    if (state.toggles[resource.code] && !resource.is_active) activate.push(resource.code);
    if (!state.toggles[resource.code] && resource.is_active) deactivate.push(resource.code);
  });
  const create = Object.keys(state.templates).filter((id) => state.templates[id]).map((template) => ({ template }))
    .concat(state.custom.filter((item) => item.label.trim()).map((item) => ({ template: "custom", label: item.label.trim(), mode: item.mode })));
  return { settings, resources: { activate, deactivate, create } };
}

// --- Étapes : chacune est un objet { title, render(state) } -----------------------------------------------------------

const ORG_WIZARD_BODIES = [
  (state) => `
    <p class="panel-text">Choisissez ce qui ressemble le plus à votre structure : cela pré-remplit des suggestions, que vous pourrez toutes modifier. « Autre » convient à toute organisation, en France ou à l'étranger.</p>
    <div class="row g-2 mb-3" role="radiogroup" aria-label="Type d'organisation">
      ${Object.entries(state.catalog.contexts).map(([key, context]) => `
        <div class="col-md-6"><label class="border rounded p-3 d-block h-100${state.context === key ? " border-primary bg-primary bg-opacity-10" : ""}">
          <input class="form-check-input me-2" type="radio" name="orgWzContext" value="${orgWzEsc(key)}" ${state.context === key ? "checked" : ""}>
          <strong>${orgWzEsc(context.label)}</strong><br><span class="small text-muted">${orgWzEsc(context.description)}</span></label></div>`).join("")}
    </div>
    <div class="mb-3"><label class="form-label" for="orgWzName">Nom de l'organisation</label>
      <input class="form-control" id="orgWzName" data-setting="org_name" maxlength="200" value="${orgWzEsc(state.settings.org_name)}"></div>
    <div class="mb-3"><label class="form-label" for="orgWzDpo">Contact protection des données (DPO / référent)</label>
      <input class="form-control" id="orgWzDpo" type="email" data-setting="dpo_email" maxlength="200" value="${orgWzEsc(state.settings.dpo_email)}">
      <div class="form-text">Adresse à laquelle les personnes adressent leurs demandes sur leurs données. Obligatoire pour une autorité publique dans l'UE ; recommandée partout.</div></div>`,
  (state) => `
    <p class="panel-text">Les types de personnes qui reçoivent du matériel (agent, salarié, bénévole, membre…). Le libellé est libre, dans la langue de votre choix.</p>
    ${state.types.map((type, index) => {
      const locked = state.usedTypes.has(type.value);
      return `<div class="row g-2 mb-2 align-items-center" data-type-row="${index}">
        <div class="col-4"><input class="form-control" data-type-field="value" aria-label="Identifiant" placeholder="identifiant" maxlength="40" value="${orgWzEsc(type.value)}" ${locked ? "readonly" : ""}></div>
        <div class="col-6"><input class="form-control" data-type-field="label" aria-label="Libellé" placeholder="Libellé affiché" maxlength="60" value="${orgWzEsc(type.label)}"></div>
        <div class="col-2">${locked ? '<span class="small text-muted" title="Utilisé par des dossiers : on ne peut que changer le libellé">utilisé</span>' : `<button class="btn btn-outline-secondary btn-sm" type="button" data-type-remove="${index}" aria-label="Retirer">✕</button>`}</div>
      </div>`;
    }).join("")}
    <button class="btn btn-outline-secondary btn-sm mt-1" type="button" id="orgWzAddType">+ Ajouter un type</button>
    <button class="btn btn-outline-secondary btn-sm mt-1 ms-2" type="button" id="orgWzResetTypes">Reprendre les suggestions</button>
    <div class="form-text mt-2">L'identifiant (a-z, 0-9, _ et -) ne change plus une fois utilisé ; le libellé ne peut pas contenir de virgule, deux-points ni point-virgule.</div>`,
  (state) => {
    const pack = state.catalog.contexts[state.context].resources;
    const templates = Object.entries(state.catalog.templates);
    return `
    <p class="panel-text">Cochez les ressources que votre structure gère. Décocher masque une ressource des nouveaux dossiers ; elle reste réactivable, et celles déjà utilisées ne peuvent pas être masquées.</p>
    <button class="btn btn-outline-primary btn-sm mb-3" type="button" id="orgWzApplyPack">Appliquer les suggestions « ${orgWzEsc(state.catalog.contexts[state.context].label)} »</button>
    <div class="row g-2">${state.catalog.resources.map((resource) => `
      <div class="col-md-6"><label class="form-check border rounded p-2 ps-4 d-block">
        <input class="form-check-input" type="checkbox" data-resource-toggle="${orgWzEsc(resource.code)}" ${state.toggles[resource.code] ? "checked" : ""} ${resource.used && resource.is_active ? "disabled" : ""}>
        ${orgWzEsc(resource.label)}${pack.includes(resource.code) ? ' <span class="status-chip status-chip--active">suggérée</span>' : ""}${resource.used ? ' <span class="small text-muted">· déjà utilisée</span>' : ""}</label></div>`).join("")}</div>
    <p class="panel-eyebrow mt-4">Ajouter d'autres ressources</p>
    ${templates.map(([id, template]) => `<label class="form-check d-block"><input class="form-check-input" type="checkbox" data-template="${orgWzEsc(id)}" ${state.templates[id] ? "checked" : ""}> ${orgWzEsc(template.label)} <span class="small text-muted">— ${orgWzEsc(template.description)}</span></label>`).join("")}
    ${state.custom.map((item, index) => `<div class="row g-2 mt-1" data-custom-row="${index}">
      <div class="col-6"><input class="form-control" data-custom-field="label" placeholder="Nom de la ressource" maxlength="80" value="${orgWzEsc(item.label)}"></div>
      <div class="col-4"><select class="form-select" data-custom-field="mode" aria-label="Suivi">
        ${[["unit", "Objet identifié"], ["none", "Sans suivi individuel"], ["quantity", "Stock par quantité"], ["access", "Accès numérique"]].map(([mode, label]) => `<option value="${mode}" ${item.mode === mode ? "selected" : ""}>${label}</option>`).join("")}</select></div>
      <div class="col-2"><button class="btn btn-outline-secondary btn-sm" type="button" data-custom-remove="${index}" aria-label="Retirer">✕</button></div></div>`).join("")}
    <button class="btn btn-outline-secondary btn-sm mt-2" type="button" id="orgWzAddCustom">+ Ressource sur mesure</button>`;
  },
  (state) => `
    <p class="panel-text">Réglages de départ, tous modifiables plus tard dans Personnalisation.</p>
    ${ORG_WIZARD_SETTINGS_FIELDS.map((field) => `<div class="mb-3"><label class="form-label" for="orgWz_${field.key}">${orgWzEsc(field.label)}</label>
      <input class="form-control" id="orgWz_${field.key}" type="${field.type}" data-setting="${field.key}" maxlength="200" value="${orgWzEsc(state.settings[field.key])}">
      ${field.help ? `<div class="form-text">${orgWzEsc(field.help)}</div>` : ""}</div>`).join("")}`,
  (state) => {
    if (state.done) {
      return `<div class="alert alert-success">Configuration appliquée.${state.done.safety_copy ? ` Une copie de sécurité de la base a été faite (${orgWzEsc(state.done.safety_copy)}).` : " Attention : la copie de sécurité n'a pas pu être faite."}</div>`;
    }
    const plan = state.plan;
    if (!plan) return '<p class="text-muted">Calcul de l\'aperçu…</p>';
    const labels = { create: "Créer", activate: "Réactiver", deactivate: "Masquer", exists: "Déjà présent", blocked: "Refusé" };
    const changed = plan.settings.length || plan.resources.some((item) => ["create", "activate", "deactivate"].includes(item.action));
    return `
      <p class="panel-text">Voici exactement ce qui sera modifié. Rien n'est supprimé ni renommé, les dossiers ne sont pas touchés.</p>
      ${plan.settings.length ? `<h3 class="h6">Réglages</h3><ul class="small">${plan.settings.map((c) => `<li><strong>${orgWzEsc(c.key)}</strong> : « ${orgWzEsc(c.from)} » → « ${orgWzEsc(c.to)} »</li>`).join("")}</ul>` : ""}
      ${plan.resources.length ? `<h3 class="h6">Ressources</h3><ul class="small">${plan.resources.map((item) => `<li><span class="status-chip status-chip--${item.action === "blocked" ? "cancelled" : item.action === "exists" ? "draft" : "active"}">${labels[item.action]}</span> ${orgWzEsc(item.label || item.code)} <span class="text-muted">— ${orgWzEsc(item.reason)}</span></li>`).join("")}</ul>` : ""}
      ${plan.warnings.map((warning) => `<p class="text-warning small">⚠ ${orgWzEsc(warning)}</p>`).join("")}
      ${changed ? `<label class="form-check mt-3"><input class="form-check-input" type="checkbox" id="orgWzConfirm" ${state.confirmed ? "checked" : ""}> J'ai lu l'aperçu et je confirme. Une copie de sécurité de la base est faite avant application.</label>` : ""}`;
  }
];

function orgWzCanContinue(state) {
  if (state.step === 1) return Boolean(state.context);
  if (state.step === 2) return state.types.some((t) => t.value.trim() && t.label.trim());
  return true;
}

function orgWzRender() {
  const modal = document.getElementById("orgWizardModal");
  if (!modal || !orgWizard) return;
  const state = orgWizard;
  modal.querySelector("#orgWzProgress").innerHTML = ORG_WIZARD_STEPS.map((name, index) =>
    `<li class="restitution-steps__item${index + 1 === state.step ? " is-current" : ""}"><span${index + 1 === state.step ? ' aria-current="step"' : ""}><span class="restitution-steps__num">${index + 1}</span> ${orgWzEsc(name)}</span></li>`).join("");
  modal.querySelector("#orgWzBody").innerHTML = ORG_WIZARD_BODIES[state.step - 1](state);
  modal.querySelector("#orgWzError").textContent = state.error;
  modal.querySelector("#orgWzError").classList.toggle("d-none", !state.error);
  modal.querySelector("#orgWzBack").classList.toggle("d-none", state.step === 1 || Boolean(state.done));
  modal.querySelector("#orgWzNext").classList.toggle("d-none", state.step === 5);
  modal.querySelector("#orgWzNext").disabled = !orgWzCanContinue(state);
  const changed = state.plan && (state.plan.settings.length || state.plan.resources.some((item) => ["create", "activate", "deactivate"].includes(item.action)));
  const apply = modal.querySelector("#orgWzApply");
  apply.classList.toggle("d-none", state.step !== 5 || Boolean(state.done));
  apply.disabled = state.busy || !changed || !state.confirmed;
  modal.querySelector("#orgWzClose").textContent = state.done ? "Terminer" : "Fermer";
}

async function orgWzLoadPreview() {
  const state = orgWizard;
  state.plan = null; state.confirmed = false; state.error = "";
  orgWzRender();
  try {
    state.plan = await orgWzFetch("/api/admin/org-wizard/preview", { method: "POST", body: JSON.stringify(orgWzPayload(state)) });
  } catch (error) {
    state.error = error.message;
    state.step = 4;
  }
  orgWzRender();
}

async function orgWzApply() {
  const state = orgWizard;
  state.busy = true; state.error = ""; orgWzRender();
  try {
    state.done = await orgWzFetch("/api/admin/org-wizard/apply", {
      method: "POST", body: JSON.stringify({ ...orgWzPayload(state), plan_hash: state.plan.plan_hash, confirmed: true })
    });
  } catch (error) {
    state.error = error.code === "plan_changed" ? "Les données ont changé depuis l'aperçu : il est recalculé." : error.message;
    if (error.code === "plan_changed") { state.busy = false; return orgWzLoadPreview(); }
  }
  state.busy = false;
  orgWzRender();
}

function orgWzCloseWizard() {
  const modal = document.getElementById("orgWizardModal");
  const applied = Boolean(orgWizard && orgWizard.done);
  if (modal) { modal.classList.add("d-none"); modal.setAttribute("aria-hidden", "true"); }
  orgWizard = null;
  if (applied) window.location.reload();
}

function orgWzHandleInput(event) {
  const state = orgWizard;
  const target = event.target;
  if (target.dataset.setting) state.settings[target.dataset.setting] = target.value;
  const typeRow = target.closest("[data-type-row]");
  if (typeRow && target.dataset.typeField) state.types[Number(typeRow.dataset.typeRow)][target.dataset.typeField] = target.value;
  const customRow = target.closest("[data-custom-row]");
  if (customRow && target.dataset.customField) state.custom[Number(customRow.dataset.customRow)][target.dataset.customField] = target.value;
  if (target.dataset.resourceToggle) state.toggles[target.dataset.resourceToggle] = target.checked;
  if (target.dataset.template) state.templates[target.dataset.template] = target.checked;
  if (target.id === "orgWzConfirm") { state.confirmed = target.checked; orgWzRender(); }
  if (target.name === "orgWzContext") {
    const previousDefaults = state.catalog.contexts[state.context].beneficiary_types;
    const untouched = state.types.map((t) => `${t.value}:${t.label}`).join(",") === previousDefaults;
    state.context = target.value;
    if (untouched) state.types = orgWzParseTypes(state.catalog.contexts[state.context].beneficiary_types);
    orgWzRender();
  }
  const nextButton = document.getElementById("orgWzNext");
  if (nextButton) nextButton.disabled = !orgWzCanContinue(state);
}

function orgWzHandleClick(event) {
  const state = orgWizard;
  const click = (selector) => event.target.closest(selector);
  if (click("[data-orgwz-close]") || click("#orgWzClose")) return orgWzCloseWizard();
  if (click("#orgWzBack")) { state.step -= 1; return orgWzRender(); }
  if (click("#orgWzNext") && orgWzCanContinue(state)) { state.step += 1; return state.step === 5 ? orgWzLoadPreview() : orgWzRender(); }
  if (click("#orgWzApply")) return orgWzApply();
  if (click("#orgWzAddType")) { state.types.push({ value: "", label: "" }); return orgWzRender(); }
  if (click("#orgWzResetTypes")) { state.types = orgWzParseTypes(state.catalog.contexts[state.context].beneficiary_types); return orgWzRender(); }
  const removeType = click("[data-type-remove]");
  if (removeType) { state.types.splice(Number(removeType.dataset.typeRemove), 1); return orgWzRender(); }
  if (click("#orgWzAddCustom")) { state.custom.push({ label: "", mode: "unit" }); return orgWzRender(); }
  const removeCustom = click("[data-custom-remove]");
  if (removeCustom) { state.custom.splice(Number(removeCustom.dataset.customRemove), 1); return orgWzRender(); }
  if (click("#orgWzApplyPack")) {
    const pack = state.catalog.contexts[state.context].resources;
    state.catalog.resources.forEach((resource) => { state.toggles[resource.code] = (resource.used && resource.is_active) || pack.includes(resource.code); });
    return orgWzRender();
  }
}

async function openOrgWizard() {
  let modal = document.getElementById("orgWizardModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "password-generator-modal d-none";
    modal.id = "orgWizardModal";
    modal.innerHTML = `
      <div class="password-generator-modal__backdrop" data-orgwz-close="true"></div>
      <div class="password-generator-modal__dialog wizard-dialog" role="dialog" aria-modal="true" aria-labelledby="orgWzTitle">
        <div class="password-generator-modal__header">
          <div><p class="panel-eyebrow">Assistant</p><h2 class="section-title" id="orgWzTitle">Configurer mon organisation</h2></div>
          <button class="btn btn-outline-secondary btn-sm" type="button" id="orgWzClose">Fermer</button>
        </div>
        <ol class="restitution-steps__list mb-3" id="orgWzProgress" aria-label="Étapes"></ol>
        <div class="alert alert-danger d-none" id="orgWzError" role="alert"></div>
        <div id="orgWzBody"></div>
        <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
          <button class="btn btn-outline-secondary" type="button" id="orgWzBack">Précédent</button>
          <button class="btn btn-primary" type="button" id="orgWzNext">Suivant</button>
          <button class="btn btn-primary d-none" type="button" id="orgWzApply">Appliquer</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener("click", orgWzHandleClick);
    modal.addEventListener("input", orgWzHandleInput);
    modal.addEventListener("change", orgWzHandleInput);
  }
  try {
    orgWizard = orgWzNewState(await orgWzFetch("/api/admin/org-presets"));
  } catch (error) {
    alert(`Assistant indisponible : ${error.message}`);
    return;
  }
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  orgWzRender();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-open-org-wizard]").forEach((button) => button.addEventListener("click", openOrgWizard));
  if (new URLSearchParams(window.location.search).get("wizard") === "1") openOrgWizard();  // lien de la checklist ou fin d'installation
});
