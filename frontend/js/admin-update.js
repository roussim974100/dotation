// Administration : nouvelle version disponible et mise à jour depuis le navigateur.
// Le serveur ne lance aucune commande : il dépose une demande qu'une unité systemd exécute (voir setup/install-web-update.sh).
// Sans cette unité, le bandeau indique simplement la commande à lancer sur le serveur.

// États de la dernière mise à jour lancée (écrits par deploy.sh) : défini en objet, ajouter un état = ajouter une entrée.
const UPDATE_PROGRESS = {
  running: { tone: "warning", title: "Mise à jour en cours" },
  ok: { tone: "success", title: "Mise à jour terminée" },
  failed: { tone: "danger", title: "La mise à jour a échoué" },
  rolled_back: { tone: "danger", title: "La mise à jour a échoué : l'ancienne version a été rétablie" }
};
const UPDATE_ERRORS = {
  wrong_password: "Mot de passe incorrect.",
  update_disabled: "La mise à jour depuis le navigateur n'est pas activée sur ce serveur.",
  already_running: "Une mise à jour est déjà en cours.",
  no_update: "Aucune nouvelle version n'est disponible.",
  rate_limit_exceeded: "Trop de tentatives : patientez quelques minutes."
};
const UPDATE_DISMISS_KEY = "updateDismissedAt";
const UPDATE_POLL_MS = 3000;
const UPDATE_POLL_MAX_MS = 6 * 60 * 1000;

let updatePollTimer = null;
let updatePollStartedAt = 0;
let updateState = null;

function updEl(id) { return document.getElementById(id); }
function updEsc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
async function updCsrf() { return (await (await fetch("/api/csrf-token", { credentials: "same-origin" })).json()).token; }

function updateCommandHint(state) {
  return state.channel === "dev" ? "sudo bash deploy-dev.sh" : "sudo bash deploy.sh";
}

function updateDismissed(progress) {
  try {
    return Number(window.localStorage.getItem(UPDATE_DISMISS_KEY) || 0) >= Number(progress.finished_at || 0);
  } catch (error) {
    return false;
  }
}

function updateBannerHtml(state) {
  const progress = state.progress || {};
  const meta = UPDATE_PROGRESS[progress.state];
  if (meta && progress.state === "running") {
    return { tone: meta.tone, html: `<strong>${meta.title}</strong> — ${updEsc(progress.message || "préparation…")}
      ${progress.step ? `<span class="text-muted">(étape ${updEsc(progress.step)})</span>` : ""}<br>
      <span class="small">L'application va redémarrer quelques secondes : ne fermez pas cette page.</span>` };
  }
  if (meta && !updateDismissed(progress) && (Date.now() / 1000 - Number(progress.finished_at || 0)) < 24 * 3600) {
    const failed = progress.state === "failed" || progress.state === "rolled_back";
    return { tone: meta.tone, dismissible: true, html: `<strong>${meta.title}</strong>${progress.to ? ` (${updEsc(progress.from || "")} → ${updEsc(progress.to)})` : ""}
      ${progress.message ? `<br><span class="small">${updEsc(progress.message)}</span>` : ""}
      ${failed ? '<br><span class="small">Le détail est dans le journal de mise à jour du serveur (dossier <code>update/</code>).</span>' : ""}` };
  }
  if (state.available) {
    const action = state.can_update
      ? '<button class="btn btn-sm btn-primary" type="button" data-update-start="true">Mettre à jour maintenant</button>'
      : `<span class="small">Sur le serveur : <code>${updEsc(updateCommandHint(state))}</code></span>`;
    return { tone: "info", html: `<div class="d-flex flex-wrap align-items-center gap-3">
      <span><strong>Nouvelle version ${updEsc(state.latest)} disponible</strong> (vous utilisez ${updEsc(state.current)}).
        <a href="${updEsc(state.release_notes_url)}" target="_blank" rel="noopener">Notes de version</a></span>
      <span class="ms-auto">${action}</span></div>` };
  }
  return null;
}

