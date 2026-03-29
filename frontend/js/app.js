const form = document.getElementById("dotationForm");
const draftStatus = document.getElementById("draftStatus");
const resumeHint = document.getElementById("resumeHint");
const pageLoader = document.getElementById("pageLoader");
const DOSSIER_TYPE_LABELS = {
  arrivee: "Nouvelle arrivée",
  changement_service: "Changement de service",
  mise_a_jour: "Mise à jour de ressources",
  sortie: "Sortie / restitution"
};
const DEFAULT_SERVICE_OPTIONS = [
  "Affaires juridiques / Commande publique",
  "Bâtiment",
  "Cabinet du Maire",
  "CCAS",
  "Communication",
  "Culture et Patrimoine",
  "CTM",
  "DGS",
  "DRH",
  "DSI",
  "DST",
  "Finances",
  "PM",
  "Population",
  "SEJE",
  "Secrétariat service technique",
  "Sports",
  "Subvention",
  "Urbanisme",
  "VRD"
];
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
const EQUIPMENT_CONFIG = [
  {
    key: "ordinateur",
    label: "Ordinateur",
    category: "materiel",
    checkboxId: "has_pc",
    detail: () => [getFieldValue("pc_nom"), getFieldValue("pc_marque"), getFieldValue("pc_modele"), getFieldValue("pc_sn")].filter(Boolean).join(" - ")
  },
  {
    key: "ecran",
    label: "Écran",
    category: "materiel",
    checkboxId: "has_screen",
    detail: () => [getFieldValue("screen_marque"), getFieldValue("screen_modele"), getFieldValue("screen_sn")].filter(Boolean).join(" - ")
  },
  {
    key: "telephone",
    label: "Téléphone",
    category: "materiel",
    checkboxId: "has_phone",
    detail: () => [getFieldValue("tel_nom"), getFieldValue("tel_marque"), getFieldValue("tel_modele"), getFieldValue("tel_imei")].filter(Boolean).join(" - ")
  },
  {
    key: "tablette",
    label: "Tablette",
    category: "materiel",
    checkboxId: "has_tablette",
    detail: () => [getFieldValue("tablette_nom"), getFieldValue("tablette_marque"), getFieldValue("tablette_modele"), getFieldValue("tablette_sn")].filter(Boolean).join(" - ")
  },
  {
    key: "vehicule",
    label: "Véhicule",
    category: "materiel",
    checkboxId: "has_vehicule",
    detail: () => [getFieldValue("vehicule_marque"), getFieldValue("vehicule_modele"), getFieldValue("vehicule_plaque")].filter(Boolean).join(" - ")
  },
  {
    key: "badge",
    label: "Badge d'accès",
    category: "materiel",
    checkboxId: "has_badge",
    detail: () => getFieldValue("badge_numero")
  },
  {
    key: "cles",
    label: "Clé(s)",
    category: "materiel",
    checkboxId: "has_cles",
    detail: () => getRepeatableValues("clesRows").join(" - ")
  },
  {
    key: "veste",
    label: "Veste",
    category: "materiel",
    checkboxId: "veste",
    detail: () => ""
  },
  {
    key: "chaussuresSecurite",
    label: "Chaussures de sécurité",
    category: "materiel",
    checkboxId: "chaussure",
    detail: () => ""
  },
  {
    key: "autre",
    label: "Autre matériel",
    category: "materiel",
    checkboxId: "has_autre",
    detail: () => getFieldValue("autre_materiel")
  },
  {
    key: "vpn",
    label: "VPN",
    category: "immateriel",
    checkboxId: "vpn",
    detail: () => ""
  },
  {
    key: "email",
    label: "Email",
    category: "immateriel",
    checkboxId: "has_mail",
    detail: () => getFieldValue("email")
  },
  {
    key: "zoneAlarme",
    label: "Zone alarme",
    category: "immateriel",
    checkboxId: "has_zone_alarme",
    detail: () => getRepeatableValues("zoneAlarmeRows").join(" - ")
  }
];

