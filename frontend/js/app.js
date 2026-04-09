const form = document.getElementById("dotationForm");
const draftStatus = document.getElementById("draftStatus");
const resumeHint = document.getElementById("resumeHint");
const pageLoader = document.getElementById("pageLoader");
let formDirty = false;
const DOSSIER_TYPE_LABELS = {
  arrivee: "Nouvelle arrivée",
  changement_service: "Changement de service",
  mise_a_jour: "Mise à jour de ressources",
  sortie: "Sortie / restitution"
};
const DEFAULT_SERVICE_OPTIONS = [];
let serviceOptions = [...DEFAULT_SERVICE_OPTIONS];
let dynamicResourceReferences = [];
let currentRestitutionData = {
  returnedAt: "",
  reason: "",
  notes: "",
  items: {}
};
let currentSignatureLink = null;
let formBootstrapWatchdogId = null;
let formBootstrapStage = "";

// Mapping central des équipements :
// on s'en sert pour générer la restitution, les résumés et certaines validations.
const restitutionStateLabels = {
  pending: "En attente",
  returned: "Restitué",
  returned_damaged: "Restitué abîmé",
  missing: "Non restitué",
  transferred: "Transféré",
  conforme: "Conforme",
  degrade: "Dégradé",
  non_restitue: "Non restitué",
  perdu: "Perdu",
  autre: "Autre"
};

const ASSIGNMENT_CONDITION_LABELS = {
  neuf: "Neuf",
  bon_etat: "Bon état",
  etat_usage: "État d'usage",
  degrade: "Dégradé"
};

let currentLockState = false;

function findResourceRefByCode(code) {
  return dynamicResourceReferences.find((r) => r.code === code) || null;
}

// Helpers de lecture du formulaire.
function getFieldValue(id) {
  const field = document.getElementById(id);
  if (!field || typeof field.value !== "string") {
    return "";
  }
  return field.value.trim() || "";
}


