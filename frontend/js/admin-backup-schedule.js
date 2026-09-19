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

let schedulerPaths = null;
let savedScheduleSignature = "";

// Jours : numero ISO (1 = lundi) -> libelle, code cron (0 = dimanche) et code schtasks.
const SCHEDULE_DAYS = {
  1: { label: "lundi", cron: 1, win: "MON" }, 2: { label: "mardi", cron: 2, win: "TUE" },
  3: { label: "mercredi", cron: 3, win: "WED" }, 4: { label: "jeudi", cron: 4, win: "THU" },
  5: { label: "vendredi", cron: 5, win: "FRI" }, 6: { label: "samedi", cron: 6, win: "SAT" },
  7: { label: "dimanche", cron: 0, win: "SUN" }
};

function scheduleSignature() {
  return [scheduleEl("schedEnabled").checked, scheduleEl("schedFrequency").value, scheduleEl("schedWeekday").value, scheduleEl("schedTime").value].join("|");
}

// Chemins reels du serveur pour son propre systeme ; chemins modeles a adapter pour l'autre.
const SCHEDULER_TEMPLATE_PATHS = {
  linux: { python: "/usr/bin/python3", script: "/chemin/application/backend/backup_cli.py", workdir: "/chemin/application/backend", log: "/chemin/application/backend/db_backups/backup_cron.log" },
  windows: { python: "C:\\chemin\\python.exe", script: "C:\\chemin\\application\\backend\\backup_cli.py", workdir: "C:\\chemin\\application\\backend", log: "C:\\chemin\\application\\backend\\db_backups\\backup_cron.log" }
};

function schedulerPathsFor(system) {
  return schedulerPaths.platform === system ? schedulerPaths : SCHEDULER_TEMPLATE_PATHS[system];
}

// Compose les commandes du planificateur d'apres les reglages affiches (mises a jour en direct).
function buildSchedulerCommands(settings) {
  const [hour, minute] = settings.time.split(":").map(Number);
  const weekly = settings.frequency === "weekly";
  const day = SCHEDULE_DAYS[settings.weekday] || SCHEDULE_DAYS[1];
  const time2 = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  const when = weekly ? `chaque ${day.label} à ${time2}` : `chaque jour à ${time2}`;

  const lin = schedulerPathsFor("linux");
  const cronCommand = `cd "${lin.workdir}" && "${lin.python}" "${lin.script}" tick >> "${lin.log}" 2>&1`;
  const win = schedulerPathsFor("windows");
  const winTask = `/TR "\\"${win.python}\\" \\"${win.script}\\" tick"`;

  return {
    when,
    linux: [
      `# Sauvegarde ${when}`,
      `${minute} ${hour} * * ${weekly ? day.cron : "*"} ${cronCommand}`,
      `# Rattrapage si le serveur était éteint à l'heure prévue (2 min après le démarrage)`,
      `@reboot sleep 120 && ${cronCommand}`
    ].join("\n"),
    windows: [
      `schtasks /Create /F /TN "AQuai Sauvegarde" /SC ${weekly ? `WEEKLY /D ${day.win}` : "DAILY"} /ST ${time2} ${winTask}`,
      `schtasks /Create /F /TN "AQuai Sauvegarde (rattrapage)" /SC ONSTART /DELAY 0002:00 ${winTask}`
    ].join("\n"),
    alt: [
      `# Linux`,
      `*/15 * * * * ${cronCommand}`,
      `# Windows`,
      `schtasks /Create /F /TN "AQuai Sauvegarde" /SC MINUTE /MO 15 ${winTask}`
    ].join("\n"),
    test: schedulerPaths.platform === "windows"
      ? `"${win.python}" "${win.script}" status`
      : `"${lin.python}" "${lin.script}" status`
  };
}

function renderSchedulerCommands() {
  if (!schedulerPaths || !scheduleEl("cmdLinux")) return;
  const commands = buildSchedulerCommands({
    frequency: scheduleEl("schedFrequency").value,
    weekday: Number(scheduleEl("schedWeekday").value),
    time: scheduleEl("schedTime").value || "02:00"
  });
  const serverIsWindows = schedulerPaths.platform === "windows";
  scheduleEl("labelLinux").textContent = serverIsWindows ? "— chemins d'exemple à adapter : ce serveur tourne sous Windows" : "— chemins de ce serveur";
  scheduleEl("labelWindows").textContent = serverIsWindows ? "— chemins de ce serveur" : "— chemins d'exemple à adapter : ce serveur tourne sous Linux";
  scheduleEl("schedulerSummary").innerHTML = scheduleEl("schedEnabled").checked
    ? `Sauvegarde <strong>${escapeHtml(commands.when)}</strong>. Le planificateur du système lance le script à cette heure ; le script vérifie les réglages, envoie la sauvegarde et purge les anciennes. À faire une seule fois :`
    : "La sauvegarde automatique est <strong>désactivée</strong> : activez-la ci-dessus pour que ces commandes prennent effet. À faire une seule fois :";
  scheduleEl("cmdLinux").textContent = commands.linux;
  scheduleEl("cmdWindows").textContent = commands.windows;
  scheduleEl("cmdAlt").textContent = commands.alt;
  scheduleEl("cmdTest").textContent = commands.test;
  scheduleEl("schedulerDirty").classList.toggle("d-none", scheduleSignature() === savedScheduleSignature);
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

  schedulerPaths = view.scheduler;
  savedScheduleSignature = scheduleSignature();
  renderSchedulerCommands();
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
  ["schedEnabled", "schedFrequency", "schedWeekday", "schedTime"].forEach((id) => {
    scheduleEl(id).addEventListener("input", renderSchedulerCommands);
    scheduleEl(id).addEventListener("change", renderSchedulerCommands);
  });
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(scheduleEl(button.dataset.copyTarget).textContent);
        button.textContent = "Copié";
      } catch (error) {
        button.textContent = "Sélectionnez et copiez";
      }
      window.setTimeout(() => { button.textContent = "Copier"; }, 2000);
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = scheduleEl("schedSaveBtn");
    button.disabled = true;
    const timingChanged = savedScheduleSignature !== scheduleSignature();
    try {
      await saveSchedule();
      showDbResult("schedResult", "ok", "Planification enregistrée.",
        timingChanged ? "Si la fréquence ou l'heure a changé, mettez à jour la tâche du serveur avec les commandes ci-dessous (section « Activer l'exécution automatique »)." : "");
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