const CORE_RESOURCE_RULES = {
  ordinateur: [
    { fieldId: "pc_nom", label: "Nom du poste", required: false, pattern: ".*", hint: "" },
    { fieldId: "pc_marque", label: "Marque ordinateur", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$", hint: "2 à 50 caractères" },
    { fieldId: "pc_modele", label: "Modèle ordinateur", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$", hint: "2 à 60 caractères" },
    { fieldId: "pc_sn", label: "Numéro de série ordinateur", required: true, pattern: "^[A-Za-z0-9-]{5,40}$", hint: "5 à 40 caractères alphanumériques" }
  ],
  ecran: [
    { fieldId: "screen_marque", label: "Marque écran", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$", hint: "2 à 50 caractères" },
    { fieldId: "screen_modele", label: "Modèle écran", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$", hint: "2 à 60 caractères" },
    { fieldId: "screen_sn", label: "Numéro de série écran", required: true, pattern: "^[A-Za-z0-9-]{5,40}$", hint: "5 à 40 caractères alphanumériques" }
  ],
  telephone: [
    { fieldId: "tel_nom", label: "Nom du téléphone", required: false, pattern: ".*", hint: "" },
    { fieldId: "tel_marque", label: "Marque téléphone", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$", hint: "2 à 50 caractères" },
    { fieldId: "tel_modele", label: "Modèle téléphone", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$", hint: "2 à 60 caractères" },
    { fieldId: "tel_imei", label: "IMEI", required: true, pattern: "^\\d{15}$", hint: "15 chiffres" }
  ],
  tablette: [
    { fieldId: "tablette_nom", label: "Nom de la tablette", required: false, pattern: ".*", hint: "" },
    { fieldId: "tablette_marque", label: "Marque tablette", required: true, pattern: ".*", hint: "" },
    { fieldId: "tablette_modele", label: "Modèle tablette", required: true, pattern: ".*", hint: "" },
    { fieldId: "tablette_sn", label: "Numéro de série tablette", required: true, pattern: ".*", hint: "" }
  ],
  vehicule: [
    { fieldId: "vehicule_marque", label: "Marque véhicule", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._-]{1,49}$", hint: "2 à 50 caractères" },
    { fieldId: "vehicule_modele", label: "Modèle véhicule", required: true, pattern: "^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$", hint: "2 à 60 caractères" },
    { fieldId: "vehicule_plaque", label: "Immatriculation", required: true, pattern: "^[A-Z]{2}-\\d{3}-[A-Z]{2}$", hint: "Format AA-123-AA" }
  ],
  badge: [
    { fieldId: "badge_numero", label: "Numéro de badge", required: true, pattern: "^[A-Za-z0-9-]{3,30}$", hint: "3 à 30 caractères" }
  ],
  autre: [
    { fieldId: "autre_materiel", label: "Description autre matériel", required: true, pattern: "^.{3,120}$", hint: "3 à 120 caractères" }
  ],
  email: [
    { fieldId: "email", label: "Adresse email", required: true, pattern: "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$", hint: "Format de type nom@domaine.fr" }
  ]
};

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

const ASSIGNMENT_CONDITION_CONFIG = [
  { checkboxId: "has_pc", targetId: "pcFields", prefix: "pc" },
  { checkboxId: "has_screen", targetId: "screenFields", prefix: "screen" },
  { checkboxId: "has_phone", targetId: "phoneFields", prefix: "tel" },
  { checkboxId: "has_tablette", targetId: "tabletteFields", prefix: "tablette" },
  { checkboxId: "vpn", targetId: "vpnFields", prefix: "vpn", createTarget: true, stacked: true, dateOnly: true },
  { checkboxId: "has_mail", targetId: "mailFields", prefix: "email", stacked: true, dateOnly: true },
  { checkboxId: "has_zone_alarme", targetId: "zoneAlarmeFields", prefix: "zoneAlarme", stacked: true, afterSelector: "#addZoneAlarmeBtn", dateOnly: true },
  { checkboxId: "has_badge", targetId: "badgeFields", prefix: "badge", stacked: true, dateOnly: true },
  { checkboxId: "has_cles", targetId: "clesFields", prefix: "cles", stacked: true, afterSelector: "#addCleBtn" },
  { checkboxId: "veste", targetId: "vesteFields", prefix: "veste", createTarget: true, stacked: true },
  { checkboxId: "chaussure", targetId: "chaussureFields", prefix: "chaussure", createTarget: true, stacked: true },
  { checkboxId: "has_vehicule", targetId: "vehiculeFields", prefix: "vehicule" },
  { checkboxId: "has_autre", targetId: "autreFields", prefix: "autre", stacked: true }
];

let currentLockState = false;

// Helpers de lecture du formulaire.
function getFieldValue(id) {
  const field = document.getElementById(id);
  if (!field || typeof field.value !== "string") {
    return "";
  }
  return field.value.trim() || "";
}

function setFieldValueIfExists(id, value) {
  const field = document.getElementById(id);
  if (!field) {
    return;
  }
  field.value = value || "";
}

function getRepeatableValues(containerId) {
  const container = document.getElementById(containerId);
  if (!container) {
    return [];
  }
  return Array.from(container.querySelectorAll("input"))
    .map((input) => input.value.trim())
    .filter(Boolean);
}

function getAssignmentConditionData(prefix) {
  return {
    assignedAt: getFieldValue(`${prefix}_assigned_at`),
    conditionAttribution: getFieldValue(`${prefix}_condition`),
    conditionNotes: getFieldValue(`${prefix}_condition_notes`)
  };
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

function buildAssignmentConditionFieldsHtml(prefix, stacked = false, dateOnly = false) {
  const marginClass = stacked ? " mt-2" : "";
  if (dateOnly) {
    return `
      <input class="form-control${marginClass}" type="date" id="${prefix}_assigned_at">
    `;
  }
  return `
      <input class="form-control${marginClass}" type="date" id="${prefix}_assigned_at">
      <select class="form-select${marginClass}" id="${prefix}_condition">
        <option value="">État à la remise</option>
      <option value="neuf">Neuf</option>
      <option value="bon_etat">Bon état</option>
      <option value="etat_usage">État d'usage</option>
      <option value="degrade">Dégradé</option>
    </select>
    <input class="form-control${marginClass}" placeholder="Observation de remise" id="${prefix}_condition_notes">
  `;
}

function ensureAssignmentConditionFields() {
  ASSIGNMENT_CONDITION_CONFIG.forEach((config) => {
    const checkbox = document.getElementById(config.checkboxId);
    if (!checkbox) {
      return;
    }

    let target = document.getElementById(config.targetId);
    if (!target && config.createTarget) {
      const equipmentItem = checkbox.closest(".equipment-item");
      if (!equipmentItem) {
        return;
      }
      target = document.createElement("div");
      target.id = config.targetId;
      target.className = "single-field d-none";
      equipmentItem.appendChild(target);
      checkbox.dataset.target = config.targetId;
    }

    if (!target || target.querySelector(`#${config.prefix}_assigned_at`)) {
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = config.stacked ? "assignment-condition-block" : "";
    wrapper.innerHTML = buildAssignmentConditionFieldsHtml(config.prefix, Boolean(config.stacked), Boolean(config.dateOnly));

    if (config.afterSelector) {
      const anchor = target.querySelector(config.afterSelector);
      if (anchor) {
        anchor.insertAdjacentElement("afterend", wrapper);
        return;
      }
    }
    target.appendChild(wrapper);
  });
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

function ensureRepeatableRow(containerId, placeholder) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  if (!container.querySelector("input")) {
    createRepeatableRow(containerId, placeholder);
  }
}

function populateRepeatableRows(containerId, placeholder, values = []) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const normalized = Array.isArray(values) ? values.filter((value) => String(value || "").trim()) : [];
  if (!normalized.length) {
    return;
  }
  normalized.forEach((value) => createRepeatableRow(containerId, placeholder, value));
}

function matchesPattern(value, pattern) {
  if (!pattern) {
    return true;
  }
  try {
    return new RegExp(pattern).test(String(value || ""));
  } catch (error) {
    // Une expression invalide ne doit pas bloquer la saisie;
    // on considère alors la règle comme non bloquante.
    return true;
  }
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
  const type = ["date", "number"].includes(fieldType) ? fieldType : "text";
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
  return `<div class="subgrid mt-3">${inputBlocks.join("")}</div>`;
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
  const field = document.getElementById(`dynamic_resource_${resourceId}_${fieldKey}`);
  if (!field) {
    return "";
  }
  if (field.type === "checkbox") {
    return field.checked ? "Oui" : "";
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
  const genericMaterialWrap = document.getElementById("dynamicResourcesGenericMaterialWrap");
  const genericImmaterialWrap = document.getElementById("dynamicResourcesGenericImmaterialWrap");
  const dsiMaterialContainer = document.getElementById("dynamicResourcesDsiMaterialGrid");
  const dsiImmaterialContainer = document.getElementById("dynamicResourcesDsiImmaterialGrid");
  const batimentMaterialContainer = document.getElementById("dynamicResourcesBatimentMaterialGrid");
  const batimentImmaterialContainer = document.getElementById("dynamicResourcesBatimentImmaterialGrid");
  const batimentImmaterialWrap = document.getElementById("dynamicResourcesBatimentImmaterialWrap");
  const otherMaterialContainer = document.getElementById("dynamicResourcesOtherMaterialGrid");
  const otherImmaterialContainer = document.getElementById("dynamicResourcesOtherImmaterialGrid");
  const otherImmaterialWrap = document.getElementById("dynamicResourcesOtherImmaterialWrap");
  const dynamicSectionsContainer = document.getElementById("dynamicServiceSections");
  const emptyState = document.getElementById("dynamicResourcesEmpty");
  if (
    !genericMaterialContainer || !genericImmaterialContainer
    || !dsiMaterialContainer || !dsiImmaterialContainer
    || !batimentMaterialContainer || !batimentImmaterialContainer
    || !otherMaterialContainer || !otherImmaterialContainer
    || !dynamicSectionsContainer || !emptyState
  ) {
    return;
  }

  try {
    const references = await requestJson("/api/reference/resources");
    dynamicResourceReferences = references.filter((resource) => !EQUIPMENT_CONFIG.some((item) => item.key === resource.code));
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
    otherMaterialContainer.innerHTML = "";
    otherImmaterialContainer.innerHTML = "";
    dynamicSectionsContainer.innerHTML = "";
    emptyState.classList.remove("d-none");
    genericMaterialWrap?.classList.add("d-none");
    genericImmaterialWrap?.classList.add("d-none");
    otherImmaterialWrap?.classList.add("d-none");
    return;
  }

  const buildResourceCard = (resource) => {
    const fieldSchema = Array.isArray(resource.field_schema) ? resource.field_schema : [];
    const fieldsMarkup = fieldSchema.length
      ? `<div class="subgrid mt-3">${fieldSchema.map((field) => buildDynamicFieldInput(resource, field)).join("")}</div>`
      : `
        <div class="single-field mt-3">
          <input class="form-control dynamic-resource-field" id="dynamic_resource_details_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}" data-field-key="details" placeholder="Détails ou précision de l'attribution">
        </div>
      `;
    const trackingMarkup = buildDynamicResourceTrackingFields(resource);
    const descriptionMarkup = resource.description
      ? `<p class="equipment-item__hint mt-2 mb-0">${escapeHtml(resource.description)}</p>`
      : "";

    return `
      <div class="equipment-item">
        <label class="equipment-toggle">
          <input type="checkbox" id="dynamic_resource_${escapeAttribute(resource.id)}" data-resource-id="${escapeAttribute(resource.id)}" data-resource-trigger="${escapeAttribute(resource.trigger_key || "")}">
          <span>${escapeHtml(resource.label)}</span>
        </label>
        ${descriptionMarkup}
        ${fieldsMarkup}
        ${trackingMarkup}
        <p class="equipment-item__hint mt-2 mb-0">${escapeHtml(resource.issuer_service || "Service non renseigné")} · ${escapeHtml(resource.category || "Ressource")}</p>
      </div>
    `;
  };

  const grouped = {
    dsi: { materiel: [], immateriel: [] },
    batiment: { materiel: [], immateriel: [] },
    other: { materiel: [], immateriel: [] },
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
    if (issuer === "autres_services") {
      grouped.other[category].push(resource);
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
  otherMaterialContainer.innerHTML = grouped.other.materiel.map(buildResourceCard).join("");
  otherImmaterialContainer.innerHTML = grouped.other.immateriel.map(buildResourceCard).join("");
  genericMaterialContainer.innerHTML = grouped.generic.materiel.map(buildResourceCard).join("");
  genericImmaterialContainer.innerHTML = grouped.generic.immateriel.map(buildResourceCard).join("");

  genericMaterialWrap?.classList.toggle("d-none", grouped.generic.materiel.length === 0);
  genericImmaterialWrap?.classList.toggle("d-none", grouped.generic.immateriel.length === 0);
  otherImmaterialWrap?.classList.toggle("d-none", grouped.other.immateriel.length === 0);

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
  emptyState.classList.toggle("d-none", (grouped.generic.materiel.length + grouped.generic.immateriel.length) > 0);
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
    Object.entries(resource.fields || {}).forEach(([fieldKey, value]) => {
      const field = document.getElementById(`dynamic_resource_${resource.id}_${fieldKey}`);
      if (field) {
        if (field.type === "checkbox") {
          field.checked = value === true || value === "true" || value === "Oui" || value === "on";
        } else {
          field.value = value || "";
        }
      }
    });
  });
}

function syncDossierTypeUi() {
  const dossierType = normalizeDossierType(document.getElementById("dossier_type").value || "arrivee");
  const destinationBlock = document.getElementById("serviceDestinationBlock");
  if (destinationBlock) {
    destinationBlock.classList.toggle("d-none", dossierType !== "changement_service");
  }
}

function hasCurrentDsiResources() {
  return Boolean(
    document.getElementById("has_pc").checked
    || document.getElementById("has_screen").checked
    || document.getElementById("has_phone").checked
    || document.getElementById("has_mail").checked
    || document.getElementById("vpn").checked
  );
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

function renderPrintSummary(formData) {
  // Construit la vue d'impression dediee utilisee par window.print().
  const container = document.getElementById("printSummary");
  if (!container) {
    return;
  }

  const dsiItems = [];
  const batimentItems = [];
  const otherItems = [];

  const pushItem = (target, label, detail, conditionSummary = "") => {
    const parts = [detail, conditionSummary].filter(Boolean);
    target.push(`<li><strong>${escapeHtml(label)}</strong>${parts.length ? ` : ${escapeHtml(parts.join(" - "))}` : ""}</li>`);
  };

  if (formData.materiel.ordinateur.selected) {
    pushItem(dsiItems, "Ordinateur", [formData.materiel.ordinateur.nomPoste, formData.materiel.ordinateur.marque, formData.materiel.ordinateur.modele, formData.materiel.ordinateur.numeroSerie].filter(Boolean).join(" - "), buildAssignmentConditionSummary(formData.materiel.ordinateur));
  }
  if (formData.materiel.ecran.selected) {
    pushItem(dsiItems, "Écran", [formData.materiel.ecran.marque, formData.materiel.ecran.modele, formData.materiel.ecran.numeroSerie].filter(Boolean).join(" - "), buildAssignmentConditionSummary(formData.materiel.ecran));
  }
  if (formData.materiel.telephone.selected) {
    pushItem(dsiItems, "Téléphone", [formData.materiel.telephone.nomTelephone, formData.materiel.telephone.marque, formData.materiel.telephone.modele, formData.materiel.telephone.imei].filter(Boolean).join(" - "), buildAssignmentConditionSummary(formData.materiel.telephone));
  }
  if (formData.materiel.tablette?.selected) {
    pushItem(dsiItems, "Tablette", [formData.materiel.tablette.nomTablette, formData.materiel.tablette.marque, formData.materiel.tablette.modele, formData.materiel.tablette.numeroSerie].filter(Boolean).join(" - "), buildAssignmentConditionSummary(formData.materiel.tablette));
  }
  if (formData.immateriel.vpn.selected) {
    pushItem(dsiItems, "VPN", "");
  }
  if (formData.immateriel.email.selected) {
    pushItem(dsiItems, "Email", formData.immateriel.email.adresse);
  }

  if (formData.materiel.badge.selected) {
    pushItem(batimentItems, "Badge d'accès", formData.materiel.badge.numero, buildAssignmentConditionSummary(formData.materiel.badge));
  }
  if (formData.materiel.cles?.selected) {
    pushItem(batimentItems, "Clé(s)", (formData.materiel.cles.values || []).join(" - "), buildAssignmentConditionSummary(formData.materiel.cles));
  }
  if (formData.materiel.veste.selected) {
    pushItem(batimentItems, "Veste", "", buildAssignmentConditionSummary(formData.materiel.veste));
  }
  if (formData.materiel.chaussuresSecurite.selected) {
    pushItem(batimentItems, "Chaussures de sécurité", "", buildAssignmentConditionSummary(formData.materiel.chaussuresSecurite));
  }
  if (formData.immateriel.zoneAlarme?.selected) {
    pushItem(batimentItems, "Zone alarme", (formData.immateriel.zoneAlarme.zones || []).join(" - "));
  }

  if (formData.materiel.vehicule.selected) {
    pushItem(otherItems, "Véhicule", [formData.materiel.vehicule.marque, formData.materiel.vehicule.modele, formData.materiel.vehicule.immatriculation].filter(Boolean).join(" - "), buildAssignmentConditionSummary(formData.materiel.vehicule));
  }
  if (formData.materiel.autre.selected) {
    pushItem(otherItems, "Autre matériel", formData.materiel.autre.description, buildAssignmentConditionSummary(formData.materiel.autre));
  }

  const restitutionItems = Object.entries(formData.restitution.items || {}).map(([key, state]) => {
    const config = EQUIPMENT_CONFIG.find((item) => item.key === key);
    const label = config.label || key;
    const parts = [restitutionStateLabels[state.state] || state.state, state.notes].filter(Boolean);
    return `<li><strong>${escapeHtml(label)}</strong> : ${escapeHtml(parts.join(" - "))}</li>`;
  });

  container.innerHTML = `
    <div class="print-sheet">
      <div class="print-sheet__header">
        <h1 class="print-sheet__title">Dossier d'attribution</h1>
        <p class="print-sheet__subtitle">${escapeHtml(formatStatusLabel(formData.workflow.status))} - ${escapeHtml(formData.beneficiaire.nom)} ${escapeHtml(formData.beneficiaire.prenom)}</p>
      </div>

      <section class="print-block">
        <h3>Bénéficiaire</h3>
        <div class="print-grid">
          <div class="print-line"><strong>Nom</strong><span>${escapeHtml(formData.beneficiaire.nom || "-")}</span></div>
          <div class="print-line"><strong>Prénom</strong><span>${escapeHtml(formData.beneficiaire.prenom || "-")}</span></div>
          <div class="print-line"><strong>Qualité</strong><span>${escapeHtml(formData.beneficiaire.qualite || "-")}</span></div>
          <div class="print-line"><strong>Mandat / Service</strong><span>${escapeHtml(formData.beneficiaire.mandat || formData.beneficiaire.service || "-")}</span></div>
          <div class="print-line"><strong>Fonction</strong><span>${escapeHtml(formData.beneficiaire.fonction || "-")}</span></div>
          <div class="print-line"><strong>Date de remise</strong><span>${escapeHtml(formData.meta.assignedAt || "-")}</span></div>
          <div class="print-line"><strong>Date de fiche</strong><span>${escapeHtml(new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(formData.meta.savedAt)))}</span></div>
        </div>
      </section>

      <section class="print-block">
        <h3>Ressources DSI</h3>
        ${dsiItems.length ? `<ul class="print-list">${dsiItems.join("")}</ul>` : "<p>Aucune ressource DSI.</p>"}
      </section>

      <section class="print-block">
        <h3>Ressources service bâtiment</h3>
        ${batimentItems.length ? `<ul class="print-list">${batimentItems.join("")}</ul>` : "<p>Aucune ressource bâtiment.</p>"}
      </section>

      <section class="print-block">
        <h3>Autres ressources attribuées</h3>
        ${otherItems.length ? `<ul class="print-list">${otherItems.join("")}</ul>` : "<p>Aucune autre ressource attribuée.</p>"}
      </section>

      <section class="print-block">
        <h3>Restitution</h3>
        <div class="print-grid">
          <div class="print-line"><strong>Date de restitution</strong><span>${escapeHtml(formData.restitution.returnedAt || "-")}</span></div>
          <div class="print-line"><strong>Motif</strong><span>${escapeHtml(formData.restitution.reason || "-")}</span></div>
        </div>
        <div class="print-line" style="margin-top:0.8rem;"><strong>Observations</strong><span>${escapeHtml(formData.restitution.notes || "-")}</span></div>
        <div style="margin-top:0.8rem;">
          ${restitutionItems.length ? `<ul class="print-list">${restitutionItems.join("")}</ul>` : "<p>Aucun détail de restitution.</p>"}
        </div>
      </section>

      <section class="print-block">
        <h3>Conformite et signature</h3>
        <div class="print-grid">
          <div class="print-line"><strong>RGPD</strong><span>${formData.validation.rgpdAccepted ? "Validation effectuée" : "Non validée"}</span></div>
        </div>
        ${formData.validation.signatureDataUrl ? `<div class="print-signature" style="margin-top:0.9rem;"><img src="${formData.validation.signatureDataUrl}" alt="Signature"></div>` : "<p style='margin-top:0.9rem;'>Aucune signature.</p>"}
      </section>
    </div>
  `;
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
      if (checkbox.checked && checkbox.id === "has_cles") {
        ensureRepeatableRow("clesRows", "Référence ou libellé de clé");
      }
      if (checkbox.checked && checkbox.id === "has_zone_alarme") {
        ensureRepeatableRow("zoneAlarmeRows", "Zone alarme");
      }
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
    const selected = selectedInput ? selectedInput.value : "agent";
    const isElu = selected === "elu";

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
  // Valide uniquement les ressources effectivement cochées
  // pour éviter les faux positifs sur les blocs masqués.
  const issues = [];
  Object.values(CORE_RESOURCE_RULES).flat().forEach((rule) => {
    clearFieldError(document.getElementById(rule.fieldId));
  });

  Object.entries(CORE_RESOURCE_RULES).forEach(([resourceKey, rules]) => {
    const equipment = buildEquipmentSelectionMap();
    const immaterial = buildIntangibleSelectionMap();
    const selected = Boolean(equipment[resourceKey]?.selected || immaterial[resourceKey]?.selected);
    if (!selected) {
      return;
    }
    rules.forEach((rule) => {
      const field = document.getElementById(rule.fieldId);
      const value = getFieldValue(rule.fieldId);
      if (rule.required && !value) {
        setFieldError(field, `${rule.label} obligatoire.`);
        issues.push(`${rule.label} manquant`);
        return;
      }
    });
  });

  if (document.getElementById("has_cles")?.checked && getRepeatableValues("clesRows").length === 0) {
    issues.push("Au moins une clé doit être renseignée");
  }

  if (document.getElementById("has_zone_alarme")?.checked && getRepeatableValues("zoneAlarmeRows").length === 0) {
    issues.push("Au moins une zone alarme doit être renseignée");
  }

  return issues;
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
    const config = EQUIPMENT_CONFIG.find((item) => item.key === key);
    const label = config.label || key;
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

function buildEquipmentSelectionMap() {
  return {
    ordinateur: { selected: document.getElementById("has_pc").checked, nomPoste: getFieldValue("pc_nom"), marque: getFieldValue("pc_marque"), modele: getFieldValue("pc_modele"), numeroSerie: getFieldValue("pc_sn"), ...getAssignmentConditionData("pc") },
    ecran: { selected: document.getElementById("has_screen").checked, marque: getFieldValue("screen_marque"), modele: getFieldValue("screen_modele"), numeroSerie: getFieldValue("screen_sn"), ...getAssignmentConditionData("screen") },
    telephone: { selected: document.getElementById("has_phone").checked, nomTelephone: getFieldValue("tel_nom"), marque: getFieldValue("tel_marque"), modele: getFieldValue("tel_modele"), imei: getFieldValue("tel_imei"), ...getAssignmentConditionData("tel") },
    tablette: { selected: document.getElementById("has_tablette").checked, nomTablette: getFieldValue("tablette_nom"), marque: getFieldValue("tablette_marque"), modele: getFieldValue("tablette_modele"), numeroSerie: getFieldValue("tablette_sn"), ...getAssignmentConditionData("tablette") },
    vehicule: { selected: document.getElementById("has_vehicule").checked, marque: getFieldValue("vehicule_marque"), modele: getFieldValue("vehicule_modele"), immatriculation: getFieldValue("vehicule_plaque"), ...getAssignmentConditionData("vehicule") },
    badge: { selected: document.getElementById("has_badge").checked, numero: getFieldValue("badge_numero"), ...getAssignmentConditionData("badge") },
    cles: { selected: document.getElementById("has_cles").checked, values: getRepeatableValues("clesRows"), ...getAssignmentConditionData("cles") },
    veste: { selected: document.getElementById("veste").checked, ...getAssignmentConditionData("veste") },
    chaussuresSecurite: { selected: document.getElementById("chaussure").checked, ...getAssignmentConditionData("chaussure") },
    autre: { selected: document.getElementById("has_autre").checked, description: getFieldValue("autre_materiel"), ...getAssignmentConditionData("autre") }
  };
}

function buildIntangibleSelectionMap() {
  return {
    vpn: { selected: document.getElementById("vpn").checked, category: "immateriel", ...getAssignmentConditionData("vpn") },
    email: { selected: document.getElementById("has_mail").checked, category: "immateriel", adresse: getFieldValue("email"), ...getAssignmentConditionData("email") },
    zoneAlarme: { selected: document.getElementById("has_zone_alarme").checked, category: "immateriel", zones: getRepeatableValues("zoneAlarmeRows"), ...getAssignmentConditionData("zoneAlarme") }
  };
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
    const config = EQUIPMENT_CONFIG.find((entry) => entry.key === key);
    pushIfSelected(key, item, config?.label || key);
  });
  Object.entries(formData.immateriel || {}).forEach(([key, item]) => {
    const config = EQUIPMENT_CONFIG.find((entry) => entry.key === key);
    pushIfSelected(key, item, config?.label || key);
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
    restitution: currentRestitutionData,
    validation: {
      rgpdAccepted: document.getElementById("rgpdCheck").checked,
      signatureDataUrl
    }
  };
}

function setCheckboxAndFields(checkboxId, checked, fields) {
  const checkbox = document.getElementById(checkboxId);
  if (checkbox) {
    checkbox.checked = Boolean(checked);
  }

  Object.entries(fields).forEach(([fieldId, value]) => {
    const field = document.getElementById(fieldId);
    if (field) {
      field.value = value || "";
    }
  });
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

  setCheckboxAndFields("has_pc", data.materiel.ordinateur.selected, { pc_nom: data.materiel.ordinateur.nomPoste, pc_sn: data.materiel.ordinateur.numeroSerie });
  setCheckboxAndFields("has_screen", data.materiel.ecran.selected, { screen_sn: data.materiel.ecran.numeroSerie });
  setCheckboxAndFields("has_phone", data.materiel.telephone.selected, { tel_nom: data.materiel.telephone.nomTelephone, tel_imei: data.materiel.telephone.imei });
  setCheckboxAndFields("has_tablette", data.materiel.tablette?.selected, { tablette_nom: data.materiel.tablette?.nomTablette, tablette_sn: data.materiel.tablette?.numeroSerie });
  setCheckboxAndFields("has_vehicule", data.materiel.vehicule.selected, { vehicule_plaque: data.materiel.vehicule.immatriculation });
  setCheckboxAndFields("has_badge", data.materiel.badge.selected, { badge_numero: data.materiel.badge.numero });
  setCheckboxAndFields("has_cles", data.materiel.cles?.selected, {});
  setCheckboxAndFields("has_autre", data.materiel.autre.selected, { autre_materiel: data.materiel.autre.description });
  setCheckboxAndFields("has_mail", data.immateriel.email.selected, { email: data.immateriel.email.adresse });
  setCheckboxAndFields("has_zone_alarme", data.immateriel.zoneAlarme?.selected, {});

  document.getElementById("pc_nom").value = data.materiel.ordinateur.nomPoste || "";
  document.getElementById("pc_marque").value = data.materiel.ordinateur.marque || "";
  document.getElementById("pc_modele").value = data.materiel.ordinateur.modele || "";
  document.getElementById("screen_marque").value = data.materiel.ecran.marque || "";
  document.getElementById("screen_modele").value = data.materiel.ecran.modele || "";
  document.getElementById("tel_nom").value = data.materiel.telephone.nomTelephone || "";
  document.getElementById("tel_marque").value = data.materiel.telephone.marque || "";
  document.getElementById("tel_modele").value = data.materiel.telephone.modele || "";
  document.getElementById("tablette_nom").value = data.materiel.tablette?.nomTablette || "";
  document.getElementById("tablette_marque").value = data.materiel.tablette?.marque || "";
  document.getElementById("tablette_modele").value = data.materiel.tablette?.modele || "";
  document.getElementById("vehicule_marque").value = data.materiel.vehicule.marque || "";
  document.getElementById("vehicule_modele").value = data.materiel.vehicule.modele || "";
  document.getElementById("pc_condition").value = data.materiel.ordinateur.conditionAttribution || "";
  document.getElementById("pc_assigned_at").value = normalizeDateInputValue(data.materiel.ordinateur.assignedAt || "");
  document.getElementById("pc_condition_notes").value = data.materiel.ordinateur.conditionNotes || "";
  document.getElementById("screen_condition").value = data.materiel.ecran.conditionAttribution || "";
  document.getElementById("screen_assigned_at").value = normalizeDateInputValue(data.materiel.ecran.assignedAt || "");
  document.getElementById("screen_condition_notes").value = data.materiel.ecran.conditionNotes || "";
  document.getElementById("tel_condition").value = data.materiel.telephone.conditionAttribution || "";
  document.getElementById("tel_assigned_at").value = normalizeDateInputValue(data.materiel.telephone.assignedAt || "");
  document.getElementById("tel_condition_notes").value = data.materiel.telephone.conditionNotes || "";
  document.getElementById("tablette_condition").value = data.materiel.tablette?.conditionAttribution || "";
  document.getElementById("tablette_assigned_at").value = normalizeDateInputValue(data.materiel.tablette?.assignedAt || "");
  document.getElementById("tablette_condition_notes").value = data.materiel.tablette?.conditionNotes || "";
  document.getElementById("vehicule_condition").value = data.materiel.vehicule.conditionAttribution || "";
  document.getElementById("vehicule_assigned_at").value = normalizeDateInputValue(data.materiel.vehicule.assignedAt || "");
  document.getElementById("vehicule_condition_notes").value = data.materiel.vehicule.conditionNotes || "";
  setFieldValueIfExists("badge_condition", data.materiel.badge.conditionAttribution || "");
  setFieldValueIfExists("badge_assigned_at", normalizeDateInputValue(data.materiel.badge.assignedAt || ""));
  setFieldValueIfExists("badge_condition_notes", data.materiel.badge.conditionNotes || "");
  document.getElementById("cles_condition").value = data.materiel.cles?.conditionAttribution || "";
  document.getElementById("cles_assigned_at").value = normalizeDateInputValue(data.materiel.cles?.assignedAt || "");
  document.getElementById("cles_condition_notes").value = data.materiel.cles?.conditionNotes || "";
  document.getElementById("veste_condition").value = data.materiel.veste.conditionAttribution || "";
  document.getElementById("veste_assigned_at").value = normalizeDateInputValue(data.materiel.veste.assignedAt || "");
  document.getElementById("veste_condition_notes").value = data.materiel.veste.conditionNotes || "";
  document.getElementById("chaussure_condition").value = data.materiel.chaussuresSecurite.conditionAttribution || "";
  document.getElementById("chaussure_assigned_at").value = normalizeDateInputValue(data.materiel.chaussuresSecurite.assignedAt || "");
  document.getElementById("chaussure_condition_notes").value = data.materiel.chaussuresSecurite.conditionNotes || "";
  document.getElementById("autre_condition").value = data.materiel.autre.conditionAttribution || "";
  document.getElementById("autre_assigned_at").value = normalizeDateInputValue(data.materiel.autre.assignedAt || "");
  document.getElementById("autre_condition_notes").value = data.materiel.autre.conditionNotes || "";
  document.getElementById("vpn_assigned_at").value = normalizeDateInputValue(data.immateriel.vpn.assignedAt || "");
  document.getElementById("email_assigned_at").value = normalizeDateInputValue(data.immateriel.email.assignedAt || "");
  document.getElementById("zoneAlarme_assigned_at").value = normalizeDateInputValue(data.immateriel.zoneAlarme?.assignedAt || "");
  populateRepeatableRows("clesRows", "Référence ou libellé de clé", data.materiel.cles?.values || []);
  populateRepeatableRows("zoneAlarmeRows", "Zone alarme", data.immateriel.zoneAlarme?.zones || []);

  document.getElementById("veste").checked = Boolean(data.materiel.veste.selected);
  document.getElementById("chaussure").checked = Boolean(data.materiel.chaussuresSecurite.selected);
  document.getElementById("vpn").checked = Boolean(data.immateriel.vpn.selected);
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
  const actionBtn = document.getElementById("saveAndCreateSignatureLinkBtn");
  if (!actionBtn) {
    return;
  }

  const canEdit = Boolean(sessionInfo?.permissions?.includes("*") || sessionInfo?.permissions?.includes("forms.edit"));
  if (!canEdit) {
    actionBtn.classList.add("d-none");
    return;
  }
  actionBtn.classList.remove("d-none");

  const hasCollectedSignature = Boolean(form.dataset.lockedAt || document.getElementById("signature")?.dataset.signed === "true");
  if (hasCollectedSignature) {
    actionBtn.disabled = true;
    actionBtn.textContent = "Dossier déjà signé";
    return;
  }

  actionBtn.disabled = false;
  if (link?.status === "active") {
    actionBtn.textContent = "Enregistrer et régénérer le lien";
    return;
  }

  actionBtn.textContent = "Enregistrer et générer le lien";
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
      window.alert(message);
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
      window.alert("Le lien de signature a été généré.");
    }
    return { link: result.link, absoluteUrl, copied };
  } catch (error) {
    if (!options.silentError) {
      window.alert(error.message || "Impossible de générer le lien de signature.");
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

  if (formData.beneficiaire.qualite === "elu" && !formData.beneficiaire.mandat) {
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
    return window.confirm(message) ? "confirm" : "secondary";
  }

  if (options.showConfirm) {
    window.alert(message);
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

async function askSignatureLinkValidityDays() {
  if (typeof window.askSignatureValidityDialog !== "function") {
    const rawValue = window.prompt("Durée de validité du lien de signature à distance (1 à 30 jours) :", "7");
    if (rawValue === null) {
      return null;
    }
    const parsed = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(parsed) || parsed < 1 || parsed > 30) {
      await showSaveInfoDialog("Durée invalide", "Veuillez saisir une durée comprise entre 1 et 30 jours.");
      return null;
    }
    return parsed;
  }

  return window.askSignatureValidityDialog({
    title: "Validité du lien de signature",
    text: "Choisissez pendant combien de jours le lien de signature à distance restera actif.",
    defaultValue: 7,
    maxDays: 30,
    confirmLabel: "Enregistrer et continuer"
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

async function saveDraft(signaturePad, options = {}) {
  const shouldGenerateRemoteLink = Boolean(options.generateSignatureLink);
  const workflowLabels = shouldGenerateRemoteLink
    ? [
        "Préparation des informations du dossier",
        "Analyse de complétude et du workflow",
        "Enregistrement sécurisé du dossier",
        "Génération du lien de signature",
      "Finalisation de l'interface"
      ]
    : [
        "Préparation des informations du dossier",
        "Analyse de complétude et du workflow",
        "Enregistrement sécurisé du dossier",
        "Finalisation de l'interface"
      ];

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

    if (result.offline && shouldGenerateRemoteLink) {
      closeSaveProgress();
      await showSaveInfoDialog(
        "Lien à distance indisponible",
        "Le dossier a été enregistré localement. Le lien de signature à distance pourra être généré après un enregistrement en base."
      );
      return;
    }

    let generatedSignatureLink = null;
    if (shouldGenerateRemoteLink) {
      updateSaveProgress({
        title: "Enregistrement du dossier",
        text: "Le lien de signature à distance est en cours de génération.",
        steps: createWorkflowSteps(workflowLabels, 3)
      });
      generatedSignatureLink = await createSignatureLink({
        validityDays: options.validityDays,
        silentSuccess: true,
        silentError: true,
        copyAfterGenerate: true
      });

      if (generatedSignatureLink?.absoluteUrl) {
        try {
          sessionStorage.setItem(DASHBOARD_SIGNATURE_LINK_NOTICE_KEY, JSON.stringify({
            kind: "assignment",
            formId: result.summary.id,
            linkId: generatedSignatureLink.link?.id,
            title: result.summary.title,
            url: generatedSignatureLink.absoluteUrl
          }));
        } catch (error) {
          // Rien de bloquant : le tableau de bord reste utilisable sans cette notice.
        }
      }
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
      window.location.href = "index.html";
      return;
    }

    await requestSaveDecision({
      title: shouldGenerateRemoteLink ? "Dossier enregistré et lien prêt" : "Dossier enregistré",
      text: shouldGenerateRemoteLink
        ? `La fiche « ${result.summary.title} » est enregistrée et le lien de signature à distance est prêt${generatedSignatureLink?.link?.expiresAt ? ` jusqu'au ${formatDateTime(generatedSignatureLink.link.expiresAt)}` : ""}.`
        : `La fiche « ${result.summary.title} » est maintenant à jour.`,
      steps: workflowLabels.map((label) => ({ label, status: "done" })),
      hideSpinner: true,
      showConfirm: true,
      confirmLabel: "OK"
    });
    window.location.href = "index.html";
  } catch (error) {
    console.error("Erreur lors de l'enregistrement du dossier", error);
    closeSaveProgress();
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

    document.getElementById("saveDraftBtn")?.addEventListener("click", () => {
      void saveDraft(signaturePad);
    });
    document.getElementById("saveAndCreateSignatureLinkBtn")?.addEventListener("click", async () => {
      const validityDays = await askSignatureLinkValidityDays();
      if (validityDays === null) {
        return;
      }
      await saveDraft(signaturePad, {
        generateSignatureLink: true,
        validityDays
      });
    });

    setFormBootstrapStage("initialisation des blocs métier", "Préparation du formulaire...");
    ensureAssignmentConditionFields();
    initRepeatableResourceLists();
    initConditionalBlocks();
    initQualite();
    syncDossierTypeUi();

    setFormBootstrapStage("ouverture de la fiche", "Chargement de la fiche...");
    await loadDraftFromUrl(signaturePad);

    [
      "has_pc",
      "has_screen",
      "has_phone",
      "has_mail",
      "vpn",
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