function normalizeDateInputValue(value) {
  if (!value) {
    return "";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offset = date.getTimezoneOffset();
  const localDate = new Date(date.getTime() - offset * 60000);
  return localDate.toISOString().slice(0, 10);
}

function formatDisplayDate(value) {
  if (!value) {
    return "";
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" }).format(date);
}

function formatAssignmentConditionLabel(value) {
  return ASSIGNMENT_CONDITION_LABELS[value] || value || "";
}

function buildAssignmentConditionSummary(item) {
  if (!item) {
    return "";
  }
  const parts = [];
  const conditionLabel = formatAssignmentConditionLabel(item.conditionAttribution);
  if (conditionLabel) {
    parts.push(`État à la remise : ${conditionLabel}`);
  }
  if (item.assignedAt) {
    parts.push(`Date d'attribution : ${formatDisplayDate(item.assignedAt)}`);
  }
  if (item.conditionNotes) {
    parts.push(`Observation : ${item.conditionNotes}`);
  }
  return parts.join(" - ");
}


function ensureAssignmentConditionFields() {
  // Les champs de condition d'attribution sont désormais générés
  // dynamiquement via buildDynamicResourceTrackingFields dans le rendu catalogue.
}

function createRepeatableRow(containerId, placeholder, value = "") {
  const row = document.createElement("div");
  row.className = "repeatable-list__row";
  row.innerHTML = `
    <input class="form-control" type="text" placeholder="${escapeAttribute(placeholder)}" value="${escapeAttribute(value)}">
    <button class="btn btn-outline-danger btn-sm" type="button">Supprimer</button>
  `;
  row.querySelector("button")?.addEventListener("click", () => {
    row.remove();
  });
  document.getElementById(containerId)?.appendChild(row);
}


function clearFieldError(field) {
  if (!field) {
    return;
  }
  field.classList.remove("field-invalid");
  field.setCustomValidity("");
  const help = field.parentElement.querySelector(`.field-help[data-for="${field.id}"]`);
  if (help) {
    help.remove();
  }
}

function setFieldError(field, message) {
  if (!field) {
    return;
  }
  clearFieldError(field);
  field.classList.add("field-invalid");
  field.setCustomValidity(message);
  const help = document.createElement("p");
  help.className = "field-help";
  help.dataset.for = field.id;
  help.textContent = message;
  field.parentElement.appendChild(help);
}

function clearProgressIndicators() {
  document.querySelectorAll(".progress-required-field").forEach((field) => field.classList.remove("progress-required-field"));
  document.querySelectorAll(".progress-required-surface").forEach((field) => field.classList.remove("progress-required-surface"));
  document.querySelectorAll(".progress-required-label").forEach((label) => label.classList.remove("progress-required-label"));
  document.querySelectorAll("[data-progress-required-badge]").forEach((badge) => badge.remove());
}

function resolveProgressIndicatorLabel(fieldId) {
  if (fieldId === "rgpdCheck") {
    return document.getElementById("rgpdCheck")?.closest("label.form-check")?.querySelector(".form-check-label") || null;
  }
  if (fieldId === "addCleBtn" || fieldId === "addZoneAlarmeBtn") {
    return document.getElementById(fieldId);
  }
  return document.querySelector(`label[for="${fieldId}"]`);
}

function addProgressIndicator(fieldId) {
  if (!fieldId) {
    return;
  }
  const field = document.getElementById(fieldId);
  if (field) {
    if (fieldId === "signature") {
      field.closest(".signature-wrap")?.classList.add("progress-required-surface");
    } else if (field.type === "checkbox") {
      field.closest("label.form-check")?.classList.add("progress-required-surface");
    } else if (field.tagName === "BUTTON") {
      field.classList.add("progress-required-surface");
    } else {
      field.classList.add("progress-required-field");
    }
  }

  const label = resolveProgressIndicatorLabel(fieldId);
  if (!label || label.querySelector("[data-progress-required-badge]")) {
    return;
  }
  label.classList.add("progress-required-label");
  const badge = document.createElement("span");
  badge.className = "progress-required-badge";
  badge.dataset.progressRequiredBadge = "true";
  badge.textContent = "À renseigner";
  label.appendChild(badge);
}

function collectProgressRequirementsFromForm() {
  const requirements = [];
  const pushRequirement = (fieldId, label) => requirements.push({ fieldId, label });

  if (!getFieldValue("nom")) {
    pushRequirement("nom", "Nom");
  }
  if (!getFieldValue("prenom")) {
    pushRequirement("prenom", "Prénom");
  }

  const qualite = document.querySelector('input[name="qualite"]:checked')?.value || "agent";
  const eluBlockDisabledForReq = Boolean(document.getElementById("eluBlock")?.dataset.eluBlockDisabled);
  if (qualite === "elu" && !eluBlockDisabledForReq) {
    if (!getFieldValue("mandat")) {
      pushRequirement("mandat", "Mandat");
    }
  } else if (!getServiceValue()) {
    pushRequirement("service", "Service");
  }

  dynamicResourceReferences.forEach((resource) => {
    const checkbox = document.getElementById(`dynamic_resource_${resource.id}`);
    if (!checkbox || !checkbox.checked) {
      return;
    }
    const fieldSchema = Array.isArray(resource.field_schema) ? resource.field_schema : [];
    if (!fieldSchema.length) {
      if (!getFieldValue(`dynamic_resource_details_${resource.id}`)) {
        pushRequirement(`dynamic_resource_details_${resource.id}`, `${resource.label} : précision`);
      }
    } else {
      fieldSchema.forEach((fieldDef) => {
        const value = getDynamicResourceFieldValue(resource.id, fieldDef.key);
        if (fieldDef.required && !value) {
          pushRequirement(`dynamic_resource_${resource.id}_${fieldDef.key}`, `${resource.label} : ${fieldDef.label}`);
        }
      });
    }
    if (usesDynamicResourceAssignmentDate(resource) && !getFieldValue(`dynamic_resource_assigned_at_${resource.id}`)) {
      pushRequirement(`dynamic_resource_assigned_at_${resource.id}`, `${resource.label} : date d'attribution`);
    }
  });

  if (!document.getElementById("rgpdCheck")?.checked) {
    pushRequirement("rgpdCheck", "Validation RGPD");
  }

  const signatureCanvas = document.getElementById("signature");
  if (signatureCanvas instanceof HTMLCanvasElement) {
    const blankCanvas = document.createElement("canvas");
    blankCanvas.width = signatureCanvas.width;
    blankCanvas.height = signatureCanvas.height;
    if (signatureCanvas.toDataURL() === blankCanvas.toDataURL()) {
      pushRequirement("signature", "Signature");
    }
  }

  return requirements;
}

function refreshProgressIndicators() {
  clearProgressIndicators();
  const requirements = collectProgressRequirementsFromForm();
  requirements.forEach((requirement) => addProgressIndicator(requirement.fieldId));
  const hint = document.getElementById("resumeHint");
  if (hint) {
    hint.textContent = requirements.length
      ? `${requirements.length} point(s) restent à renseigner pour finaliser la progression du dossier.`
      : "Tous les éléments utiles à la progression du dossier sont renseignés.";
  }
}

function bindProgressIndicatorRefresh() {
  if (!form || form.dataset.boundProgressIndicators) {
    return;
  }
  const refresh = () => refreshProgressIndicators();
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  form.dataset.boundProgressIndicators = "true";
}

function buildDynamicFieldInput(resource, field) {
  const inputId = `dynamic_resource_${resource.id}_${field.key}`;
  const placeholder = field.placeholder || field.label;
  const requiredAttribute = field.required ? " required" : "";
  const fieldType = field.type || "text";
  if (fieldType === "textarea") {
    return `
      <div>
        <label class="form-label" for="${escapeAttribute(inputId)}">${escapeHtml(field.label)}</label>
        <textarea class="form-control dynamic-resource-field" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="textarea"${requiredAttribute} placeholder="${escapeAttribute(placeholder)}"></textarea>
      </div>
    `;
  }
  if (fieldType === "select") {
    const options = Array.isArray(field.options) ? field.options : [];
    return `
      <div>
        <label class="form-label" for="${escapeAttribute(inputId)}">${escapeHtml(field.label)}</label>
        <select class="form-select dynamic-resource-field" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="select"${requiredAttribute}>
          <option value="">Sélectionner</option>
          ${options.map((option) => `<option value="${escapeAttribute(option)}">${escapeHtml(option)}</option>`).join("")}
        </select>
      </div>
    `;
  }
  if (fieldType === "checkbox") {
    return `
      <div class="pt-2">
        <label class="form-check">
          <input class="form-check-input dynamic-resource-field" type="checkbox" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="checkbox">
          <span class="form-check-label">${escapeHtml(field.label)}</span>
        </label>
      </div>
    `;
  }
  if (fieldType === "list") {
    const listId = `dynamic_resource_list_${resource.id}_${field.key}`;
    const suggestAttr = field.suggest ? ` data-suggest-key="${escapeAttribute(field.key)}"` : "";
    return `
      <div>
        <label class="form-label">${escapeHtml(field.label)}</label>
        <div id="${escapeAttribute(listId)}" class="repeatable-list dynamic-resource-list" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-placeholder="${escapeAttribute(placeholder)}"></div>
        <button class="btn btn-outline-secondary btn-sm mt-2 dynamic-resource-list-add" type="button" data-list-id="${escapeAttribute(listId)}" data-placeholder="${escapeAttribute(placeholder)}"${suggestAttr}>+ Ajouter</button>
      </div>
    `;
  }
  if (fieldType === "email_with_domain") {
    return `
      <div>
        <label class="form-label" for="${escapeAttribute(inputId)}">${escapeHtml(field.label)}</label>
        <div class="input-group">
          <input class="form-control dynamic-resource-field" type="text" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="email_with_domain"${requiredAttribute} placeholder="${escapeAttribute(placeholder)}" autocomplete="email">
          <select class="input-group-text form-select dynamic-resource-email-domain" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" style="max-width:220px;border-left:0"></select>
        </div>
      </div>
    `;
  }
  const type = ["date", "number"].includes(fieldType) ? fieldType : "text";
  if (field.suggest) {
    const datalistId = `fsugg-${escapeAttribute(field.key)}`;
    return `
      <div>
        <label class="form-label" for="${escapeAttribute(inputId)}">${escapeHtml(field.label)}</label>
        <input class="form-control dynamic-resource-field" type="${escapeAttribute(type)}" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="${escapeAttribute(type)}"${requiredAttribute} placeholder="${escapeAttribute(placeholder)}" list="${datalistId}" autocomplete="off">
        <datalist id="${datalistId}"></datalist>
      </div>
    `;
  }
  return `
    <div>
      <label class="form-label" for="${escapeAttribute(inputId)}">${escapeHtml(field.label)}</label>
      <input class="form-control dynamic-resource-field" type="${escapeAttribute(type)}" id="${escapeAttribute(inputId)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="${escapeAttribute(field.key)}" data-field-type="${escapeAttribute(type)}"${requiredAttribute} placeholder="${escapeAttribute(placeholder)}">
    </div>
  `;
}

function usesDynamicResourceAssignmentDate(resource) {
  if (resource && (Object.prototype.hasOwnProperty.call(resource, "hasAssignmentDate") || Object.prototype.hasOwnProperty.call(resource, "has_assignment_date"))) {
    return Boolean(resource.hasAssignmentDate ?? resource.has_assignment_date);
  }
  return true;
}

function usesDynamicResourceAssignmentCondition(resource) {
  if (resource && (Object.prototype.hasOwnProperty.call(resource, "hasAssignmentCondition") || Object.prototype.hasOwnProperty.call(resource, "has_assignment_condition"))) {
    return Boolean(resource.hasAssignmentCondition ?? resource.has_assignment_condition);
  }
  return false;
}

function usesDynamicResourceAssignmentNotes(resource) {
  if (resource && (Object.prototype.hasOwnProperty.call(resource, "hasAssignmentNotes") || Object.prototype.hasOwnProperty.call(resource, "has_assignment_notes"))) {
    return Boolean(resource.hasAssignmentNotes ?? resource.has_assignment_notes);
  }
  return false;
}

function buildDynamicResourceTrackingFields(resource) {
  const inputBlocks = [];
  if (usesDynamicResourceAssignmentDate(resource)) {
    inputBlocks.push(`
      <div>
        <label class="form-label" for="dynamic_resource_assigned_at_${escapeAttribute(resource.id)}">Date d'attribution</label>
        <input class="form-control dynamic-resource-field dynamic-resource-assigned-at" type="date" id="dynamic_resource_assigned_at_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}">
      </div>
    `);
  }
  if (usesDynamicResourceAssignmentCondition(resource)) {
    inputBlocks.push(`
      <div>
        <label class="form-label" for="dynamic_resource_condition_${escapeAttribute(resource.id)}">État à la remise</label>
        <select class="form-select dynamic-resource-field dynamic-resource-condition" id="dynamic_resource_condition_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}">
          <option value="">Sélectionner</option>
          <option value="neuf">Neuf</option>
          <option value="bon_etat">Bon état</option>
          <option value="etat_usage">État d'usage</option>
          <option value="degrade">Dégradé</option>
        </select>
      </div>
    `);
  }
  if (usesDynamicResourceAssignmentNotes(resource)) {
    inputBlocks.push(`
      <div>
        <label class="form-label" for="dynamic_resource_condition_notes_${escapeAttribute(resource.id)}">Observation de remise</label>
        <input class="form-control dynamic-resource-field dynamic-resource-condition-notes" id="dynamic_resource_condition_notes_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}" placeholder="Observation de remise">
      </div>
    `);
  }
  if (!inputBlocks.length) {
    return "";
  }
  return `<div class="subgrid">${inputBlocks.join("")}</div>`;
}

function syncDynamicResourceCard(resourceId) {
  const checkbox = document.getElementById(`dynamic_resource_${resourceId}`);
  const fieldsWrap = document.getElementById(`dynamic_resource_fields_wrap_${resourceId}`);
  if (!checkbox || !fieldsWrap) {
    return;
  }
  const checked = checkbox.checked;
  fieldsWrap.classList.toggle("d-none", !checked);
  checkbox.closest(".equipment-item")?.classList.toggle("is-selected", checked);
}

function bindDynamicResourceToggles() {
  dynamicResourceReferences.forEach((resource) => {
    const checkbox = document.getElementById(`dynamic_resource_${resource.id}`);
    if (!checkbox) {
      return;
    }
    if (!checkbox.dataset.boundDynamicToggle) {
      checkbox.addEventListener("change", () => syncDynamicResourceCard(resource.id));
      checkbox.dataset.boundDynamicToggle = "true";
    }
    syncDynamicResourceCard(resource.id);
  });
  initDynamicListFields();
  initDynamicEmailDomainFields();
}

function initDynamicListFields() {
  document.querySelectorAll(".dynamic-resource-list-add").forEach((button) => {
    if (button.dataset.boundListAdd) return;
    button.addEventListener("click", () => {
      const listId = button.dataset.listId;
      const placeholder = button.dataset.placeholder || "";
      const suggestKey = button.dataset.suggestKey || "";
      const container = document.getElementById(listId);
      if (!container) return;
      const row = document.createElement("div");
      row.className = "repeatable-list__row";
      const listAttr = suggestKey ? ` list="fsugg-${escapeAttribute(suggestKey)}"` : "";
      row.innerHTML = `
        <input class="form-control" type="text" placeholder="${escapeAttribute(placeholder)}"${listAttr} autocomplete="off">
        <button class="btn btn-outline-danger btn-sm" type="button">Supprimer</button>
      `;
      row.querySelector("button").addEventListener("click", () => row.remove());
      container.appendChild(row);
    });
    button.dataset.boundListAdd = "true";
  });
}

function initDynamicEmailDomainFields() {
  const domainSelects = document.querySelectorAll(".dynamic-resource-email-domain");
  if (!domainSelects.length) return;
  const cachedDomains = window._emailDomainsCache;
  const applyDomains = (domains) => {
    domainSelects.forEach((select) => {
      if (select.options.length > 0) return;
      if (!domains.length) {
        select.classList.add("d-none");
        return;
      }
      domains.forEach((domain) => {
        const option = document.createElement("option");
        option.value = domain;
        option.textContent = `@${domain}`;
        select.appendChild(option);
      });
    });
  };
  if (cachedDomains) {
    applyDomains(cachedDomains);
  } else {
    requestJson("/api/settings/public").then((settings) => {
      const domains = settings.email_domains || [];
      window._emailDomainsCache = domains;
      applyDomains(domains);
    }).catch(() => {});
  }
}

function summarizeDynamicResource(resource) {
  const fields = resource.fields || {};
  const values = Object.values(fields).map((value) => String(value || "").trim()).filter(Boolean);
  if (values.length) {
    return values.join(" - ");
  }
  return String(resource.details || "").trim();
}

function getDynamicResourceFieldValue(resourceId, fieldKey) {
  // Type list : collecte les valeurs depuis le conteneur répétable
  const listContainer = document.getElementById(`dynamic_resource_list_${resourceId}_${fieldKey}`);
  if (listContainer) {
    const values = Array.from(listContainer.querySelectorAll("input"))
      .map((input) => input.value.trim())
      .filter(Boolean);
    return values.length ? values : "";
  }
  const field = document.getElementById(`dynamic_resource_${resourceId}_${fieldKey}`);
  if (!field) {
    return "";
  }
  if (field.type === "checkbox") {
    return field.checked ? "Oui" : "";
  }
  // Type email_with_domain : ajouter le domaine sélectionné
  if (field.dataset.fieldType === "email_with_domain") {
    const value = field.value.trim();
    if (!value) return "";
    if (value.includes("@")) return value;
    const domainSelect = field.closest(".input-group")?.querySelector(".dynamic-resource-email-domain");
    const domain = domainSelect?.value;
    return domain ? `${value}@${domain}` : value;
  }
  return typeof field.value === "string" ? field.value.trim() : "";
}

function getDynamicResourceAssignmentData(resourceId) {
  return {
    assignedAt: getFieldValue(`dynamic_resource_assigned_at_${resourceId}`),
    conditionAttribution: getFieldValue(`dynamic_resource_condition_${resourceId}`),
    conditionNotes: getFieldValue(`dynamic_resource_condition_notes_${resourceId}`)
  };
}

function isDynamicResourceComplete(resource) {
  if (!resource?.selected) {
    return false;
  }
  const fieldSchema = Array.isArray(resource.fieldSchema)
    ? resource.fieldSchema
    : (Array.isArray(resource.field_schema) ? resource.field_schema : []);
  const fieldValues = resource.fields || {};
  if (fieldSchema.length) {
    const hasMissingRequiredField = fieldSchema.some((field) => field.required && !String(fieldValues[field.key] || "").trim());
    if (hasMissingRequiredField) {
      return false;
    }
  } else if (!String(resource.details || "").trim()) {
    return false;
  }
  if (usesDynamicResourceAssignmentDate(resource) && !String(resource.assignedAt || "").trim()) {
    return false;
  }
  return true;
}

function getCurrentDateTimeLocal() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const localDate = new Date(now.getTime() - offset * 60000);
  return localDate.toISOString().slice(0, 16);
}

function normalizeDateTimeLocal(value) {
  if (!value) {
    return "";
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    return value;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const offset = date.getTimezoneOffset();
  const localDate = new Date(date.getTime() - offset * 60000);
  return localDate.toISOString().slice(0, 16);
}

function getServiceValue() {
  const serviceField = document.getElementById("service");
  if (!serviceField) {
    return "";
  }
  return serviceField.value === "__custom__" ? getFieldValue("service_custom") : serviceField.value;
}

function getServiceSelectValue(fieldId, customFieldId) {
  const serviceField = document.getElementById(fieldId);
  if (!serviceField) {
    return "";
  }
  return serviceField.value === "__custom__" ? getFieldValue(customFieldId) : serviceField.value;
}

function syncServiceCustomField(fieldId = "service", customFieldId = "service_custom") {
  const serviceField = document.getElementById(fieldId);
  const customField = document.getElementById(customFieldId);
  if (!serviceField || !customField) {
    return;
  }

  const isCustom = serviceField.value === "__custom__";
  customField.classList.toggle("d-none", !isCustom);
  if (!isCustom) {
    customField.value = "";
  }
}

function setServiceSelectValue(value, fieldId = "service", customFieldId = "service_custom") {
  const serviceField = document.getElementById(fieldId);
  const customField = document.getElementById(customFieldId);
  if (!serviceField) {
    return;
  }

  if (value && serviceOptions.includes(value)) {
    serviceField.value = value;
    if (customField) {
      customField.value = "";
    }
    syncServiceCustomField(fieldId, customFieldId);
    return;
  }

  if (value) {
    serviceField.value = "__custom__";
    if (customField) {
      customField.value = value;
    }
    syncServiceCustomField(fieldId, customFieldId);
    return;
  }

  serviceField.value = "";
  if (customField) {
    customField.value = "";
  }
  syncServiceCustomField(fieldId, customFieldId);
}

function setServiceValue(value) {
  setServiceSelectValue(value, "service", "service_custom");
}

function getServiceDestinationValue() {
  return getServiceSelectValue("service_destination", "service_destination_custom");
}

function setServiceDestinationValue(value) {
  setServiceSelectValue(value, "service_destination", "service_destination_custom");
}

function renderServiceOptions(options = []) {
  const serviceField = document.getElementById("service");
  const destinationField = document.getElementById("service_destination");
  if (!serviceField && !destinationField) {
    return;
  }

  const currentValue = getServiceValue();
  const currentDestinationValue = getServiceDestinationValue();
  serviceOptions = options.length ? [...options] : [...DEFAULT_SERVICE_OPTIONS];
  const optionsMarkup = `
    <option value="">Sélectionner un service</option>
    ${serviceOptions.map((option) => `<option value="${escapeAttribute(option)}">${escapeHtml(option)}</option>`).join("")}
    <option value="__custom__">Autre...</option>
  `;
  if (serviceField) {
    serviceField.innerHTML = optionsMarkup;
  }
  if (destinationField) {
    destinationField.innerHTML = optionsMarkup;
  }
  setServiceValue(currentValue);
  setServiceDestinationValue(currentDestinationValue);
}

async function loadServiceOptions() {
  try {
    const services = await requestJson("/api/reference/services");
    const labels = services
      .map((service) => String(service.label || "").trim())
      .filter(Boolean);
    renderServiceOptions(labels);
  } catch (error) {
    renderServiceOptions(DEFAULT_SERVICE_OPTIONS);
  }
}

async function loadDynamicResourceReferences() {
  const genericMaterialContainer = document.getElementById("dynamicResourcesMaterialGrid");
  const genericImmaterialContainer = document.getElementById("dynamicResourcesImmaterialGrid");
  const genericSection = document.getElementById("dynamicResourcesGenericSection");
  const genericMaterialWrap = document.getElementById("dynamicResourcesGenericMaterialWrap");
  const genericImmaterialWrap = document.getElementById("dynamicResourcesGenericImmaterialWrap");
  const dsiMaterialContainer = document.getElementById("dynamicResourcesDsiMaterialGrid");
  const dsiImmaterialContainer = document.getElementById("dynamicResourcesDsiImmaterialGrid");
  const batimentMaterialContainer = document.getElementById("dynamicResourcesBatimentMaterialGrid");
  const batimentImmaterialContainer = document.getElementById("dynamicResourcesBatimentImmaterialGrid");
  const batimentImmaterialWrap = document.getElementById("dynamicResourcesBatimentImmaterialWrap");
  const dynamicSectionsContainer = document.getElementById("dynamicServiceSections");
  const emptyState = document.getElementById("dynamicResourcesEmpty");
  if (
    !genericMaterialContainer || !genericImmaterialContainer || !genericSection
    || !dsiMaterialContainer || !dsiImmaterialContainer
    || !batimentMaterialContainer || !batimentImmaterialContainer
    || !dynamicSectionsContainer || !emptyState
  ) {
    return;
  }

  try {
    const references = await requestJson("/api/reference/resources");
    dynamicResourceReferences = references;
  } catch (error) {
    dynamicResourceReferences = [];
  }

  if (!dynamicResourceReferences.length) {
    genericMaterialContainer.innerHTML = "";
    genericImmaterialContainer.innerHTML = "";
    dsiMaterialContainer.innerHTML = "";
    dsiImmaterialContainer.innerHTML = "";
    batimentMaterialContainer.innerHTML = "";
    batimentImmaterialContainer.innerHTML = "";
    dynamicSectionsContainer.innerHTML = "";
    emptyState.classList.remove("d-none");
    genericSection.classList.add("d-none");
    genericMaterialWrap?.classList.add("d-none");
    genericImmaterialWrap?.classList.add("d-none");
    return;
  }

  const buildResourceCard = (resource) => {
    const fieldSchema = Array.isArray(resource.field_schema) ? resource.field_schema : [];
    const fieldsMarkup = fieldSchema.length
      ? `<div class="subgrid">${fieldSchema.map((field) => buildDynamicFieldInput(resource, field)).join("")}</div>`
      : `
        <div class="mt-3">
          <label class="form-label" for="dynamic_resource_details_${escapeAttribute(resource.id)}">Précision / Détails</label>
          <input class="form-control dynamic-resource-field" id="dynamic_resource_details_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="details" placeholder="Numéro de série, taille, couleur…">
        </div>
      `;
    const trackingMarkup = buildDynamicResourceTrackingFields(resource);
    const descriptionMarkup = resource.description
      ? `<p class="equipment-item__desc">${escapeHtml(resource.description)}</p>`
      : "";

    return `
      <div class="equipment-item">
        <div class="equipment-item__header">
          <label class="equipment-toggle">
            <input type="checkbox" id="dynamic_resource_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}" data-resource-trigger="${escapeAttribute(resource.trigger_key || "")}">
            <span>${escapeHtml(resource.label)}</span>
          </label>
          <span class="equipment-item__hint">${escapeHtml(resource.issuer_service || "Service non renseigné")} · ${escapeHtml(resource.category || "Ressource")}</span>
        </div>
        ${descriptionMarkup}
        <div id="dynamic_resource_fields_wrap_${escapeAttribute(resource.id)}" class="d-none equipment-item__body">
          ${fieldsMarkup}
          ${trackingMarkup}
        </div>
      </div>
    `;
  };

  const grouped = {
    dsi: { materiel: [], immateriel: [] },
    batiment: { materiel: [], immateriel: [] },
    generic: { materiel: [], immateriel: [] },
    services: new Map()
  };

  dynamicResourceReferences.forEach((resource) => {
    const issuer = normalizeServiceName(resource.issuer_service);
    const issuerLabel = formatIssuerServiceLabel(resource.issuer_service);
    const category = resource.category === "immateriel" ? "immateriel" : "materiel";
    if (issuer === "dsi") {
      grouped.dsi[category].push(resource);
      return;
    }
    if (issuer === "batiment") {
      grouped.batiment[category].push(resource);
      return;
    }
    if (issuer) {
      if (!grouped.services.has(issuer)) {
        grouped.services.set(issuer, {
          label: issuerLabel,
          materiel: [],
          immateriel: []
        });
      }
      grouped.services.get(issuer)[category].push(resource);
      return;
    }
    grouped.generic[category].push(resource);
  });

  dsiMaterialContainer.innerHTML = grouped.dsi.materiel.map(buildResourceCard).join("");
  dsiImmaterialContainer.innerHTML = grouped.dsi.immateriel.map(buildResourceCard).join("");
  batimentMaterialContainer.innerHTML = grouped.batiment.materiel.map(buildResourceCard).join("");
  batimentImmaterialContainer.innerHTML = grouped.batiment.immateriel.map(buildResourceCard).join("");
  genericMaterialContainer.innerHTML = grouped.generic.materiel.map(buildResourceCard).join("");
  genericImmaterialContainer.innerHTML = grouped.generic.immateriel.map(buildResourceCard).join("");

  batimentImmaterialWrap?.classList.toggle("d-none", grouped.batiment.immateriel.length === 0);
  genericMaterialWrap?.classList.toggle("d-none", grouped.generic.materiel.length === 0);
  genericImmaterialWrap?.classList.toggle("d-none", grouped.generic.immateriel.length === 0);

  dynamicSectionsContainer.innerHTML = Array.from(grouped.services.values())
    .sort((left, right) => left.label.localeCompare(right.label, "fr"))
    .map((group) => `
      <section class="content-card">
        <div class="section-heading">
          <div>
            <p class="panel-eyebrow">${escapeHtml(group.label)}</p>
            <h3 class="section-title">Ressources remises par le service ${escapeHtml(group.label)}</h3>
          </div>
        </div>
        <div class="resource-kind-block">
          <div class="resource-kind-block__header">
            <h4 class="resource-kind-block__title">Ressources matérielles</h4>
          </div>
          <div class="equipment-grid equipment-grid--compact">
            ${group.materiel.map(buildResourceCard).join("")}
          </div>
        </div>
        ${group.immateriel.length ? `
        <div class="resource-kind-block mt-4">
          <div class="resource-kind-block__header">
            <h4 class="resource-kind-block__title">Ressources immatérielles</h4>
          </div>
          <div class="equipment-grid equipment-grid--compact">
            ${group.immateriel.map(buildResourceCard).join("")}
          </div>
        </div>` : ""}
        ${(!group.materiel.length && !group.immateriel.length) ? `
        <div class="empty-state">
          <p>Aucune ressource active pour ce service.</p>
        </div>
        ` : ""}
      </section>
    `)
    .join("");
  const hasGenericResources = (grouped.generic.materiel.length + grouped.generic.immateriel.length) > 0;
  genericSection.classList.toggle("d-none", !hasGenericResources);
  emptyState.classList.toggle("d-none", hasGenericResources);
  bindDynamicResourceToggles();
}

function getAdditionalResourcesData() {
  return dynamicResourceReferences.map((resource) => ({
    id: resource.id,
    code: resource.code,
    label: resource.label,
    description: resource.description || "",
    category: resource.category,
    issuerService: resource.issuer_service,
    triggerKey: resource.trigger_key || "",
    requiresReturn: Boolean(resource.requires_return),
    hasAssignmentDate: usesDynamicResourceAssignmentDate(resource),
    hasAssignmentCondition: usesDynamicResourceAssignmentCondition(resource),
    hasAssignmentNotes: usesDynamicResourceAssignmentNotes(resource),
    displayOrder: Number(resource.display_order || 100),
    selected: Boolean(document.getElementById(`dynamic_resource_${resource.id}`)?.checked),
    fieldSchema: Array.isArray(resource.field_schema) ? resource.field_schema : [],
    fields: Object.fromEntries(
      (Array.isArray(resource.field_schema) ? resource.field_schema : [])
        .map((field) => [field.key, getDynamicResourceFieldValue(resource.id, field.key)])
        .filter(([, value]) => value)
    ),
    details: getFieldValue(`dynamic_resource_details_${resource.id}`),
    ...getDynamicResourceAssignmentData(resource.id)
  })).map((resource) => ({
    ...resource,
    details: resource.details || summarizeDynamicResource(resource)
  })).filter((resource) => (
    resource.selected
    || resource.details
    || Object.keys(resource.fields).length
    || resource.assignedAt
    || resource.conditionAttribution
    || resource.conditionNotes
  ));
}

function populateAdditionalResources(data = {}) {
  const resources = data.resources?.additional || [];
  resources.forEach((resource) => {
    const checkbox = document.getElementById(`dynamic_resource_${resource.id}`);
    const details = document.getElementById(`dynamic_resource_details_${resource.id}`);
    if (checkbox) {
      checkbox.checked = Boolean(resource.selected);
    }
    if (details) {
      details.value = resource.details || "";
    }
    const assignedAtField = document.getElementById(`dynamic_resource_assigned_at_${resource.id}`);
    if (assignedAtField) {
      assignedAtField.value = normalizeDateInputValue(resource.assignedAt || "");
    }
    const conditionField = document.getElementById(`dynamic_resource_condition_${resource.id}`);
    if (conditionField) {
      conditionField.value = resource.conditionAttribution || "";
    }
    const notesField = document.getElementById(`dynamic_resource_condition_notes_${resource.id}`);
    if (notesField) {
      notesField.value = resource.conditionNotes || "";
    }
    // Compat ascendante : l'ancien champ "imei" a été renommé en "numeroSerie"
    const fields = { ...(resource.fields || {}) };
    if (fields.imei && !fields.numeroSerie) {
      fields.numeroSerie = fields.imei;
      delete fields.imei;
    }
    Object.entries(fields).forEach(([fieldKey, value]) => {
      // Type list : peupler les lignes répétables
      const listContainer = document.getElementById(`dynamic_resource_list_${resource.id}_${fieldKey}`);
      if (listContainer && Array.isArray(value)) {
        const placeholder = listContainer.dataset.placeholder || "";
        const suggestKey = document.querySelector(`[data-list-id="${CSS.escape(`dynamic_resource_list_${resource.id}_${fieldKey}`)}"][data-suggest-key]`)?.dataset?.suggestKey || "";
        const listAttr = suggestKey ? ` list="fsugg-${escapeAttribute(suggestKey)}"` : "";
        value.forEach((v) => {
          if (!String(v).trim()) return;
          const row = document.createElement("div");
          row.className = "repeatable-list__row";
          row.innerHTML = `
            <input class="form-control" type="text" placeholder="${escapeAttribute(placeholder)}" value="${escapeAttribute(v)}"${listAttr} autocomplete="off">
            <button class="btn btn-outline-danger btn-sm" type="button">Supprimer</button>
          `;
          row.querySelector("button").addEventListener("click", () => row.remove());
          listContainer.appendChild(row);
        });
        return;
      }
      const field = document.getElementById(`dynamic_resource_${resource.id}_${fieldKey}`);
      if (field) {
        if (field.type === "checkbox") {
          field.checked = value === true || value === "true" || value === "Oui" || value === "on";
        } else if (field.dataset.fieldType === "email_with_domain" && typeof value === "string" && value.includes("@")) {
          // Séparer le préfixe et le domaine pour l'affichage
          const domainSelect = field.closest(".input-group")?.querySelector(".dynamic-resource-email-domain");
          if (domainSelect?.options.length) {
            const parts = value.split("@");
            for (const option of domainSelect.options) {
              if (option.value === parts[1]) {
                domainSelect.value = parts[1];
                field.value = parts[0];
                return;
              }
            }
          }
          field.value = value;
        } else {
          field.value = value || "";
        }
      }
    });
  });
  bindDynamicResourceToggles();
  refreshProgressIndicators();
}

function syncDossierTypeUi() {
  const dossierType = normalizeDossierType(document.getElementById("dossier_type").value || "arrivee");
  const destinationBlock = document.getElementById("serviceDestinationBlock");
  if (destinationBlock) {
    destinationBlock.classList.toggle("d-none", dossierType !== "changement_service");
  }
}


function applyLockState(locked) {
  // Une fiche signée complète passe en lecture seule.
  // L'utilisateur peut encore consulter / imprimer, mais plus modifier.
  currentLockState = locked;
  form.classList.toggle("form-locked", locked);

  form.querySelectorAll("input, select, textarea, button").forEach((element) => {
    if (element.id === "exportPdfBtn") {
      element.disabled = false;
      return;
    }
    if (element.getAttribute("onclick")) {
      element.disabled = false;
      return;
    }
    element.disabled = locked;
  });

  if (resumeHint && locked) {
    resumeHint.textContent = "Fiche signée : elle est maintenant verrouillée et disponible uniquement en consultation et impression.";
  }
}

function showPageLoader(message) {
  if (!pageLoader) {
    return;
  }
  if (message) {
    const paragraph = pageLoader.querySelector("p");
    if (paragraph) {
      paragraph.textContent = message;
    }
  }
  pageLoader.classList.remove("is-hidden");
}

function hidePageLoader() {
  clearFormBootstrapWatchdog();
  pageLoader.classList.add("is-hidden");
}

function setFormBootstrapStage(stage, loaderMessage = "") {
  formBootstrapStage = stage || "";
  if (loaderMessage) {
    showPageLoader(loaderMessage);
  }
}

function clearFormBootstrapWatchdog() {
  if (formBootstrapWatchdogId) {
    window.clearTimeout(formBootstrapWatchdogId);
    formBootstrapWatchdogId = null;
  }
}

function startFormBootstrapWatchdog() {
  clearFormBootstrapWatchdog();
  formBootstrapWatchdogId = window.setTimeout(() => {
    const stageLabel = formBootstrapStage || "initialisation";
    console.error("Chargement de la fiche bloqué", { stage: stageLabel });
    hidePageLoader();
    alert(`Le chargement de la fiche prend trop de temps à l'étape : ${stageLabel}.`);
  }, 20000);
}

function failFormBootstrap(error, fallbackMessage) {
  console.error(fallbackMessage, error);
  clearFormBootstrapWatchdog();
  hidePageLoader();
  const message = error?.message || fallbackMessage || "Impossible de charger correctement la fiche.";
  alert(message);
}


function toggleField(id, visible) {
  const element = document.getElementById(id);
  if (!element) {
    return;
  }
  element.classList.toggle("d-none", !visible);
}

function initConditionalBlocks() {
  // Gere les blocs qui apparaissent selon les cases cochees.
  document.querySelectorAll("[data-target]").forEach((checkbox) => {
    const sync = () => {
      toggleField(checkbox.dataset.target, checkbox.checked);
    };
    if (!checkbox.dataset.boundToggle) {
      checkbox.addEventListener("change", sync);
      checkbox.dataset.boundToggle = "true";
    }
    sync();
  });
}

function initRepeatableResourceLists() {
  const clesButton = document.getElementById("addCleBtn");
  const zoneButton = document.getElementById("addZoneAlarmeBtn");

  if (clesButton && !clesButton.dataset.boundRepeatable) {
    clesButton.addEventListener("click", () => {
      createRepeatableRow("clesRows", "Référence ou libellé de clé");
    });
    clesButton.dataset.boundRepeatable = "true";
  }

  if (zoneButton && !zoneButton.dataset.boundRepeatable) {
    zoneButton.addEventListener("click", () => {
      createRepeatableRow("zoneAlarmeRows", "Zone alarme");
    });
    zoneButton.dataset.boundRepeatable = "true";
  }
}

function initQualite() {
  const radios = document.querySelectorAll('input[name="qualite"]');
  if (!radios.length) {
    window.addEventListener("qualite:ready", () => initQualite(), { once: true });
    return;
  }
  const service = document.getElementById("service");
  const serviceCustom = document.getElementById("service_custom");
  const serviceDestination = document.getElementById("service_destination");
  const serviceDestinationCustom = document.getElementById("service_destination_custom");
  const fonction = document.getElementById("fonction");
  const mandat = document.getElementById("mandat");
  const serviceFieldBlock = document.getElementById("serviceFieldBlock");
  const fonctionFieldBlock = document.getElementById("fonctionFieldBlock");

  const sync = () => {
    const selectedInput = document.querySelector('input[name="qualite"]:checked');
    const selected = selectedInput ? selectedInput.value : (radios[0]?.value || "agent");
    const eluBlockEl = document.getElementById("eluBlock");
    const eluBlockDisabled = Boolean(eluBlockEl?.dataset.eluBlockDisabled);
    const isElu = selected === "elu" && !eluBlockDisabled;

    toggleField("eluBlock", isElu);
    toggleField("serviceFieldBlock", !isElu);
    toggleField("fonctionFieldBlock", !isElu);

    if (service) {
      service.disabled = isElu;
      if (isElu) {
        service.value = "";
      }
    }
      if (serviceCustom) {
        serviceCustom.disabled = isElu;
        if (isElu) {
          serviceCustom.value = "";
        }
      }
      syncServiceCustomField();
      if (serviceDestination) {
        serviceDestination.disabled = isElu;
        if (isElu) {
          serviceDestination.value = "";
        }
      }
      if (serviceDestinationCustom) {
        serviceDestinationCustom.disabled = isElu;
        if (isElu) {
          serviceDestinationCustom.value = "";
        }
      }
      syncServiceCustomField("service_destination", "service_destination_custom");

      if (fonction) {
        fonction.disabled = isElu;
        if (isElu) {
        fonction.value = "";
      }
    }

    if (mandat) {
      mandat.disabled = !isElu;
      if (!isElu) {
        mandat.value = "";
      }
    }
  };

  radios.forEach((radio) => {
    if (!radio.dataset.boundQualite) {
      radio.addEventListener("change", sync);
      radio.dataset.boundQualite = "true";
    }
  });
  if (service && !service.dataset.boundService) {
    service.addEventListener("change", syncServiceCustomField);
    service.dataset.boundService = "true";
  }
  if (!document.querySelector('input[name="qualite"]:checked') && radios[0]) {
    radios[0].checked = true;
  }
  sync();
}

function validateFixedResourceSelection() {
  // Toutes les ressources sont désormais validées via validateDynamicResourceSelection.
  return [];
}

function validateDynamicResourceSelection() {
  const issues = [];
  document.querySelectorAll(".dynamic-resource-field").forEach((field) => clearFieldError(field));

  dynamicResourceReferences.forEach((resource) => {
    const checkbox = document.getElementById(`dynamic_resource_${resource.id}`);
    if (!checkbox || !checkbox.checked) {
      return;
    }
    const fieldSchema = Array.isArray(resource.field_schema) ? resource.field_schema : [];
    if (!fieldSchema.length) {
      const detailsField = document.getElementById(`dynamic_resource_details_${resource.id}`);
      const detailsValue = detailsField ? detailsField.value.trim() || "" : "";
      if (!detailsValue) {
        setFieldError(detailsField, "Précision obligatoire.");
        issues.push(`${resource.label} : précision manquante`);
      }
      return;
    }

    fieldSchema.forEach((fieldDef) => {
      const field = document.getElementById(`dynamic_resource_${resource.id}_${fieldDef.key}`);
      const value = getDynamicResourceFieldValue(resource.id, fieldDef.key);
      if (fieldDef.required && !value) {
        setFieldError(field, `${fieldDef.label} obligatoire.`);
        issues.push(`${resource.label} : ${fieldDef.label} manquant`);
        return;
      }
    });

    if (usesDynamicResourceAssignmentDate(resource)) {
      const assignedAtField = document.getElementById(`dynamic_resource_assigned_at_${resource.id}`);
      if (!getFieldValue(`dynamic_resource_assigned_at_${resource.id}`)) {
        setFieldError(assignedAtField, "Date d'attribution obligatoire.");
        issues.push(`${resource.label} : date d'attribution manquante`);
      }
    }
  });

  return issues;
}

function collectResourceValidationIssues() {
  return [
    ...validateFixedResourceSelection(),
    ...validateDynamicResourceSelection()
  ];
}

function updateStatusInfo(status = "draft") {
  const statusDisplay = document.getElementById("workflowStatusDisplay");
  const statusHint = document.getElementById("workflowStatusHint");
  if (statusDisplay) {
    statusDisplay.textContent = formatStatusLabel(status);
  }
  if (!statusHint) {
    return;
  }

  const hints = {
    draft: "Le dossier reste modifiable tant qu'il n'est pas signé et validé.",
    partial_assignment: "Le dossier reste modifiable car l'attribution est partielle ou parce qu'au moins une ressource cochée reste incomplète.",
    awaiting_signature: "Le dossier est prêt et n'attend plus que la signature finale.",
    active: "Le dossier est verrouillé et la restitution se gère depuis la page dédiée.",
    returned: "Le dossier a été restitué. Les détails restent consultables depuis la restitution.",
    partial_return: "Une partie des ressources a été restituée. Le détail est visible dans la page de restitution.",
    cancelled: "Le dossier a été annulé et n'entre plus dans le flux normal d'attribution."
  };
  statusHint.textContent = hints[status] || hints.draft;
}

function renderRestitutionSummary() {
  const summary = document.getElementById("restitutionSummary");
  const hint = document.getElementById("restitutionSummaryHint");
  if (!summary || !hint) {
    return;
  }

  const restitution = currentRestitutionData || {};
  const hasGlobalInfo = Boolean(restitution.returnedAt || restitution.reason || restitution.notes);
  const itemEntries = Object.entries(restitution.items || {});
  const hasItems = itemEntries.length > 0;

  if (!hasGlobalInfo && !hasItems) {
    summary.classList.add("d-none");
    summary.innerHTML = "";
    hint.textContent = "La restitution ne se renseigne plus dans ce formulaire. Elle se gère depuis la page dédiée accessible depuis l'accueil sur les attributions actives.";
    return;
  }

  hint.textContent = "Les informations ci-dessous proviennent du formulaire de restitution et restent consultables ici en lecture seule.";
  const reasonLabels = {
    fin_de_fonction: "Fin de fonction",
    demission: "Démission",
    mutation: "Mutation",
    fin_de_mandat: "Fin de mandat",
    autre: "Autre"
  };

  const itemLines = itemEntries.map(([key, state]) => {
    const ref = findResourceRefByCode(key);
    const label = ref?.label || key;
    const parts = [
      restitutionStateLabels[state.state] || state.state || "État non renseigné",
      state.notes || ""
    ].filter(Boolean);
    return `<li><strong>${escapeHtml(label)}</strong>${parts.length ? ` : ${escapeHtml(parts.join(" - "))}` : ""}</li>`;
  }).join("");

  summary.innerHTML = `
    <div class="print-grid mt-3">
      <div class="print-line"><strong>Date</strong><span>${escapeHtml(restitution.returnedAt || "-")}</span></div>
      <div class="print-line"><strong>Motif</strong><span>${escapeHtml(reasonLabels[restitution.reason] || restitution.reason || "-")}</span></div>
    </div>
    <div class="print-line mt-3"><strong>Observations</strong><span>${escapeHtml(restitution.notes || "-")}</span></div>
    <div class="mt-3">
      ${hasItems ? `<ul class="print-list">${itemLines}</ul>` : "<p class='rgpd-text mb-0'>Aucun détail par ressource n'a été saisi.</p>"}
    </div>
  `;
  summary.classList.remove("d-none");
}

function initSignaturePad() {
  // Signature canvas simple, compatible souris et tactile.
  const canvas = document.getElementById("signature");
  const clearButton = document.getElementById("clearSignatureBtn");

  if (!canvas) {
    return { clear: () => {}, restore: () => {}, toDataUrl: () => "" };
  }

  const context = canvas.getContext("2d");
  let isDrawing = false;
  let hasDrawn = false;

  function setupContext() {
    context.lineWidth = 2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#17354d";
  }

  function resizeCanvas() {
    const snapshot = hasDrawn ? canvas.toDataURL() : null;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    setupContext();

    if (snapshot) {
      const image = new Image();
      image.onload = () => {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        hasDrawn = true;
      };
      image.src = snapshot;
    }
  }

  function getPoint(event) {
    const rect = canvas.getBoundingClientRect();
    const source = event.touches?.[0] || event;
    return {
      x: source.clientX - rect.left,
      y: source.clientY - rect.top
    };
  }

  function startDrawing(event) {
    event.preventDefault();
    const point = getPoint(event);
    isDrawing = true;
    context.beginPath();
    context.moveTo(point.x, point.y);
  }

  function draw(event) {
    if (!isDrawing) {
      return;
    }
    event.preventDefault();
    const point = getPoint(event);
    context.lineTo(point.x, point.y);
    context.stroke();
    hasDrawn = true;
  }

  function stopDrawing() {
    isDrawing = false;
  }

  function clear() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    hasDrawn = false;
  }

  clearButton.addEventListener("click", clear);
  canvas.addEventListener("mousedown", startDrawing);
  canvas.addEventListener("mousemove", draw);
  canvas.addEventListener("mouseup", stopDrawing);
  canvas.addEventListener("mouseleave", stopDrawing);
  canvas.addEventListener("touchstart", startDrawing, { passive: false });
  canvas.addEventListener("touchmove", draw, { passive: false });
  canvas.addEventListener("touchend", stopDrawing);
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  return {
    clear,
    restore(dataUrl) {
      clear();
      if (!dataUrl) {
        return;
      }
      const image = new Image();
      image.onload = () => {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        hasDrawn = true;
      };
      image.src = dataUrl;
    },
    toDataUrl: () => (hasDrawn ? canvas.toDataURL("image/png") : "")
  };
}

function migrateLegacyResourcesToAdditional(data) {
  // Pour les dossiers sauvegardés avec l'ancien format (materiel/immateriel hardcodé),
  // on convertit les données en entrées resources.additional exploitables par populateAdditionalResources.
  if (!data.resources) {
    data.resources = {};
  }
  if (!data.resources.additional) {
    data.resources.additional = [];
  }
  const existing = new Set(data.resources.additional.map((r) => r.code));

  const migrateOne = (code, legacyData) => {
    if (!legacyData || !legacyData.selected || existing.has(code)) {
      return;
    }
    const ref = findResourceRefByCode(code);
    if (!ref) {
      return;
    }
    const fields = {};
    const fieldSchema = Array.isArray(ref.field_schema) ? ref.field_schema : [];
    fieldSchema.forEach((field) => {
      const value = legacyData[field.key] || "";
      if (value) {
        fields[field.key] = value;
      }
    });
    // Champs spéciaux pour types list
    if (legacyData.values) {
      const listField = fieldSchema.find((f) => f.type === "list");
      if (listField) {
        fields[listField.key] = legacyData.values;
      }
    }
    if (legacyData.zones) {
      const listField = fieldSchema.find((f) => f.type === "list");
      if (listField) {
        fields[listField.key] = legacyData.zones;
      }
    }
    // Champ email spécial
    if (legacyData.adresse) {
      const emailField = fieldSchema.find((f) => f.type === "email_with_domain");
      if (emailField) {
        fields[emailField.key] = legacyData.adresse;
      }
    }
    data.resources.additional.push({
      id: ref.id,
      code: ref.code,
      label: ref.label,
      category: ref.category,
      issuerService: ref.issuer_service,
      selected: true,
      fieldSchema: fieldSchema,
      fields: fields,
      assignedAt: legacyData.assignedAt || "",
      conditionAttribution: legacyData.conditionAttribution || "",
      conditionNotes: legacyData.conditionNotes || ""
    });
  };

  const mat = data.materiel || {};
  const imm = data.immateriel || {};
  Object.entries(mat).forEach(([code, item]) => migrateOne(code, item));
  Object.entries(imm).forEach(([code, item]) => migrateOne(code, item));
}

function buildEquipmentSelectionMap() {
  // Les ressources matérielles sont désormais collectées via getAdditionalResourcesData().
  return {};
}

function buildIntangibleSelectionMap() {
  // Les ressources immatérielles sont désormais collectées via getAdditionalResourcesData().
  return {};
}

function collectRequestedResourcesFromFormData(formData) {
  const resources = [];
  const pushIfSelected = (key, item, label) => {
    if (item?.selected) {
      resources.push({
        key,
        label,
        isCompleted: Boolean(item.assignedAt)
      });
    }
  };

  Object.entries(formData.materiel || {}).forEach(([key, item]) => {
    const ref = findResourceRefByCode(key);
    pushIfSelected(key, item, ref?.label || key);
  });
  Object.entries(formData.immateriel || {}).forEach(([key, item]) => {
    const ref = findResourceRefByCode(key);
    pushIfSelected(key, item, ref?.label || key);
  });
  (formData.resources?.additional || []).forEach((resource) => {
    if (resource?.selected) {
      resources.push({
        key: resource.id || resource.code || "resource",
        label: resource.label || "Ressource complémentaire",
        isCompleted: isDynamicResourceComplete(resource)
      });
    }
  });

  return resources;
}

function summarizeRequestedResourceCompletion(formData) {
  const requested = collectRequestedResourcesFromFormData(formData);
  return {
    total: requested.length,
    completed: requested.filter((resource) => resource.isCompleted).length,
    missing: requested.filter((resource) => !resource.isCompleted)
  };
}

function setUncRefAd(label) {
  const wrap = document.getElementById("uncRefAd");
  const lbl = document.getElementById("uncRefAdLabel");
  if (!wrap || !lbl) return;
  if (label) { lbl.textContent = label; wrap.classList.remove("d-none"); }
  else { wrap.classList.add("d-none"); lbl.textContent = ""; }
}

function getUncRefAd() {
  return document.getElementById("uncRefAdLabel")?.textContent?.trim() || "";
}

function bindUncCopyFrom() {
  const searchInput = document.getElementById("uncCopySearch");
  const resultsBox = document.getElementById("uncCopyResults");
  if (!searchInput || !resultsBox) return;

  let debounceTimer;

  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) { resultsBox.classList.add("d-none"); resultsBox.innerHTML = ""; return; }
    debounceTimer = setTimeout(async () => {
      const res = await fetch(`/api/forms?search=${encodeURIComponent(q)}`);
      if (!res.ok) return;
      const forms = await res.json();
      const withUnc = forms.filter(f => f.id !== (document.getElementById("form")?.dataset?.draftId || ""));
      resultsBox.innerHTML = "";
      if (!withUnc.length) {
        resultsBox.innerHTML = `<span class="list-group-item list-group-item-secondary small">Aucun dossier trouvé</span>`;
      } else {
        withUnc.slice(0, 8).forEach(f => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "list-group-item list-group-item-action small";
          btn.textContent = `${f.prenom} ${f.nom}${f.service ? " — " + f.service : ""}`;
          btn.addEventListener("click", async () => {
            resultsBox.classList.add("d-none");
            searchInput.value = "";
            const detail = await fetch(`/api/forms/${f.id}`);
            if (!detail.ok) return;
            const data = await detail.json();
            const entries = data.data?.unc_acces || [];
            setUncRefAd(`${f.prenom} ${f.nom}${f.service ? " — " + f.service : ""}`);
            if (!entries.length) return;
            entries.forEach(e => document.getElementById("uncAccessList").appendChild(createUncRow(e)));
          });
          resultsBox.appendChild(btn);
        });
      }
      resultsBox.classList.remove("d-none");
    }, 280);
  });

  document.addEventListener("click", e => {
    if (!searchInput.contains(e.target) && !resultsBox.contains(e.target)) {
      resultsBox.classList.add("d-none");
    }
  });
}

