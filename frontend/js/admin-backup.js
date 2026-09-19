// Sauvegarde multi-bases : export (chiffrement optionnel), analyse, restauration, copies de securite.
// S'appuie sur les helpers de admin-db.js (getCsrfToken, showDbResult, escapeHtml).

const BACKUP_ERROR_MESSAGES = {
  password_required: "Cette sauvegarde est protégée : saisissez son mot de passe.",
  wrong_password: "Mot de passe incorrect, ou archive altérée.",
  password_too_short: "Mot de passe trop court.",
  invalid_archive: "Ce fichier n'est pas une sauvegarde valide.",
  corrupted_archive: "Sauvegarde corrompue (empreinte invalide).",
  unsupported_format: "Format de sauvegarde non pris en charge.",
  file_too_large: "Archive trop volumineuse.",
  diagnose_failed: "Une base de l'archive est invalide : restauration refusée.",
  no_file: "Aucun fichier reçu."
};

const BACKUP_LEVEL_LABELS = { ok: "Valide", warning: "Valide, avec avertissements", error: "Invalide" };

function backupFormatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
}

function backupStatsText(stats) {
  const parts = [];
  if (stats?.dossiers !== undefined) parts.push(`${stats.dossiers} dossier(s)`);
  if (stats?.comptes !== undefined) parts.push(`${stats.comptes} compte(s)`);
  return parts.join(" · ");
}

async function backupRequest(url, options = {}) {
  const csrf = await getCsrfToken();
  return fetch(url, { credentials: "same-origin", ...options, headers: { "X-CSRF-Token": csrf, ...(options.headers || {}) } });
}

async function backupErrorText(response) {
  let data = null;
  try { data = await response.json(); } catch (error) { /* corps non JSON */ }
  return BACKUP_ERROR_MESSAGES[data?.error] || data?.message || `Erreur ${response.status}`;
}

