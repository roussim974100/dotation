// Module dedie a la personnalisation visuelle :
// chargement, apercu, sauvegarde et retour au portail admin.
const ADMIN_FLASH_NOTICE_KEY = "adminFlashNotice";
const ADMIN_RETURN_URL = "admin.html";

function brandingById(id) {
  return document.getElementById(id);
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

function updateBrandingPreview(url, orgName) {
  const preview = brandingById("brandingLogoPreview");
  if (!preview) {
    return;
  }
  preview.src = url || "assets/app-icon.svg";
  preview.alt = `Logo ${orgName || "collectivite"}`;
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
  notice.classList.add(tone === "danger" ? "alert-danger" : "alert-info");
}

async function loadBrandingSettings() {
  const payload = await brandingJson("/api/admin/settings");
  const raw = payload.raw || {};

  brandingById("brandingOrgName").value = raw.org_name || "";
  brandingById("brandingAppName").value = raw.app_name || "";
  brandingById("brandingDpoEmail").value = raw.dpo_email || payload.dpoEmail || "";
  brandingById("brandingLogoMode").value = raw.brand_logo_mode || "url";
  brandingById("brandingLogoUrl").value = raw.brand_logo_url || "";
  brandingById("brandingTheme").innerHTML = (payload.themeOptions || []).map((theme) => `
    <option value="${theme.id}">${theme.label}</option>
  `).join("");
  brandingById("brandingTheme").value = raw.theme_id || "institutionnel";
  brandingById("brandingDarkMode").value = raw.dark_mode_policy || "disabled";

  toggleLogoFields(brandingById("brandingLogoMode").value);
  updateBrandingPreview(payload.logoUrl, raw.org_name || payload.orgName);
}

async function saveBrandingSettings() {
  const saveButton = brandingById("saveBrandingBtn");
  const payload = {
    org_name: brandingById("brandingOrgName").value.trim(),
    app_name: brandingById("brandingAppName").value.trim(),
    dpo_email: brandingById("brandingDpoEmail").value.trim(),
    brand_logo_mode: brandingById("brandingLogoMode").value,
    brand_logo_url: brandingById("brandingLogoUrl").value.trim(),
    theme_id: brandingById("brandingTheme").value,
    dark_mode_policy: brandingById("brandingDarkMode").value
  };

  try {
    if (saveButton) {
      saveButton.disabled = true;
      saveButton.textContent = "Enregistrement...";
    }

    const response = await brandingJson("/api/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    updateBrandingPreview(response.logoUrl, response.orgName);
    if (window.loadBranding) {
      await window.loadBranding();
    }

    showBrandingNotice("Personnalisation enregistrée. Retour au portail admin...");

    try {
      sessionStorage.setItem(ADMIN_FLASH_NOTICE_KEY, "Personnalisation enregistree avec succes.");
    } catch (error) {
      // Rien de bloquant si le stockage local est indisponible.
    }

    window.setTimeout(() => {
      window.location.href = ADMIN_RETURN_URL;
    }, 500);
  } catch (error) {
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
    showBrandingNotice("Logo televerse et active.");

    if (window.loadBranding) {
      window.loadBranding();
    }
  } catch (error) {
    showBrandingNotice("Impossible de televerser le logo.", "danger");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  if (!brandingById("brandingOrgName")) {
    return;
  }

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