function createUncRow(entry = {}) {
  const row = document.createElement("div");
  row.className = "unc-row";
  row.innerHTML = `
    <input class="form-control unc-chemin" list="uncPathsList" placeholder="\\\\serveur\\partage" value="${(entry.chemin || "").replace(/"/g, "&quot;")}">
    <select class="form-select unc-acces">
      <option value="lecture"${entry.acces === "lecture" ? " selected" : ""}>Lecture</option>
      <option value="lecture_ecriture"${entry.acces === "lecture_ecriture" ? " selected" : ""}>Lecture / Écriture</option>
      <option value="refuse"${entry.acces === "refuse" ? " selected" : ""}>Accès refusé</option>
    </select>
    <select class="form-select unc-statut">
      <option value="demande"${!entry.statut || entry.statut === "demande" ? " selected" : ""}>Demandé</option>
      <option value="en_cours"${entry.statut === "en_cours" ? " selected" : ""}>En cours</option>
      <option value="provisionne"${entry.statut === "provisionne" ? " selected" : ""}>Provisionné</option>
    </select>
    <input class="form-control unc-commentaire" placeholder="Commentaire (optionnel)" value="${(entry.commentaire || "").replace(/"/g, "&quot;")}">
    <button type="button" class="btn btn-outline-danger btn-sm unc-remove" aria-label="Supprimer">−</button>`;
  return row;
}