async function loadBackupInfo() {
  try {
    const response = await fetch("/api/admin/backup/info", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    const info = await response.json();
    document.getElementById("backupMinLength").textContent = info.min_password_length;
    document.getElementById("backupDatabasesList").innerHTML = info.databases.map((db) =>
      `<li>${db.exists ? "✔" : "✖"} ${escapeHtml(db.label)} <span class="text-muted">(${db.exists ? backupFormatSize(db.size) : "absente"})</span></li>`
    ).join("");
    const safety = document.getElementById("backupSafetyList");
    safety.innerHTML = info.safety_copies.length
      ? `<ul class="list-unstyled mb-0">${info.safety_copies.map((copy) =>
          `<li><code>${escapeHtml(copy.name)}</code> · ${backupFormatSize(copy.size)} · ${escapeHtml(new Date(copy.modified).toLocaleString("fr-FR"))}</li>`).join("")}</ul>`
      : "Aucune copie de sécurité pour l'instant.";
  } catch (error) {
    document.getElementById("backupSafetyList").textContent = "Impossible de charger la liste.";
  }
}

function initBackupExport() {
  const protect = document.getElementById("backupProtect");
  const fields = document.getElementById("backupPasswordFields");
  const button = document.getElementById("backupExportBtn");
  if (!protect || !button) return;
  protect.addEventListener("change", () => fields.classList.toggle("d-none", !protect.checked));

  button.addEventListener("click", async () => {
    const password = protect.checked ? document.getElementById("backupPassword").value : "";
    if (protect.checked) {
      if (password.length < Number(document.getElementById("backupMinLength").textContent)) {
        showDbResult("backupExportResult", "error", "Mot de passe trop court.", "");
        return;
      }
      if (password !== document.getElementById("backupPasswordConfirm").value) {
        showDbResult("backupExportResult", "error", "Les deux mots de passe ne correspondent pas.", "");
        return;
      }
    } else if (!(await askConfirm("Exporter sans mot de passe ? L'archive contiendra les comptes et toutes les données personnelles en clair.", { confirmLabel: "Exporter sans protection", confirmClass: "btn-danger" }))) {
      return;
    }
    button.disabled = true;
    button.textContent = "Préparation…";
    try {
      const response = await backupRequest("/api/admin/backup/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password })
      });
      if (!response.ok) {
        showDbResult("backupExportResult", "error", await backupErrorText(response), "");
        return;
      }
      const blob = await response.blob();
      const match = (response.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = match ? match[1] : "sauvegarde.aqbak";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(link.href), 2000);
      showDbResult("backupExportResult", "ok", "Sauvegarde téléchargée.", `${escapeHtml(link.download)} · ${backupFormatSize(blob.size)}${password ? " · protégée par mot de passe" : ""}`);
      document.getElementById("backupPassword").value = "";
      document.getElementById("backupPasswordConfirm").value = "";
    } catch (error) {
      showDbResult("backupExportResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      button.disabled = false;
      button.textContent = "Télécharger la sauvegarde";
    }
  });
}

function backupRestoreForm() {
  const file = document.getElementById("backupRestoreFile")?.files?.[0];
  const fd = new FormData();
  if (file) fd.append("file", file);
  fd.append("password", document.getElementById("backupRestorePassword")?.value || "");
  return { file, fd };
}

function initBackupRestore() {
  const analyseBtn = document.getElementById("backupAnalyseBtn");
  const restoreBtn = document.getElementById("backupRestoreBtn");
  if (!analyseBtn || !restoreBtn) return;
  const choice = document.getElementById("backupRestoreChoice");

  analyseBtn.addEventListener("click", async () => {
    const { file, fd } = backupRestoreForm();
    choice.classList.add("d-none");
    document.getElementById("backupRestoreResult").classList.add("d-none");
    if (!file) {
      showDbResult("backupAnalyseResult", "error", "Sélectionnez un fichier de sauvegarde.", "");
      return;
    }
    analyseBtn.disabled = true;
    analyseBtn.textContent = "Analyse…";
    try {
      const response = await backupRequest("/api/admin/backup/diagnose", { method: "POST", body: fd });
      if (!response.ok) {
        showDbResult("backupAnalyseResult", "error", await backupErrorText(response), "");
        return;
      }
      const report = await response.json();
      const details = report.databases.map((db) => {
        const problems = [...(db.issues || []), ...(db.warnings || [])];
        return `<li><strong>${escapeHtml(db.label)}</strong> · ${BACKUP_LEVEL_LABELS[db.level] || db.level} · ${backupFormatSize(db.size)}${backupStatsText(db.stats) ? ` · ${escapeHtml(backupStatsText(db.stats))}` : ""}${problems.length ? `<ul>${problems.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>` : ""}</li>`;
      }).join("");
      showDbResult("backupAnalyseResult", report.level, `Sauvegarde ${BACKUP_LEVEL_LABELS[report.level].toLowerCase()}${report.encrypted ? " (protégée)" : ""}`,
        `${report.created_at ? `Créée le ${escapeHtml(new Date(report.created_at).toLocaleString("fr-FR"))}` : ""}<ul class="mb-0 mt-2">${details}</ul>`);
      if (report.level !== "error") {
        document.getElementById("backupRestoreKeys").innerHTML = report.databases.map((db) => `
          <div class="form-check">
            <input class="form-check-input backup-restore-key" type="checkbox" id="restore_${escapeHtml(db.key)}" value="${escapeHtml(db.key)}" checked>
            <label class="form-check-label" for="restore_${escapeHtml(db.key)}">${escapeHtml(db.label)}</label>
          </div>`).join("");
        choice.classList.remove("d-none");
      }
    } catch (error) {
      showDbResult("backupAnalyseResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      analyseBtn.disabled = false;
      analyseBtn.textContent = "Analyser";
    }
  });

  restoreBtn.addEventListener("click", async () => {
    const keys = [...document.querySelectorAll(".backup-restore-key:checked")].map((input) => input.value);
    if (!keys.length) {
      showDbResult("backupRestoreResult", "error", "Cochez au moins une base à restaurer.", "");
      return;
    }
    const labels = keys.map((key) => document.querySelector(`label[for="restore_${key}"]`)?.textContent || key).join(", ");
    if (!(await askConfirm(`Remplacer les données actuelles (${labels}) par celles de la sauvegarde ? Une copie de sécurité sera créée.`, { confirmLabel: "Restaurer", confirmClass: "btn-danger" }))) return;
    const { fd } = backupRestoreForm();
    fd.append("keys", keys.join(","));
    restoreBtn.disabled = true;
    restoreBtn.textContent = "Restauration…";
    try {
      const response = await backupRequest("/api/admin/backup/import", { method: "POST", body: fd });
      if (!response.ok) {
        showDbResult("backupRestoreResult", "error", await backupErrorText(response), "");
        return;
      }
      const data = await response.json();
      showDbResult("backupRestoreResult", "ok", "Restauration terminée.",
        `Bases restaurées : ${escapeHtml(data.restored.join(", "))}.<br>Copies de sécurité : ${data.safety_copies.map((name) => `<code>${escapeHtml(name)}</code>`).join(", ") || "aucune"}.<br>Rechargez la page ; reconnectez-vous si besoin.`);
      choice.classList.add("d-none");
      document.getElementById("backupRestoreFile").value = "";
      document.getElementById("backupRestorePassword").value = "";
      loadBackupInfo();
    } catch (error) {
      showDbResult("backupRestoreResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      restoreBtn.disabled = false;
      restoreBtn.textContent = "Restaurer la sélection";
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initBackupExport();
  initBackupRestore();
  loadBackupInfo();
});
