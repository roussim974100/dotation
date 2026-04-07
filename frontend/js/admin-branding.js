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
  const response = await fetch(url, {
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
    support_email: raw.support_email || ""
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
    support_email: brandingById("brandingSupportEmail")?.value.trim()
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

  [orgChange, dpoChange, emailDomainsChange, themeChange, darkModeChange].filter(Boolean).forEach((item) => {
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

  toggleLogoFields(raw.brand_logo_mode);
  updateBrandingPreview(payload.logoUrl, raw.org_name || payload.orgName);
}

async function saveBrandingSettings() {
  const saveButton = brandingById("saveBrandingBtn");
  const payload = collectBrandingPayload();
  const previous = brandingSettingsSnapshot || normalizeBrandingSettings();
  const changeLabels = describeBrandingChanges(previous, payload);

  if (!changeLabels.length) {
    showBrandingNotice("Aucune modification à enregistrer.");
    return;
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
    updateBrandingSaveStep(steps, "save", "error");
    renderBrandingSaveDialog({
      title: "Enregistrement interrompu",
      text: "La personnalisation n'a pas pu être enregistrée. Vérifiez les informations saisies puis réessayez.",
      steps,
      showConfirm: true,
      confirmLabel: "Fermer",
      hideSpinner: true,
      onConfirm: closeBrandingSaveDialog
    });
    showBrandingNotice("Impossible d'enregistrer la personnalisation.", "danger");
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

document.addEventListener("DOMContentLoaded", async () => {
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