function getUncAccesData() {
  return Array.from(document.querySelectorAll("#uncAccessList .unc-row")).map(row => ({
    chemin: row.querySelector(".unc-chemin").value.trim(),
    acces: row.querySelector(".unc-acces").value,
    statut: row.querySelector(".unc-statut").value,
    commentaire: row.querySelector(".unc-commentaire").value.trim(),
  })).filter(e => e.chemin);
}

function populateUncAcces(entries = []) {
  const list = document.getElementById("uncAccessList");
  if (!list) return;
  list.innerHTML = "";
  entries.forEach(e => list.appendChild(createUncRow(e)));
}

function getFormData(signaturePad) {
  // Produit le payload métier complet qui sera envoyé à l'API.
  const now = new Date().toISOString();
  const currentDraftId = form.dataset.draftId || "";
  const signatureDataUrl = signaturePad.toDataUrl();
  const selectedStatus = form.dataset.workflowStatus || "draft";
  const qualiteInput = document.querySelector('input[name="qualite"]:checked');
  const status = signatureDataUrl && selectedStatus === "draft" ? "active" : selectedStatus;
  const lockedAt = form.dataset.lockedAt || (signatureDataUrl ? now : "");
  const assignedAt = document.getElementById("assigned_at").value || getCurrentDateTimeLocal();
  const startAt = document.getElementById("start_at").value || "";

  return {
    meta: {
      id: currentDraftId,
      savedAt: now,
      lockedAt,
      assignedAt,
      startAt
    },
      workflow: {
        status
      },
      dossier: {
        type: normalizeDossierType(document.getElementById("dossier_type").value || "arrivee"),
        serviceDestination: getServiceDestinationValue()
      },
    beneficiaire: {
      nom: document.getElementById("nom").value.trim(),
      prenom: document.getElementById("prenom").value.trim(),
      service: getServiceValue(),
      fonction: document.getElementById("fonction").value.trim(),
      qualite: qualiteInput ? qualiteInput.value : "",
      mandat: document.getElementById("mandat").value
    },
    materiel: buildEquipmentSelectionMap(),
    immateriel: buildIntangibleSelectionMap(),
    resources: {
      additional: getAdditionalResourcesData()
    },
    unc_acces: getUncAccesData(),
    unc_ref_ad: getUncRefAd(),
    restitution: currentRestitutionData,
    validation: {
      rgpdAccepted: document.getElementById("rgpdCheck").checked,
      signatureDataUrl
    }
  };
}

