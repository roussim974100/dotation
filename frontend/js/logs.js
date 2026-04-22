let logsCurrentOffset = 0;
let searchTimer = null;

async function logsRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options
  });
  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = null; }
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("fr-FR");
}

function formatLogDetails(details) {
  if (!details || typeof details !== "object" || Object.keys(details).length === 0) return "-";
  const labels = {
    poste: "Poste", ip: "IP", ip_vue_serveur: "IP WAN", ip_reelle_proxy: "IP WAN proxy",
    ip_locale: "IP LAN", reseau_local: "Réseau local", navigateur: "Navigateur",
    plateforme: "Plateforme", user_agent: "User-Agent", langue: "Langue", langues: "Langues",
    fuseau_horaire: "Fuseau horaire", ecran: "Écran", fenetre: "Fenêtre",
    cookies_actifs: "Cookies actifs", page_connexion: "Page",
    etat_authentification: "Résultat", identifiant_tente: "Identifiant tenté",
    methode: "Méthode", chemin: "Chemin", hote: "Hôte",
    ip_distante_socket: "IP socket", ip_proxy_reelle: "IP proxy réelle",
    ip_wan_proxy: "IP WAN proxy", chaine_proxy: "Chaîne proxy",
    origine: "Origin", referer: "Referer", accept_language: "Accept-Language"
  };
  return Object.entries(details)
    .map(([k, v]) => `${labels[k] || k}: ${Array.isArray(v) ? v.join(", ") : String(v ?? "")}`)
    .join(" | ");
}

function formatLogTarget(log) {
  const type = log.target_type || "";
  const label = log.target_label || log.details?.title || log.details?.label || "";
  const id = log.target_id || "";
  if (!type && !id) return "-";
  if (label) {
    return `<span class="log-target__type">${escapeHtml(type)}</span><span class="log-target__label">${escapeHtml(label)}</span>`;
  }
  return escapeHtml([type, id].filter(Boolean).join(" · "));
}

function normalizeLogLabel(value) {
  const label = String(value || "").trim();
  const legacyMap = { "Connexion reussie": "Connexion réussie", "Deconnexion": "Déconnexion" };
  return legacyMap[label] || label || "-";
}

function renderPagination(total, limit, offset) {
  const container = document.getElementById("logsPagination");
  if (!container) return;

  const totalPages = Math.ceil(total / limit) || 1;
  const currentPage = Math.floor(offset / limit) + 1;

  if (totalPages <= 1) {
    container.classList.add("d-none");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("d-none");

  const maxButtons = 7;
  let pages = [];
  if (totalPages <= maxButtons) {
    pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  } else {
    pages = [1];
    let start = Math.max(2, currentPage - 2);
    let end = Math.min(totalPages - 1, currentPage + 2);
    if (start > 2) pages.push("…");
    for (let p = start; p <= end; p++) pages.push(p);
    if (end < totalPages - 1) pages.push("…");
    pages.push(totalPages);
  }

  const btn = (label, page, disabled, active) =>
    `<button class="logs-pagination__btn${active ? " is-active" : ""}"
      ${disabled ? "disabled" : `data-page="${page}"`}
      aria-label="Page ${label}" ${active ? 'aria-current="page"' : ""}>
      ${escapeHtml(String(label))}
    </button>`;

  container.innerHTML = `
    <div class="logs-pagination__info">
      Page ${currentPage} / ${totalPages} &nbsp;·&nbsp; ${total} entrée${total > 1 ? "s" : ""}
    </div>
    <div class="logs-pagination__controls">
      ${btn("←", currentPage - 1, currentPage === 1, false)}
      ${pages.map(p => p === "…"
        ? `<span class="logs-pagination__ellipsis">…</span>`
        : btn(p, p, false, p === currentPage)
      ).join("")}
      ${btn("→", currentPage + 1, currentPage === totalPages, false)}
    </div>
  `;

  container.querySelectorAll("[data-page]").forEach(el => {
    el.addEventListener("click", async () => {
      const page = Number(el.dataset.page);
      logsCurrentOffset = (page - 1) * limit;
      try { await loadLogs(); } catch (e) { alert(`Erreur : ${e.message}`); }
    });
  });
}

async function loadLogs(resetPage = false) {
  if (resetPage) logsCurrentOffset = 0;
  const search = document.getElementById("logSearchInput")?.value.trim() || "";
  const limit = Number(document.getElementById("logLimitSelect")?.value || "100");
  const params = new URLSearchParams({ limit, offset: logsCurrentOffset });
  if (search) params.set("q", search);

  const data = await logsRequest(`/api/admin/logs?${params.toString()}`);
  const { items, total } = data;

  const tbody = document.getElementById("logTableBody");
  const emptyState = document.getElementById("logsEmptyState");
  const logCount = document.getElementById("logCount");

  if (logCount) logCount.textContent = String(total);

  if (!items.length) {
    tbody.innerHTML = "";
    emptyState?.classList.remove("d-none");
    renderPagination(0, limit, logsCurrentOffset);
    return;
  }

  emptyState?.classList.add("d-none");
  tbody.innerHTML = items.map(log => `
    <tr class="draft-row">
      <td data-label="Date">${escapeHtml(formatDateTime(log.created_at))}</td>
      <td data-label="Acteur">${escapeHtml(log.actor || "system")}</td>
      <td data-label="Périmètre">${escapeHtml(log.scope || "-")}</td>
      <td data-label="Action">${escapeHtml(normalizeLogLabel(log.action_label || log.action_type || "-"))}</td>
      <td data-label="Cible">${formatLogTarget(log)}</td>
      <td data-label="Détail">${escapeHtml(formatLogDetails(log.details))}</td>
    </tr>
  `).join("");

  renderPagination(total, limit, logsCurrentOffset);
}

document.addEventListener("DOMContentLoaded", async () => {
  try { await loadLogs(); } catch (e) { alert(`Impossible de charger le journal : ${e.message}`); }

  document.getElementById("refreshLogsBtn")?.addEventListener("click", async () => {
    try { await loadLogs(); } catch (e) { alert(`Impossible de rafraîchir le journal : ${e.message}`); }
  });

  document.getElementById("logLimitSelect")?.addEventListener("change", async () => {
    try { await loadLogs(true); } catch (e) { alert(`Erreur : ${e.message}`); }
  });

  document.getElementById("logResetBtn")?.addEventListener("click", async () => {
    document.getElementById("logSearchInput").value = "";
    document.getElementById("logLimitSelect").value = "100";
    try { await loadLogs(true); } catch (e) { alert(`Erreur : ${e.message}`); }
  });

  document.getElementById("logSearchInput")?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(async () => {
      try { await loadLogs(true); } catch (e) { alert(`Erreur : ${e.message}`); }
    }, 250);
  });
});
