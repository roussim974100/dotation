// Module dédié à la personnalisation visuelle :
// chargement, aperçu, sauvegarde guidée et retour au portail admin.
const ADMIN_FLASH_NOTICE_KEY = "adminFlashNotice";
const ADMIN_RETURN_URL = "admin.html";
const BRANDING_DARK_MODE_LABELS = {
  disabled: "Désactivé",
  allowed: "Autorisé",
  forced: "Forcé"
};
const BRANDING_LOGO_MODE_LABELS = {
  default: "Logo par défaut",
  url: "URL distante",
  file: "Fichier téléversé"
};

let brandingSettingsSnapshot = null;
let brandingThemeLabels = new Map();
let brandingSaveDialogConfirm = null;

function brandingById(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pause(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function brandingJson(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const csrfHeaders = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && typeof getCsrfToken === "function") {
    csrfHeaders["X-CSRF-Token"] = await getCsrfToken();
  }
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: { ...csrfHeaders, ...(options.headers || {}) }
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

function normalizeBrandingSettings(raw = {}) {
  return {
    org_name: raw.org_name || "",
    dpo_email: raw.dpo_email || "",
    email_domains: raw.email_domains || "",
    brand_logo_mode: raw.brand_logo_mode || "url",
    brand_logo_url: raw.brand_logo_url || "",
    theme_id: raw.theme_id || "institutionnel",
    dark_mode_policy: raw.dark_mode_policy || "disabled",
    org_context: raw.org_context || "public_collectivite",
    beneficiary_types: raw.beneficiary_types || "agent:Agent,elu:Élu(e)",
    support_name: raw.support_name || "",
    support_role: raw.support_role || "",
    support_email: raw.support_email || "",
    restitution_phase1_unlock_days: raw.restitution_phase1_unlock_days ?? "1",
    timing_warning_days: raw.timing_warning_days ?? "3",
    parc_retention_years: raw.parc_retention_years ?? "5",
    timezone: raw.timezone || "Europe/Paris"
  };
}

function collectBrandingPayload() {
  return normalizeBrandingSettings({
    org_name: brandingById("brandingOrgName")?.value.trim(),
    dpo_email: brandingById("brandingDpoEmail")?.value.trim(),
    email_domains: brandingById("brandingEmailDomains")?.value.trim(),
    brand_logo_mode: brandingById("brandingLogoMode")?.value,
    brand_logo_url: brandingById("brandingLogoUrl")?.value.trim(),
    theme_id: brandingById("brandingTheme")?.value,
    dark_mode_policy: brandingById("brandingDarkMode")?.value,
    org_context: brandingById("brandingOrgContext")?.value,
    beneficiary_types: brandingById("brandingBeneficiaryTypes")?.value.trim(),
    support_name: brandingById("brandingSupportName")?.value.trim(),
    support_role: brandingById("brandingSupportRole")?.value.trim(),
    support_email: brandingById("brandingSupportEmail")?.value.trim(),
    restitution_phase1_unlock_days: parseInt(brandingById("brandingPhase1UnlockDays")?.value || "1", 10),
    timing_warning_days: parseInt(brandingById("brandingTimingWarningDays")?.value || "3", 10),
    parc_retention_years: parseInt(brandingById("brandingParcRetentionYears")?.value || "5", 10),
    timezone: (resolveTimezone(brandingById("brandingTimezone")?.value) || brandingById("brandingTimezone")?.value || "Europe/Paris").trim()
  });
}

function updateBrandingPreview(url, orgName) {
  const preview = brandingById("brandingLogoPreview");
  if (!preview) {
    return;
  }
  preview.src = url || "assets/app-icon.svg";
  preview.alt = `Logo ${orgName || "A quai"}`;
}

function toggleLogoFields(mode) {
  brandingById("brandingLogoUrlWrap")?.classList.toggle("d-none", mode !== "url");
  brandingById("brandingLogoFileWrap")?.classList.toggle("d-none", mode !== "file");
}

function showBrandingNotice(message, tone = "info") {
  const notice = brandingById("brandingNotice");
  if (!notice) {
    return;
  }

  notice.textContent = message;
  notice.classList.remove("d-none", "alert-danger", "alert-info", "alert-success");
  if (tone === "danger") {
    notice.classList.add("alert-danger");
    return;
  }
  if (tone === "success") {
    notice.classList.add("alert-success");
    return;
  }
  notice.classList.add("alert-info");
}

function getThemeLabel(themeId) {
  return brandingThemeLabels.get(themeId) || themeId || "Non renseigné";
}

function describeValueChange(label, previousValue, nextValue) {
  const before = String(previousValue || "").trim();
  const after = String(nextValue || "").trim();
  if (before === after) {
    return "";
  }
  if (!before && after) {
    return `${label} défini sur ${after}.`;
  }
  if (before && !after) {
    return `${label} vidé.`;
  }
  return `${label} mis à jour : ${before} -> ${after}.`;
}

function describeBrandingChanges(previous, next) {
  const changes = [];
  const orgChange = describeValueChange("Nom de la collectivité", previous.org_name, next.org_name);
  const dpoChange = describeValueChange("E-mail du DPO", previous.dpo_email, next.dpo_email);
  const themeChange = describeValueChange("Thème", getThemeLabel(previous.theme_id), getThemeLabel(next.theme_id));
  const darkModeChange = describeValueChange("Mode sombre", BRANDING_DARK_MODE_LABELS[previous.dark_mode_policy], BRANDING_DARK_MODE_LABELS[next.dark_mode_policy]);
  const emailDomainsChange = describeValueChange("Domaines e-mail autorisés", previous.email_domains, next.email_domains);
  const supportNameChange = describeValueChange("Nom du contact support", previous.support_name, next.support_name);
  const supportEmailChange = describeValueChange("Email du contact support", previous.support_email, next.support_email);
  const supportRoleChange = describeValueChange("Rôle du contact support", previous.support_role, next.support_role);
  const orgContextChange = describeValueChange("Type d'organisation", previous.org_context, next.org_context);
  const beneficiaryTypesChange = describeValueChange("Types de bénéficiaires", previous.beneficiary_types, next.beneficiary_types);
  // Réglages numériques : sans eux, modifier UNIQUEMENT l'un d'eux donnait « Aucune modification à enregistrer » et rien n'était envoyé.
  const phase1Change = describeValueChange("Fenêtre de modification de la phase 1 (jours)", previous.restitution_phase1_unlock_days, next.restitution_phase1_unlock_days);
  const timingChange = describeValueChange("Seuil d'alerte pilotage (jours)", previous.timing_warning_days, next.timing_warning_days);
  const retentionChange = describeValueChange("Conservation de l'historique du parc (ans)", previous.parc_retention_years, next.parc_retention_years);
  const timezoneChange = describeValueChange("Fuseau horaire", previous.timezone, next.timezone);

  [orgChange, dpoChange, emailDomainsChange, themeChange, darkModeChange, supportNameChange, supportEmailChange, supportRoleChange, orgContextChange, beneficiaryTypesChange,
    phase1Change, timingChange, retentionChange, timezoneChange].filter(Boolean).forEach((item) => {
    changes.push(item);
  });

  if (previous.brand_logo_mode !== next.brand_logo_mode || previous.brand_logo_url !== next.brand_logo_url) {
    if (next.brand_logo_mode === "default") {
      changes.push("Logo rétabli sur le visuel par défaut de l'application.");
    } else if (next.brand_logo_mode === "file") {
      changes.push("Logo téléversé activé pour l'ensemble de l'application.");
    } else {
      changes.push(`Logo distant mis à jour via l'URL : ${next.brand_logo_url || "non renseignée"}.`);
    }
  }

  return changes;
}

function buildBrandingSaveSteps(changeLabels) {
  return [
    { key: "save", label: "Enregistrement des paramètres de personnalisation", status: "active" },
    ...changeLabels.map((label, index) => ({
      key: `change_${index}`,
      label,
      status: "pending"
    })),
    { key: "preview", label: "Actualisation de l'aperçu local", status: "pending" },
    { key: "branding", label: "Propagation du branding dans l'interface", status: "pending" },
    { key: "return", label: "Préparation du retour vers l'accueil admin", status: "pending" }
  ];
}

function getBrandingSaveStateLabel(status) {
  if (status === "active") {
    return "En cours";
  }
  if (status === "done") {
    return "Terminé";
  }
  if (status === "error") {
    return "Erreur";
  }
  return "À traiter";
}

function renderBrandingSaveDialog({ title, text, steps, showConfirm = false, confirmLabel = "OK", onConfirm = null, hideSpinner = false }) {
  const overlay = brandingById("brandingSaveLoader");
  const titleNode = brandingById("brandingSaveLoaderTitle");
  const textNode = brandingById("brandingSaveLoaderText");
  const stepsNode = brandingById("brandingSaveLoaderSteps");
  const actionsNode = brandingById("brandingSaveLoaderActions");
  const confirmButton = brandingById("brandingSaveLoaderConfirmBtn");
  const spinner = brandingById("brandingSaveLoaderSpinner");

  if (!overlay || !titleNode || !textNode || !stepsNode || !actionsNode || !confirmButton || !spinner) {
    return;
  }

  titleNode.textContent = title;
  textNode.textContent = text;
  spinner.classList.toggle("d-none", hideSpinner);
  stepsNode.innerHTML = steps.map((step) => `
    <li class="branding-save-loader__item is-${escapeHtml(step.status)}">
      <span class="branding-save-loader__bullet" aria-hidden="true"></span>
      <div class="branding-save-loader__content">
        <span class="branding-save-loader__label">${escapeHtml(step.label)}</span>
        <span class="branding-save-loader__state">${escapeHtml(getBrandingSaveStateLabel(step.status))}</span>
      </div>
    </li>
  `).join("");

  actionsNode.classList.toggle("d-none", !showConfirm);
  confirmButton.textContent = confirmLabel;
  brandingSaveDialogConfirm = onConfirm;
  overlay.classList.remove("is-hidden");
  overlay.setAttribute("aria-hidden", "false");
}

function closeBrandingSaveDialog() {
  const overlay = brandingById("brandingSaveLoader");
  if (!overlay) {
    return;
  }
  overlay.classList.add("is-hidden");
  overlay.setAttribute("aria-hidden", "true");
  brandingSaveDialogConfirm = null;
}

function updateBrandingSaveStep(steps, key, status) {
  const step = steps.find((item) => item.key === key);
  if (!step) {
    return;
  }
  step.status = status;
}

async function loadBrandingSettings() {
  const payload = await brandingJson("/api/admin/settings");
  const raw = normalizeBrandingSettings(payload.raw || {});

  brandingThemeLabels = new Map((payload.themeOptions || []).map((theme) => [theme.id, theme.label]));
  brandingSettingsSnapshot = raw;

  brandingById("brandingOrgName").value = raw.org_name;
  brandingById("brandingDpoEmail").value = raw.dpo_email || payload.dpoEmail || "";
  brandingById("brandingEmailDomains").value = raw.email_domains || "";
  brandingById("brandingLogoMode").value = raw.brand_logo_mode;
  brandingById("brandingLogoUrl").value = raw.brand_logo_url;
  brandingById("brandingTheme").innerHTML = (payload.themeOptions || []).map((theme) => `
    <option value="${theme.id}">${theme.label}</option>
  `).join("");
  brandingById("brandingTheme").value = raw.theme_id;
  brandingById("brandingDarkMode").value = raw.dark_mode_policy;
  if (brandingById("brandingOrgContext")) {
    brandingById("brandingOrgContext").value = raw.org_context || "public_collectivite";
  }
  if (brandingById("brandingBeneficiaryTypes")) {
    brandingById("brandingBeneficiaryTypes").value = raw.beneficiary_types || "agent:Agent,elu:Élu(e)";
  }
  if (brandingById("brandingSupportName")) brandingById("brandingSupportName").value = raw.support_name || "";
  if (brandingById("brandingSupportRole")) brandingById("brandingSupportRole").value = raw.support_role || "";
  if (brandingById("brandingSupportEmail")) brandingById("brandingSupportEmail").value = raw.support_email || "";
  if (brandingById("brandingPhase1UnlockDays")) brandingById("brandingPhase1UnlockDays").value = raw.restitution_phase1_unlock_days ?? "1";
  if (brandingById("brandingTimingWarningDays")) brandingById("brandingTimingWarningDays").value = raw.timing_warning_days ?? "3";
  if (brandingById("brandingParcRetentionYears")) brandingById("brandingParcRetentionYears").value = raw.parc_retention_years ?? "5";
  if (brandingById("brandingTimezone")) {
    setTimezoneValue(raw.timezone);
  }

  toggleLogoFields(raw.brand_logo_mode);
  updateBrandingPreview(payload.logoUrl, raw.org_name || payload.orgName);
}

async function checkBeneficiaryTypesConflict(previousTypes, newTypes) {
  if (!newTypes || previousTypes === newTypes) {
    return null;
  }
  try {
    const params = new URLSearchParams({ beneficiary_types: newTypes });
    const response = await fetch(`/api/admin/settings/conflict-check?${params}`, { credentials: "same-origin" });
    if (!response.ok) return null;
    const data = await response.json();
    return data.hasConflicts ? data : null;
  } catch (error) {
    return null;
  }
}

async function saveBrandingSettings() {
  const saveButton = brandingById("saveBrandingBtn");
  const payload = collectBrandingPayload();
  const previous = brandingSettingsSnapshot || normalizeBrandingSettings();
  const changeLabels = describeBrandingChanges(previous, payload);

  if (!changeLabels.length) {
    showBrandingNotice("Aucune modification à enregistrer.");
    brandingById("brandingNotice")?.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }

  const conflict = await checkBeneficiaryTypesConflict(previous.beneficiary_types, payload.beneficiary_types);
  if (conflict) {
    const lines = conflict.conflicts.map((c) => `• "${escapeHtml(c.type)}" : ${c.count} dossier${c.count > 1 ? "s" : ""}`).join("\n");
    const confirmed = window.confirm(
      `Attention : ${conflict.totalAffected} dossier${conflict.totalAffected > 1 ? "s" : ""} utilisent un type de bénéficiaire qui sera supprimé :\n\n${lines}\n\nCes dossiers ne seront plus filtrables par type. Continuer quand même ?`
    );
    if (!confirmed) return;
  }

  const steps = buildBrandingSaveSteps(changeLabels);

  try {
    if (saveButton) {
      saveButton.disabled = true;
      saveButton.textContent = "Enregistrement...";
    }

    renderBrandingSaveDialog({
      title: "Enregistrement de la personnalisation",
      text: "Les changements détectés sont en cours d'application.",
      steps
    });

    const response = await brandingJson("/api/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    updateBrandingSaveStep(steps, "save", "done");
    renderBrandingSaveDialog({
      title: "Enregistrement de la personnalisation",
      text: "Les paramètres sont enregistrés. L'application finalise maintenant la mise à jour visuelle.",
      steps
    });

    for (const step of steps.filter((item) => item.key.startsWith("change_"))) {
      updateBrandingSaveStep(steps, step.key, "active");
      renderBrandingSaveDialog({
        title: "Enregistrement de la personnalisation",
        text: "Les changements détectés sont en cours d'application.",
        steps
      });
      await pause(90);
      updateBrandingSaveStep(steps, step.key, "done");
    }

    updateBrandingSaveStep(steps, "preview", "active");
    renderBrandingSaveDialog({
      title: "Enregistrement de la personnalisation",
      text: "Mise à jour de l'aperçu du logo et des libellés de la page.",
      steps
    });
    updateBrandingPreview(response.logoUrl, response.orgName);
    await pause(120);
    updateBrandingSaveStep(steps, "preview", "done");

    updateBrandingSaveStep(steps, "branding", "active");
    renderBrandingSaveDialog({
      title: "Enregistrement de la personnalisation",
      text: "Application du branding dans l'ensemble de l'interface.",
      steps
    });
    let brandingRefreshError = false;
    if (window.loadBranding) {
      try {
        await window.loadBranding();
      } catch (error) {
        brandingRefreshError = true;
      }
    }
    await pause(120);
    updateBrandingSaveStep(steps, "branding", brandingRefreshError ? "error" : "done");

    updateBrandingSaveStep(steps, "return", "done");
    brandingSettingsSnapshot = payload;
    showBrandingNotice(
      brandingRefreshError
        ? "Personnalisation enregistrée. L'actualisation locale du thème sera visible au prochain chargement."
        : "Personnalisation enregistrée avec succès.",
      brandingRefreshError ? "info" : "success"
    );

    try {
      sessionStorage.setItem(ADMIN_FLASH_NOTICE_KEY, "Personnalisation enregistrée avec succès.");
    } catch (error) {
      // Rien de bloquant si le stockage local est indisponible.
    }

    renderBrandingSaveDialog({
      title: "Personnalisation enregistrée",
      text: brandingRefreshError
        ? "Les changements sont enregistrés. L'interface locale terminera son actualisation au prochain chargement. Cliquez sur OK pour revenir au portail admin."
        : "Tous les changements ont été appliqués. Cliquez sur OK pour revenir au portail admin.",
      steps,
      showConfirm: true,
      confirmLabel: "OK",
      hideSpinner: true,
      onConfirm: () => {
        window.location.href = ADMIN_RETURN_URL;
      }
    });
  } catch (error) {
    // Le serveur explique un refus de validation en français (ex. « Fuseau horaire inconnu ») ; un code technique ou « HTTP 500 » reste masqué.
    const serverReason = /^[A-ZÀ-Ý«]/.test(error?.message || "") && !/^HTTP /.test(error.message) ? error.message : "";
    updateBrandingSaveStep(steps, "save", "error");
    renderBrandingSaveDialog({
      title: "Enregistrement interrompu",
      text: `La personnalisation n'a pas pu être enregistrée.${serverReason ? ` ${serverReason}` : " Vérifiez les informations saisies puis réessayez."}`,
      steps,
      showConfirm: true,
      confirmLabel: "Fermer",
      hideSpinner: true,
      onConfirm: closeBrandingSaveDialog
    });
    showBrandingNotice(`Impossible d'enregistrer la personnalisation.${serverReason ? ` ${serverReason}` : ""}`, "danger");
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.textContent = "Enregistrer la personnalisation";
    }
  }
}

async function uploadBrandingLogo() {
  const fileInput = brandingById("brandingLogoFile");
  const file = fileInput?.files?.[0];

  if (!file) {
    showBrandingNotice("Choisissez d'abord un fichier logo.", "danger");
    return;
  }

  const formData = new FormData();
  formData.append("logo", file);

  try {
    const response = await fetch("/api/admin/settings/logo-upload", {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    });
    if (!response.ok) {
      throw new Error("upload_failed");
    }

    const payload = await response.json();
    brandingById("brandingLogoMode").value = "file";
    toggleLogoFields("file");
    updateBrandingPreview(payload.logoUrl, brandingById("brandingOrgName").value.trim());
    showBrandingNotice("Logo téléversé et activé.", "success");

    if (window.loadBranding) {
      window.loadBranding();
    }
  } catch (error) {
    showBrandingNotice("Impossible de téléverser le logo.", "danger");
  }
}

// Fuseau horaire de l'organisation : une liste déroulante, avec d'abord les cas courants en français (France et outre-mer, pays
// voisins, Canada, Maghreb et Afrique francophone), puis tous les fuseaux connus du navigateur regroupés par région.
// Décrire les groupes par des données (TIMEZONE_GROUPS) : en ajouter un = ajouter une entrée, sans toucher au rendu.
const TIMEZONE_GROUPS = [
  { label: "France et outre-mer", zones: {
    "Europe/Paris": "France métropolitaine", "America/Martinique": "Martinique", "America/Guadeloupe": "Guadeloupe", "America/Cayenne": "Guyane",
    "Indian/Reunion": "La Réunion", "Indian/Mayotte": "Mayotte", "America/Miquelon": "Saint-Pierre-et-Miquelon",
    "Pacific/Noumea": "Nouvelle-Calédonie", "Pacific/Tahiti": "Polynésie française (Tahiti)", "Pacific/Wallis": "Wallis-et-Futuna" } },
  { label: "Europe francophone", zones: {
    "Europe/Brussels": "Belgique", "Europe/Zurich": "Suisse", "Europe/Luxembourg": "Luxembourg", "Europe/Monaco": "Monaco" } },
  { label: "Canada", zones: { "America/Toronto": "Québec et Ontario", "America/Halifax": "Provinces de l'Atlantique", "America/Vancouver": "Colombie-Britannique" } },
  { label: "Afrique francophone", zones: {
    "Africa/Algiers": "Algérie", "Africa/Tunis": "Tunisie", "Africa/Casablanca": "Maroc", "Africa/Dakar": "Sénégal", "Africa/Abidjan": "Côte d'Ivoire" } },
];

function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (error) {
    return "";
  }
}

function timezoneOffsetLabel(name) {
  try {
    return new Intl.DateTimeFormat("fr-FR", { timeZone: name, timeZoneName: "shortOffset" }).formatToParts(new Date()).find((part) => part.type === "timeZoneName")?.value || "";
  } catch (error) {
    return "";
  }
}

function timezoneOptionLabel(name, friendly) {
  const offset = timezoneOffsetLabel(name);
  return `${friendly ? `${friendly} — ` : ""}${name}${offset ? ` (${offset})` : ""}`;
}

function allKnownTimezones() {
  try {
    return typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  } catch (error) {
    return [];
  }
}

// Champ à saisie libre avec suggestions : on peut taper un nom IANA (Europe/Paris), un lieu en français (« Réunion », « Belgique »)
// ou choisir dans la liste. TIMEZONE_CHOICES garde, pour chaque fuseau proposé, son libellé : c'est ce qui permet de retrouver
// « Indian/Reunion » à partir de « Réunion » (comparaison sans accents ni majuscules).
let TIMEZONE_CHOICES = [];

function normalizeTimezoneText(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function buildTimezoneOptions() {
  const list = brandingById("brandingTimezoneList");
  if (!list) {
    return;
  }
  const used = new Set();
  const choices = [];
  TIMEZONE_GROUPS.forEach((group) => {
    Object.entries(group.zones).forEach(([name, friendly]) => {
      used.add(name);
      choices.push({ name, friendly, label: timezoneOptionLabel(name, friendly) });
    });
  });
  allKnownTimezones().filter((name) => !used.has(name)).forEach((name) => {
    choices.push({ name, friendly: "", label: timezoneOptionLabel(name, "") });
  });
  if (!choices.some((choice) => choice.name === "UTC")) {
    choices.push({ name: "UTC", friendly: "", label: timezoneOptionLabel("UTC", "") });
  }
  TIMEZONE_CHOICES = choices;
  const escape = (value) => String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  list.innerHTML = choices.map((choice) => `<option value="${escape(choice.name)}" label="${escape(choice.label)}"></option>`).join("");
}

// Ce que la personne a tapé : un nom exact, ou un lieu qui ne correspond qu'à UN fuseau. null = inconnu (le serveur le vérifiera aussi).
function resolveTimezone(text) {
  const wanted = normalizeTimezoneText(text);
  if (!wanted) {
    return null;
  }
  const exact = TIMEZONE_CHOICES.find((choice) => normalizeTimezoneText(choice.name) === wanted);
  if (exact) {
    return exact.name;
  }
  const named = TIMEZONE_CHOICES.filter((choice) => choice.friendly && normalizeTimezoneText(choice.friendly).includes(wanted));
  if (named.length === 1) {
    return named[0].name;
  }
  const byCity = TIMEZONE_CHOICES.filter((choice) => normalizeTimezoneText(choice.name.split("/").pop()) === wanted);
  return byCity.length === 1 ? byCity[0].name : null;
}

// Un fuseau valide pour le navigateur mais absent de la liste (ex. alias) reste utilisable : on teste en le formatant.
function isUsableTimezone(name) {
  try {
    new Intl.DateTimeFormat("fr-FR", { timeZone: name });
    return true;
  } catch (error) {
    return false;
  }
}

function setTimezoneValue(name) {
  const input = brandingById("brandingTimezone");
  if (!input) {
    return;
  }
  input.value = name || "Europe/Paris";
  updateTimezonePreview();
}

// Décalage (en minutes) d'un fuseau à une date donnée, lu dans la base des fuseaux du navigateur (donc règles d'été / d'hiver comprises).
function timezoneOffsetMinutes(name, date) {
  const text = new Intl.DateTimeFormat("en-US", { timeZone: name, timeZoneName: "longOffset" }).formatToParts(date).find((part) => part.type === "timeZoneName")?.value || "GMT";
  const match = text.match(/GMT([+-])(\d{1,2})(?::?(\d{2}))?/);
  if (!match) {
    return 0;  // « GMT » seul : décalage nul
  }
  return (match[1] === "-" ? -1 : 1) * (Number(match[2]) * 60 + Number(match[3] || 0));
}

// Heure d'été / d'hiver : le fuseau en observe-t-il une, laquelle est en vigueur, et quand a lieu le prochain changement ?
// (heure d'été = le décalage le plus élevé des deux saisons, dans les deux hémisphères)
function timezoneChangeInfo(name, from = new Date()) {
  const offsetNow = timezoneOffsetMinutes(name, from);
  const january = timezoneOffsetMinutes(name, new Date(Date.UTC(from.getUTCFullYear(), 0, 15)));
  const july = timezoneOffsetMinutes(name, new Date(Date.UTC(from.getUTCFullYear(), 6, 15)));
  const info = { offsetNow, observesDst: january !== july, isDst: january !== july && offsetNow === Math.max(january, july), nextChange: null, nextOffset: null };
  let previous = offsetNow;
  for (let day = 1; day <= 400 && info.observesDst; day += 1) {
    const date = new Date(from.getTime() + day * 86400000);
    const offset = timezoneOffsetMinutes(name, date);
    if (offset !== previous) {
      info.nextChange = date;
      info.nextOffset = offset;
      break;
    }
  }
  return info;
}

function formatOffsetMinutes(minutes) {
  const sign = minutes < 0 ? "-" : "+";
  const abs = Math.abs(minutes);
  return `UTC${sign}${Math.floor(abs / 60)}${abs % 60 ? `:${String(abs % 60).padStart(2, "0")}` : ""}`;
}

function describeTimezoneChange(name, from = new Date()) {
  const info = timezoneChangeInfo(name, from);
  if (!info.observesDst) {
    return "Ce fuseau n'a pas de changement d'heure : le décalage est le même toute l'année.";
  }
  const season = info.isDst ? "Heure d'été en vigueur" : "Heure d'hiver en vigueur";
  if (!info.nextChange) {
    return `${season}.`;
  }
  const day = info.nextChange.toLocaleDateString("fr-FR", { timeZone: name, weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const toDst = info.nextOffset > info.offsetNow;
  return `${season}. Prochain changement d'heure : ${day}, passage à l'${toDst ? "heure d'été" : "heure d'hiver"} (${formatOffsetMinutes(info.nextOffset)}). Les heures des PDF suivent ce changement automatiquement.`;
}

function updateTimezonePreview() {
  const select = brandingById("brandingTimezone");
  const preview = brandingById("brandingTimezonePreview");
  if (!select || !preview) {
    return;
  }
  const name = select.value.trim();
  select.setAttribute("aria-invalid", "false");
  if (!isUsableTimezone(name)) {
    select.setAttribute("aria-invalid", name ? "true" : "false");
    preview.textContent = name
      ? "Fuseau inconnu : choisissez-en un dans la liste ou tapez un nom comme Europe/Paris."
      : "Europe/Paris par défaut.";
    return;
  }
  try {
    const time = new Date().toLocaleTimeString("fr-FR", { timeZone: name, hour: "2-digit", minute: "2-digit" });
    const offset = timezoneOffsetLabel(name);
    preview.textContent = `Il est actuellement ${time} dans ce fuseau${offset ? ` (${offset})` : ""}. ${describeTimezoneChange(name)}`;
  } catch (error) {
    preview.textContent = "Fuseau inconnu de ce navigateur : il sera vérifié à l'enregistrement.";
  }
}

function initTimezoneField() {
  const input = brandingById("brandingTimezone");
  if (!input) {
    return;
  }
  buildTimezoneOptions();
  input.addEventListener("input", updateTimezonePreview);
  // À la sortie du champ (ou au choix d'une suggestion) : « Réunion » devient « Indian/Reunion » si ce lieu est sans ambiguïté.
  input.addEventListener("change", () => {
    const resolved = resolveTimezone(input.value);
    if (resolved) {
      input.value = resolved;
    }
    updateTimezonePreview();
  });
  brandingById("brandingTimezoneDetect")?.addEventListener("click", () => {
    const detected = browserTimezone();
    if (detected) {
      setTimezoneValue(detected);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
  updateTimezonePreview();
}

document.addEventListener("DOMContentLoaded", async () => {
  initTimezoneField();
  if (!brandingById("brandingOrgName")) {
    return;
  }

  brandingById("brandingSaveLoaderConfirmBtn")?.addEventListener("click", () => {
    if (typeof brandingSaveDialogConfirm === "function") {
      const callback = brandingSaveDialogConfirm;
      brandingSaveDialogConfirm = null;
      callback();
      return;
    }
    closeBrandingSaveDialog();
  });

  try {
    await loadBrandingSettings();
  } catch (error) {
    showBrandingNotice("Impossible de charger la personnalisation.", "danger");
  }

  brandingById("brandingLogoMode")?.addEventListener("change", (event) => {
    toggleLogoFields(event.target.value);
  });
  brandingById("saveBrandingBtn")?.addEventListener("click", saveBrandingSettings);
  brandingById("uploadBrandingLogoBtn")?.addEventListener("click", uploadBrandingLogo);
});