function populateForm(data, signaturePad) {
  // Hydrate tout le formulaire a partir d'une fiche existante.
  if (!data) {
    return;
  }

  form.dataset.draftId = data.meta.id || "";
  form.dataset.lockedAt = data.meta.lockedAt || "";
  document.getElementById("nom").value = data.beneficiaire.nom || "";
    document.getElementById("prenom").value = data.beneficiaire.prenom || "";
    document.getElementById("dossier_type").value = normalizeDossierType(data.dossier.type || "arrivee");
    setServiceValue(data.beneficiaire.service || "");
    setServiceDestinationValue(data.dossier.serviceDestination || "");
  document.getElementById("fonction").value = data.beneficiaire.fonction || "";
  document.getElementById("mandat").value = data.beneficiaire.mandat || "";
  document.getElementById("start_at").value = normalizeDateInputValue(data.meta.startAt || "");
  document.getElementById("assigned_at").value = normalizeDateTimeLocal(data.meta.assignedAt || data.meta.savedAt || "");
  form.dataset.workflowStatus = data.workflow.status || "draft";
  currentRestitutionData = JSON.parse(JSON.stringify(data.restitution || {
    returnedAt: "",
    reason: "",
    notes: "",
    items: {}
  }));
  if (data.beneficiaire.qualite) {
    const radio = document.querySelector(`input[name="qualite"][value="${data.beneficiaire.qualite}"]`);
    if (radio) {
      radio.checked = true;
    }
  }

  populateUncAcces(data.unc_acces || []);
  setUncRefAd(data.unc_ref_ad || "");

  // Migration : convertir les anciennes données materiel/immateriel en resources.additional
  // pour les dossiers sauvegardés avant le rendu dynamique.
  migrateLegacyResourcesToAdditional(data);

  document.getElementById("rgpdCheck").checked = Boolean(data.validation.rgpdAccepted);
  populateAdditionalResources(data);

  initQualite();
  initConditionalBlocks();
  syncDossierTypeUi();
  updateStatusInfo(form.dataset.workflowStatus || "draft");
  renderRestitutionSummary();
  renderReopenInfo(data.meta || {});
  signaturePad.restore(data.validation.signatureDataUrl || "");
  updateDraftUi(data.meta.savedAt, true, data.workflow.status || "draft");
  applyLockState(Boolean(data.meta.lockedAt));
}