function renderUpdate(state) {
  updateState = state;
  const banner = updEl("updateBanner");
  const info = updEl("updateInfo");
  if (!banner) return;
  const view = state.enabled === false && !(state.progress && state.progress.state) ? null : updateBannerHtml(state);
  banner.className = `alert alert-${view ? view.tone : "info"} ${view ? "" : "d-none"} mb-4`;
  banner.innerHTML = view ? `${view.html}${view.dismissible ? '<button type="button" class="btn-close float-end" data-update-dismiss="true" aria-label="Fermer"></button>' : ""}` : "";
  if (info) {
    const checked = state.checked_at ? new Date(state.checked_at * 1000).toLocaleString("fr-FR") : null;
    info.innerHTML = `Version installée <strong>${updEsc(state.current || "?")}</strong>
      ${state.enabled === false ? "· vérification des mises à jour désactivée" : state.error && !state.latest ? "· vérification impossible (pas d'accès à GitHub ?)" : state.available ? "" : "· à jour"}
      ${checked ? `<span class="text-muted">(vérifié le ${updEsc(checked)})</span>` : ""}
      ${state.enabled === false ? "" : '<button class="btn btn-link btn-sm p-0 ms-2" type="button" data-update-check="true">Vérifier maintenant</button>'}`;
  }
  if (state.progress && state.progress.state === "running") startUpdatePolling(); else stopUpdatePolling();
}

async function loadUpdateStatus(force = false) {
  const options = force ? { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": await updCsrf() }, body: "{}" }
    : { credentials: "same-origin", cache: "no-store" };
  const response = await fetch(force ? "/api/admin/update/check" : "/api/admin/update/status", options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  renderUpdate(await response.json());
}

function startUpdatePolling() {
  if (updatePollTimer) return;
  updatePollStartedAt = Date.now();
  updatePollTimer = window.setInterval(async () => {
    if (Date.now() - updatePollStartedAt > UPDATE_POLL_MAX_MS) return stopUpdatePolling();
    try {
      const before = updateState?.current;
      await loadUpdateStatus(false);
      if (updateState.progress?.state === "ok" && updateState.current !== before) {
        stopUpdatePolling();
        window.setTimeout(() => window.location.reload(), 1500);
      }
    } catch (error) {
      const banner = updEl("updateBanner");
      if (banner) { banner.className = "alert alert-warning mb-4"; banner.innerHTML = "<strong>Mise à jour en cours</strong> — redémarrage du service, un instant…"; }
    }
  }, UPDATE_POLL_MS);
}

function stopUpdatePolling() {
  if (updatePollTimer) { window.clearInterval(updatePollTimer); updatePollTimer = null; }
}

function openUpdateModal() {
  const modal = updEl("updateModal");
  updEl("updatePassword").value = "";
  updEl("updateError").classList.add("d-none");
  updEl("updateModalText").innerHTML = `Passer de <strong>${updEsc(updateState.current)}</strong> à <strong>${updEsc(updateState.latest)}</strong>.
    Une sauvegarde des bases est faite avant, et l'ancienne version est <strong>rétablie automatiquement</strong> si la nouvelle ne démarre pas.
    L'application sera indisponible quelques secondes.`;
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  updEl("updatePassword").focus();
}

function closeUpdateModal() {
  const modal = updEl("updateModal");
  modal.classList.add("d-none");
  modal.setAttribute("aria-hidden", "true");
}

async function submitUpdate() {
  const error = updEl("updateError");
  const password = updEl("updatePassword").value;
  if (!password) { error.textContent = "Saisissez votre mot de passe pour confirmer."; error.classList.remove("d-none"); return; }
  const button = updEl("updateConfirm");
  button.disabled = true;
  try {
    const response = await fetch("/api/admin/update/start", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await updCsrf() }, body: JSON.stringify({ password })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      error.textContent = UPDATE_ERRORS[data.error] || data.message || `Erreur ${response.status}`;
      error.classList.remove("d-none");
      return;
    }
    closeUpdateModal();
    renderUpdate({ ...updateState, progress: { state: "running", message: "demande envoyée, démarrage…" } });
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!updEl("updateBanner")) return;
  loadUpdateStatus(false).catch(() => {});
  document.addEventListener("click", async (event) => {
    if (event.target.closest("[data-update-start]")) return openUpdateModal();
    if (event.target.closest("[data-update-cancel]")) return closeUpdateModal();
    if (event.target.closest("[data-update-confirm]")) return submitUpdate();
    if (event.target.closest("[data-update-check]")) { try { await loadUpdateStatus(true); } catch (error) { /* silencieux */ } return; }
    if (event.target.closest("[data-update-dismiss]")) {
      try { window.localStorage.setItem(UPDATE_DISMISS_KEY, String(Date.now() / 1000)); } catch (error) { /* stockage indisponible */ }
      renderUpdate(updateState);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeUpdateModal();
    if (event.key === "Enter" && event.target.id === "updatePassword") submitUpdate();
  });
});
