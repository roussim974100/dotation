// Sauvegarde automatique : reglages, mot de passe serveur, lancement immediat, commandes du planificateur.
// S'appuie sur admin-db.js et admin-backup.js (showDbResult, escapeHtml, backupRequest, askConfirm).

const SCHEDULE_ERROR_MESSAGES = {
  bad_frequency: "Fréquence invalide.",
  bad_time: "Heure invalide.",
  bad_weekday: "Jour invalide.",
  bad_retention: "Durée de conservation invalide (1 à 3650 jours, 1 à 1000 archives).",
  bad_env_var: "Nom de variable invalide (majuscules, chiffres et _ uniquement).",
  password_too_short: "Mot de passe trop court.",
  already_running: "Une sauvegarde est déjà en cours."
};

const SCHEDULE_HEALTH_CLASSES = { ok: "alert-success", info: "alert-info", warning: "alert-warning", error: "alert-danger" };

function scheduleEl(id) {
  return document.getElementById(id);
}

function renderScheduleView(view) {
  scheduleEl("schedEnabled").checked = view.schedule.enabled;
  scheduleEl("schedFrequency").value = view.schedule.frequency;
  scheduleEl("schedWeekday").value = String(view.schedule.weekday);
  scheduleEl("schedTime").value = view.schedule.time;
  scheduleEl("schedKeepDays").value = view.retention.keep_days;
  scheduleEl("schedKeepMin").value = view.retention.keep_min;
  scheduleEl("schedEnvVar").value = view.password.env_var;
  scheduleEl("schedAllowUnencrypted").checked = view.allow_unencrypted;
  scheduleEl("schedPassword").value = "";
  scheduleEl("schedWeekdayWrap").classList.toggle("d-none", view.schedule.frequency !== "weekly");

  const origins = { env: "variable d'environnement", file: "fichier protégé du serveur" };
  scheduleEl("schedPasswordState").textContent = view.password.available
    ? `Un mot de passe est défini (${origins[view.password.origin] || "serveur"}). Il n'est jamais affiché.`
    : "Aucun mot de passe défini : les sauvegardes automatiques seront refusées (sauf option non chiffrée).";
  scheduleEl("schedPasswordClear").classList.toggle("d-none", view.password.origin !== "file");

  const health = scheduleEl("scheduleHealth");
  health.className = `alert ${SCHEDULE_HEALTH_CLASSES[view.health.level] || "alert-info"}`;
  health.textContent = view.health.message + (view.next_run ? ` Prochaine échéance : ${new Date(view.next_run).toLocaleString("fr-FR")}.` : "");

  scheduleEl("cmdLinux").textContent = view.commands.linux;
  scheduleEl("cmdWindows").textContent = view.commands.windows;
  scheduleEl("cmdTest").textContent = view.commands.test;
}

async function loadScheduleView() {
  try {
    const response = await fetch("/api/admin/backup/schedule", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    renderScheduleView(await response.json());
  } catch (error) {
    showDbResult("schedResult", "error", "Impossible de charger la planification.", "");
  }
}

async function saveSchedule(extra = {}) {
  const payload = {
    schedule: {
      enabled: scheduleEl("schedEnabled").checked,
      frequency: scheduleEl("schedFrequency").value,
      weekday: Number(scheduleEl("schedWeekday").value),
      time: scheduleEl("schedTime").value
    },
    retention: { keep_days: Number(scheduleEl("schedKeepDays").value), keep_min: Number(scheduleEl("schedKeepMin").value) },
    password_source: { env_var: scheduleEl("schedEnvVar").value.trim() },
    allow_unencrypted: scheduleEl("schedAllowUnencrypted").checked,
    ...extra
  };
  const password = scheduleEl("schedPassword").value;
  if (password) payload.password = password;
  const response = await backupRequest("/api/admin/backup/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch (error) { /* corps non JSON */ }
    throw new Error(SCHEDULE_ERROR_MESSAGES[data?.error] || data?.message || `Erreur ${response.status}`);
  }
  renderScheduleView(await response.json());
}

document.addEventListener("DOMContentLoaded", () => {
  const form = scheduleEl("scheduleForm");
  if (!form) return;
  scheduleEl("schedFrequency").addEventListener("change", () => {
    scheduleEl("schedWeekdayWrap").classList.toggle("d-none", scheduleEl("schedFrequency").value !== "weekly");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = scheduleEl("schedSaveBtn");
    button.disabled = true;
    try {
      await saveSchedule();
      showDbResult("schedResult", "ok", "Planification enregistrée.", "");
    } catch (error) {
      showDbResult("schedResult", "error", error.message, "");
    } finally {
      button.disabled = false;
    }
  });

  scheduleEl("schedPasswordClear").addEventListener("click", async () => {
    if (!(await askConfirm("Effacer le mot de passe enregistré ? Les sauvegardes automatiques seront refusées tant qu'aucun mot de passe n'est défini.", { confirmLabel: "Effacer", confirmClass: "btn-danger" }))) return;
    try {
      await saveSchedule({ clear_password: true });
      showDbResult("schedResult", "ok", "Mot de passe effacé.", "");
    } catch (error) {
      showDbResult("schedResult", "error", error.message, "");
    }
  });

  scheduleEl("schedRunNowBtn").addEventListener("click", async () => {
    const button = scheduleEl("schedRunNowBtn");
    button.disabled = true;
    showDbResult("schedResult", "info", "Sauvegarde en cours…", "");
    try {
      const response = await backupRequest("/api/admin/backup/run-now", { method: "POST" });
      if (!response.ok) {
        let data = null;
        try { data = await response.json(); } catch (error) { /* corps non JSON */ }
        showDbResult("schedResult", "error", SCHEDULE_ERROR_MESSAGES[data?.error] || data?.message || `Erreur ${response.status}`, "");
        return;
      }
      const summary = await response.json();
      showDbResult("schedResult", summary.ok ? "ok" : "error",
        summary.ok ? `Sauvegarde envoyée vers ${summary.sent} destination(s).` : "La sauvegarde a échoué.",
        `${summary.deleted.length ? `${summary.deleted.length} ancienne(s) archive(s) supprimée(s). ` : ""}${summary.errors.map(escapeHtml).join("<br>")}`);
      if (typeof loadDestinations === "function") loadDestinations();
      if (typeof loadBackupHistory === "function") loadBackupHistory();
      loadScheduleView();
    } catch (error) {
      showDbResult("schedResult", "error", "Erreur de connexion au serveur.", "");
    } finally {
      button.disabled = false;
    }
  });

  loadScheduleView();
});