function formatStatusLabel(status) {
  const labels = {
    draft: "À compléter",
    partial_assignment: "Attribution partielle",
    awaiting_signature: "En attente de signature",
    active: "Attribution active",
    returned: "Restitution terminée",
    partial_return: "Restitution partielle",
    cancelled: "Dossier annulé"
  };
  return labels[status] || "À compléter";
}

function updateDraftUi(savedAt, isLoaded = false, status = "draft") {
  if (!draftStatus || !resumeHint) {
    return;
  }

  const label = formatStatusLabel(status);
  if (!savedAt) {
    draftStatus.textContent = label;
    resumeHint.textContent = "Enregistrez le dossier pour pouvoir le reprendre ensuite depuis l'accueil.";
    updateStatusInfo(status);
    return;
  }

  const formatted = new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(savedAt));

  draftStatus.textContent = isLoaded ? `${label} chargé le ${formatted}` : `${label} enregistré le ${formatted}`;
  updateStatusInfo(status);
  if (!currentLockState) {
    resumeHint.textContent = "Vous pouvez rouvrir ce dossier depuis l'accueil pour le mettre à jour ou lancer une restitution dédiée.";
  }
}

function renderReopenInfo(meta = {}) {
  const notice = document.getElementById("reopenNotice");
  const text = document.getElementById("reopenNoticeText");
  if (!notice || !text) {
    return;
  }

  const reopenCount = Number(meta.reopenCount || 0);
  if (!reopenCount) {
    notice.classList.add("d-none");
    text.textContent = "";
    return;
  }

  const lastReopenedAt = meta.lastReopenedAt
    ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(meta.lastReopenedAt))
    : "date non renseignée";
  const lastReopenedBy = meta.lastReopenedBy || "utilisateur non renseigné";
  text.textContent = reopenCount === 1
    ? `Ce dossier a déjà été rouvert 1 fois. Dernière réouverture le ${lastReopenedAt} par ${lastReopenedBy}.`
    : `Ce dossier a déjà été rouvert ${reopenCount} fois. Dernière réouverture le ${lastReopenedAt} par ${lastReopenedBy}.`;
  notice.classList.remove("d-none");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

