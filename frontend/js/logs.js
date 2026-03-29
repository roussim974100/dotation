async function logsRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
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

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("fr-FR");
}

function formatLogDetails(details) {
  if (!details || typeof details !== "object" || Object.keys(details).length === 0) {
    return "-";
  }
  const labels = {
    poste: "Poste",
    ip: "IP",
    ip_vue_serveur: "IP WAN",
    ip_reelle_proxy: "IP WAN proxy",
    ip_locale: "IP LAN",
    reseau_local: "Réseau local",
    navigateur: "Navigateur",
    plateforme: "Plateforme",
    user_agent: "User-Agent",
    langue: "Langue",
    langues: "Langues",
    fuseau_horaire: "Fuseau horaire",
    ecran: "Écran",
    fenetre: "Fenêtre",
    cookies_actifs: "Cookies actifs",
    page_connexion: "Page",
    etat_authentification: "Résultat",
    identifiant_tente: "Identifiant tenté",
    methode: "Méthode",
    chemin: "Chemin",
    hote: "Hôte",
    ip_distante_socket: "IP socket",
    ip_proxy_reelle: "IP proxy réelle",
    ip_wan_proxy: "IP WAN proxy",
    chaine_proxy: "Chaîne proxy",
    origine: "Origin",
    referer: "Referer",
    accept_language: "Accept-Language"
  };
  return Object.entries(details)
    .map(([key, value]) => `${labels[key] || key}: ${Array.isArray(value) ? value.join(", ") : String(value ?? "")}`)
    .join(" | ");
}

function normalizeLogLabel(value) {
  const label = String(value || "").trim();
  const legacyMap = {
    "Connexion reussie": "Connexion réussie",
    "Deconnexion": "Déconnexion"
  };
  return legacyMap[label] || label || "-";
}

async function loadLogs() {
  const search = document.getElementById("logSearchInput")?.value.trim() || "";
  const limit = document.getElementById("logLimitSelect")?.value || "200";
  const params = new URLSearchParams({ limit });
  if (search) {
    params.set("q", search);
  }

  const logs = await logsRequest(`/api/admin/logs?${params.toString()}`);
  const tbody = document.getElementById("logTableBody");
  const emptyState = document.getElementById("logsEmptyState");
  const logCount = document.getElementById("logCount");

  if (logCount) {
    logCount.textContent = String(logs.length);
  }

  if (!logs.length) {
    tbody.innerHTML = "";
    emptyState?.classList.remove("d-none");
    return;
  }

  emptyState?.classList.add("d-none");
  tbody.innerHTML = logs.map((log) => `
    <tr class="draft-row">
      <td data-label="Date">${escapeHtml(formatDateTime(log.created_at))}</td>
      <td data-label="Acteur">${escapeHtml(log.actor || "system")}</td>
      <td data-label="Périmètre">${escapeHtml(log.scope || "-")}</td>
      <td data-label="Action">${escapeHtml(normalizeLogLabel(log.action_label || log.action_type || "-"))}</td>
      <td data-label="Cible">${escapeHtml([log.target_type, log.target_id].filter(Boolean).join(" / ") || "-")}</td>
      <td data-label="Détail">${escapeHtml(formatLogDetails(log.details))}</td>
    </tr>
  `).join("");
}

let searchTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadLogs();
  } catch (error) {
    alert(`Impossible de charger le journal : ${error.message}`);
  }

  document.getElementById("refreshLogsBtn")?.addEventListener("click", async () => {
    try {
      await loadLogs();
    } catch (error) {
      alert(`Impossible de rafraîchir le journal : ${error.message}`);
    }
  });

  document.getElementById("logLimitSelect")?.addEventListener("change", async () => {
    try {
      await loadLogs();
    } catch (error) {
      alert(`Impossible de charger le journal : ${error.message}`);
    }
  });

  document.getElementById("logResetBtn")?.addEventListener("click", async () => {
    document.getElementById("logSearchInput").value = "";
    document.getElementById("logLimitSelect").value = "200";
    try {
      await loadLogs();
    } catch (error) {
      alert(`Impossible de réinitialiser le journal : ${error.message}`);
    }
  });

  document.getElementById("logSearchInput")?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(async () => {
      try {
        await loadLogs();
      } catch (error) {
        alert(`Impossible de filtrer le journal : ${error.message}`);
      }
    }, 250);
  });
});
// Gère l'écran de journal d'activité :
// chargement, filtrage et rendu lisible des événements.