function updateSignatureLinkUi(link) {
  currentSignatureLink = link || null;
}

async function loadSignatureLinkState() {
  if (!form.dataset.draftId) {
    updateSignatureLinkUi(null);
    return;
  }
  try {
    const result = await requestJson(`/api/forms/${encodeURIComponent(form.dataset.draftId)}/signature-link`);
    updateSignatureLinkUi(result.link);
  } catch (error) {
    updateSignatureLinkUi(null);
  }
}

async function createSignatureLink(options = {}) {
  if (!form.dataset.draftId) {
    const message = "Enregistrez d'abord le dossier avant de générer un lien.";
    if (!options.silentError) {
      showToast(message, "error");
    }
    throw new Error(message);
  }
  try {
    const payload = {};
    if (Number.isFinite(options.validityDays)) {
      payload.validityDays = options.validityDays;
    }
    const result = await requestJson(`/api/forms/${encodeURIComponent(form.dataset.draftId)}/signature-link`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
    updateSignatureLinkUi(result.link);
    const absoluteUrl = result.link?.url ? new URL(result.link.url, window.location.origin).href : "";
    let copied = false;
    if (options.copyAfterGenerate && absoluteUrl) {
      try {
        await navigator.clipboard.writeText(absoluteUrl);
        copied = true;
      } catch (error) {
        copied = false;
      }
    }
    if (!options.silentSuccess) {
      showToast("Le lien de signature a été généré.", "success");
    }
    return { link: result.link, absoluteUrl, copied };
  } catch (error) {
    if (!options.silentError) {
      showToast(error.message || "Impossible de générer le lien de signature.", "error");
    }
    throw error;
  }
}

async function loadDraftFromUrl(signaturePad) {
  // Ouvre une fiche existante si l'URL contient id=...
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");

  if (!id) {
    form.dataset.draftId = "";
    form.dataset.lockedAt = "";
    form.dataset.workflowStatus = "draft";
    currentRestitutionData = { returnedAt: "", reason: "", notes: "", items: {} };
    document.getElementById("assigned_at").value = getCurrentDateTimeLocal();
    updateDraftUi("", false, "draft");
    renderRestitutionSummary();
    renderReopenInfo({});
    updateSignatureLinkUi(null);
    applyLockState(false);
    hidePageLoader();
    return;
  }

  showPageLoader("Récupération des informations de la fiche en cours...");
  try {
    setFormBootstrapStage("lecture du dossier", "Récupération des informations de la fiche...");
    const result = await getDraftById(id);
    if (!result) {
      alert("La fiche demandée est introuvable.");
      hidePageLoader();
      return;
    }

    const session = await getSessionInfo();
    const canEdit = Boolean(session?.permissions?.includes("*") || session?.permissions?.includes("forms.edit"));
    const currentStatus = result.summary?.status || result.data?.workflow?.status || "draft";
    if (canEdit && ["draft", "partial_assignment", "awaiting_signature"].includes(currentStatus)) {
      try {
        setFormBootstrapStage("traçage de la réouverture", "Mise à jour des informations d'ouverture...");
        const reopenResult = await requestJson(`/api/forms/${encodeURIComponent(id)}/reopen`, {
          method: "POST",
          timeoutMs: 10000
        });
        if (reopenResult?.meta) {
          result.data.meta = { ...(result.data.meta || {}), ...reopenResult.meta };
        }
      } catch (error) {
        console.error("Impossible de tracer la réouverture du dossier", error);
      }
    }

    setFormBootstrapStage("préparation des données métier", "Préparation de la fiche...");
    populateForm(result.data, signaturePad);
    setFormBootstrapStage("chargement du lien de signature", "Chargement du lien de signature...");
    await loadSignatureLinkState();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => hidePageLoader());
    });
  } catch (error) {
    console.error("Erreur lors du chargement de la fiche", error);
    hidePageLoader();
    alert(error?.message || "Impossible de charger correctement la fiche.");
  }
}

async function exportPDF(signaturePad) {
  alert("L'export PDF est disponible depuis la page d'accueil une fois la fiche enregistrée.");
}

function validateFormData(formData, options = {}) {
  if (!formData.beneficiaire.nom || !formData.beneficiaire.prenom) {
    return "Le nom et le prénom sont obligatoires.";
  }

  if (!formData.beneficiaire.qualite) {
    return "Veuillez sélectionner la qualité du bénéficiaire.";
  }

  const eluBlockDisabledForValidation = Boolean(document.getElementById("eluBlock")?.dataset.eluBlockDisabled);
  if (formData.beneficiaire.qualite === "elu" && !formData.beneficiaire.mandat && !eluBlockDisabledForValidation) {
    return "Veuillez renseigner le mandat de l'élu.";
  }

  if (options.requireRgpd && !formData.validation.rgpdAccepted) {
    return "La validation RGPD est obligatoire avant l'export PDF.";
  }

  const resourceIssues = collectResourceValidationIssues();
  formData.meta.resourceValidationErrors = resourceIssues;
  return null;
}

function updateSaveProgress(options = {}) {
  if (typeof window.showWorkflowDialog === "function") {
    window.showWorkflowDialog(options);
    return;
  }

  showPageLoader(options.text || options.title || "Traitement en cours...");
}

function setSaveButtonLoading(loading) {
  const btn = document.getElementById("saveDraftBtn");
  if (!btn) return;
  if (loading) {
    btn.dataset.originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${btn.dataset.originalText}`;
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.originalText || btn.textContent;
    delete btn.dataset.originalText;
  }
}

function markFormDirty() {
  formDirty = true;
}

function markFormClean() {
  formDirty = false;
}

function closeSaveProgress() {
  if (typeof window.closeWorkflowDialog === "function") {
    window.closeWorkflowDialog();
  }
  hidePageLoader();
}

async function requestSaveDecision(options = {}) {
  if (typeof window.askWorkflowDialog === "function") {
    return window.askWorkflowDialog(options);
  }

  hidePageLoader();
  const title = options.title || "Confirmation";
  const text = options.text || "";
  const lines = [title, text].filter(Boolean);
  const message = lines.join("\n\n");

  if (options.secondaryLabel) {
    const ok = await askConfirm(message, { title: title, confirmLabel: options.confirmLabel, cancelLabel: options.secondaryLabel });
    return ok ? "confirm" : "secondary";
  }

  if (options.showConfirm) {
    showToast(message, "info");
    return "confirm";
  }

  return "secondary";
}

function createWorkflowSteps(labels, activeIndex = 0) {
  return labels.map((label, index) => ({
    label,
    status: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending"
  }));
}

async function showSaveInfoDialog(title, text, items = []) {
  const steps = items.length
    ? items.map((label) => ({ label, status: "error" }))
    : [{ label: text, status: "error" }];
  await requestSaveDecision({
    title,
    text,
    steps,
    hideSpinner: true,
    showConfirm: true,
    confirmLabel: "OK"
  });
}


async function resolveSaveWorkflow(formData) {
  const hasSignature = Boolean(formData.validation.signatureDataUrl);
  const rgpdAccepted = Boolean(formData.validation.rgpdAccepted);
  const currentStatus = formData.workflow.status;
  const resourceIssues = formData.meta.resourceValidationErrors || [];
  const resourceCompletion = summarizeRequestedResourceCompletion(formData);

  if (["returned", "partial_return", "cancelled"].includes(currentStatus)) {
    return formData;
  }

  if (!hasSignature || !rgpdAccepted) {
    formData.workflow.status = "draft";
    formData.meta.lockedAt = "";
    return formData;
  }

  if (resourceIssues.length > 0) {
    formData.workflow.status = "partial_assignment";
    formData.meta.lockedAt = "";
    await showSaveInfoDialog(
      "Attribution partielle",
      "Certaines ressources cochées ne sont pas complètement renseignées. Le dossier reste modifiable.",
      resourceIssues
    );
    return formData;
  }

  if (resourceCompletion.completed < resourceCompletion.total) {
    formData.workflow.status = "partial_assignment";
    formData.meta.lockedAt = "";
    const missingDetails = resourceCompletion.missing.map((resource) => `${resource.label} : ressource encore à compléter`);
    await showSaveInfoDialog(
      "Attribution partielle",
      `L'attribution n'est pas encore complète : ${resourceCompletion.completed}/${resourceCompletion.total} ressource(s) attribuées.`,
      missingDetails
    );
    return formData;
  }

  if (!hasSignature) {
    formData.workflow.status = "awaiting_signature";
    formData.meta.lockedAt = "";
    await showSaveInfoDialog(
      "En attente de signature",
      "Le dossier est complet et n'attend plus que la signature finale."
    );
    return formData;
  }

  const choice = await requestSaveDecision({
    title: "Finalisation du dossier",
    text: "Toutes les informations sont présentes. Souhaitez-vous verrouiller ce dossier comme attribution complète ?",
    steps: [
      { label: "Bénéficiaire, ressources et validation sont complets", status: "done" },
      { label: "Choisissez entre finalisation complète ou poursuite en mode partiel", status: "active" }
    ],
    hideSpinner: true,
    showConfirm: true,
    confirmLabel: "Finaliser le dossier",
    secondaryLabel: "Laisser partiel"
  });

  if (choice === "confirm") {
    formData.workflow.status = "active";
    formData.meta.lockedAt = formData.meta.lockedAt || new Date().toISOString();
    return formData;
  }

  formData.workflow.status = "partial_assignment";
  formData.meta.lockedAt = "";
  return formData;
}

async function saveDraft(signaturePad) {
  const workflowLabels = [
    "Préparation des informations du dossier",
    "Analyse de complétude et du workflow",
    "Enregistrement sécurisé du dossier",
    "Finalisation de l'interface"
  ];

  setSaveButtonLoading(true);
  try {
    updateSaveProgress({
      title: "Enregistrement du dossier",
      text: "Le dossier est en cours de préparation avant sauvegarde.",
      steps: createWorkflowSteps(workflowLabels, 0)
    });

    const formData = getFormData(signaturePad);
    const validationError = validateFormData(formData);
    if (validationError) {
      closeSaveProgress();
      setSaveButtonLoading(false);
      await showSaveInfoDialog("Enregistrement impossible", validationError);
      return;
    }

    updateSaveProgress({
      title: "Enregistrement du dossier",
      text: "Le dossier est en cours d'analyse pour déterminer son état métier.",
      steps: createWorkflowSteps(workflowLabels, 1)
    });
    await resolveSaveWorkflow(formData);

    updateSaveProgress({
      title: "Enregistrement du dossier",
      text: "Les informations sont en cours d'enregistrement.",
      steps: createWorkflowSteps(workflowLabels, 2)
    });

    const result = await saveFormData(formData);
    form.dataset.draftId = result.summary.id;
    form.dataset.lockedAt = result.data.meta.lockedAt || formData.meta.lockedAt || "";
    updateDraftUi(result.summary.updatedAt, false, result.summary.status);
    await loadSignatureLinkState();
    if (form.dataset.lockedAt) {
      applyLockState(true);
    }

    updateSaveProgress({
      title: "Enregistrement du dossier",
      text: "La fiche a été enregistrée. L'application finalise maintenant le retour vers le tableau de bord.",
      steps: workflowLabels.map((label) => ({ label, status: "done" }))
    });

    if (["active", "awaiting_signature"].includes(result.summary.status || "") && typeof window.playCompletionCelebration === "function") {
      await window.playCompletionCelebration("confetti");
    }

    if (result.offline) {
      resumeHint.textContent = "Le dossier a été conservé localement et pourra être repris depuis cet appareil.";
      await requestSaveDecision({
        title: "Dossier enregistré localement",
        text: `La fiche « ${result.summary.title} » a été conservée sur cet appareil.`,
        steps: workflowLabels.map((label) => ({ label, status: "done" })),
        hideSpinner: true,
        showConfirm: true,
        confirmLabel: "OK"
      });
      markFormClean();
      window.location.href = "index.html";
      return;
    }

    closeSaveProgress();
    setSaveButtonLoading(false);
    showToast(`Dossier « ${result.summary.title} » enregistré.`, "success");
    markFormClean();
    setTimeout(() => { window.location.href = "index.html"; }, 1400);
  } catch (error) {
    console.error("Erreur lors de l'enregistrement du dossier", error);
    closeSaveProgress();
    setSaveButtonLoading(false);
    await showSaveInfoDialog(
      "Erreur d'enregistrement",
      error.message === "Cette fiche est signée et verrouillée. Elle ne peut plus être modifiée."
        ? error.message
        : "Impossible d'enregistrer la fiche."
    );
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function normalizeServiceName(value) {
  const normalized = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();

  if (!normalized) {
    return "";
  }
  if (normalized === "dsi") {
    return "dsi";
  }
  if (normalized === "batiment") {
    return "batiment";
  }
  if (normalized === "autres services" || normalized === "autres_service" || normalized === "autres services ") {
    return "autres_services";
  }
  return normalized;
}

function formatIssuerServiceLabel(value) {
  const label = String(value || "").trim();
  return label || "Service";
}

window.addEventListener("error", (event) => {
  if (!form || pageLoader?.classList.contains("is-hidden")) {
    return;
  }
  failFormBootstrap(event.error || new Error(event.message || "Erreur JavaScript"), "Erreur JavaScript pendant le chargement de la fiche");
});

window.addEventListener("unhandledrejection", (event) => {
  if (!form || pageLoader?.classList.contains("is-hidden")) {
    return;
  }
  failFormBootstrap(event.reason instanceof Error ? event.reason : new Error(String(event.reason || "Promesse rejetée")), "Promesse rejetée pendant le chargement de la fiche");
});

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll("[data-back-to-index]").forEach((btn) => {
    btn.addEventListener("click", () => { window.location.href = "index.html"; });
  });

  if (!form) {
    return;
  }

  setFormBootstrapStage("préparation de l'interface", "Chargement du formulaire...");
  startFormBootstrapWatchdog();

  try {
    setFormBootstrapStage("chargement des services", "Chargement des services...");
    await loadServiceOptions();

    setFormBootstrapStage("chargement des ressources", "Chargement des ressources...");
    await loadDynamicResourceReferences();

    setFormBootstrapStage("chargement de la session", "Chargement de la session...");
    await getSessionInfo();

    setFormBootstrapStage("initialisation de la signature", "Préparation de la signature...");
    const signaturePad = initSignaturePad();

    // Chargement des suggestions de champs (marque, modèle, etc.) — non bloquant
    void loadFieldSuggestions();

    fetch("/api/settings/public").then(r => r.ok ? r.json() : {}).then(s => {
      window._emailDomainsCache = s.emailDomains || [];
    });
    fetch("/api/forms/unc-paths").then(r => r.ok ? r.json() : []).then(paths => {
      const dl = document.getElementById("uncPathsList");
      if (dl) paths.forEach(p => { const o = document.createElement("option"); o.value = p; dl.appendChild(o); });
    });
    bindUncCopyFrom();
    document.getElementById("uncRefAdClear")?.addEventListener("click", () => setUncRefAd(""));
    document.getElementById("addUncBtn")?.addEventListener("click", () => {
      document.getElementById("uncAccessList").appendChild(createUncRow());
    });
    document.getElementById("uncAccessList")?.addEventListener("click", e => {
      if (e.target.closest(".unc-remove")) {
        e.target.closest(".unc-row").remove();
      }
    });
    document.getElementById("uncAccessList")?.addEventListener("blur", e => {
      const input = e.target.closest(".unc-chemin");
      if (!input) return;
      const val = input.value.trim();
      if (val && !val.startsWith("\\\\")) {
        input.classList.add("is-invalid");
        if (!input.nextElementSibling?.classList.contains("unc-invalid-feedback")) {
          const msg = document.createElement("div");
          msg.className = "invalid-feedback unc-invalid-feedback";
          msg.textContent = "Le chemin doit commencer par \\\\serveur\\partage";
          input.after(msg);
        }
      } else {
        input.classList.remove("is-invalid");
        input.nextElementSibling?.classList.contains("unc-invalid-feedback") && input.nextElementSibling.remove();
      }
    }, true);

    document.getElementById("saveDraftBtn")?.addEventListener("click", () => {
      void saveDraft(signaturePad);
    });

    // Ctrl+S / Cmd+S — sauvegarde rapide depuis le formulaire
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        void saveDraft(signaturePad);
      }
    });
    setFormBootstrapStage("initialisation des blocs métier", "Préparation du formulaire...");
    ensureAssignmentConditionFields();
    initRepeatableResourceLists();
    initConditionalBlocks();
    initQualite();
    bindProgressIndicatorRefresh();
    syncDossierTypeUi();

    setFormBootstrapStage("ouverture de la fiche", "Chargement de la fiche...");
    await loadDraftFromUrl(signaturePad);

    [
      "dossier_type",
      "service",
      "service_destination"
    ].forEach((id) => {
      const field = document.getElementById(id);
      if (!field) {
        return;
      }
      field.addEventListener("change", () => {
        if (id === "dossier_type") {
          syncDossierTypeUi();
          return;
        }
        if (id === "service") {
          syncServiceCustomField();
          return;
        }
        if (id === "service_destination") {
          syncServiceCustomField("service_destination", "service_destination_custom");
        }
      });
    });

    refreshProgressIndicators();

    // Dirty tracking — marquer le formulaire modifié dès qu'un champ change
    form.addEventListener("input", markFormDirty, { passive: true });
    form.addEventListener("change", markFormDirty, { passive: true });

    // Confirmation départ si modifications non sauvegardées
    window.addEventListener("beforeunload", (e) => {
      if (formDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
    document.querySelectorAll("[data-back-to-index]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopImmediatePropagation();
        if (formDirty) {
          const ok = await askConfirm("Des modifications non sauvegardées seront perdues. Quitter quand même ?", {
            confirmLabel: "Quitter sans sauvegarder",
            confirmClass: "btn-danger",
            cancelLabel: "Rester"
          });
          if (!ok) return;
        }
        markFormClean();
        window.location.href = "index.html";
      });
    });

    clearFormBootstrapWatchdog();
    if (!new URLSearchParams(window.location.search).get("id")) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => hidePageLoader());
      });
    }
  } catch (error) {
    failFormBootstrap(error, "Impossible de charger correctement le formulaire.");
  }
});

function normalizeDossierType(value) {
  const mapping = {
    nouvel_agent: "arrivee",
    nouvel_elu: "arrivee",
    elu_en_place: "mise_a_jour",
    changement_service: "changement_service",
    sortie: "sortie",
    arrivee: "arrivee",
    mise_a_jour: "mise_a_jour"
  };
  return mapping[value] || "arrivee";
}





// Module principal de la fiche d'attribution :
// collecte métier, validation locale et sérialisation du payload.
