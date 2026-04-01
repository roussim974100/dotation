// Alimente le portail d'administration avec ses indicateurs
// et affiche les messages flash issus des sous-pages admin.
const ADMIN_FLASH_NOTICE_KEY = "adminFlashNotice";

async function fetchAdminJson(url) {
  const response = await fetch(url, {
    credentials: "same-origin"
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

function setMetric(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = String(value);
  }
}

function showAdminFlashNotice() {
  const notice = document.getElementById("adminFlashNotice");
  if (!notice) {
    return;
  }
  try {
    const message = sessionStorage.getItem(ADMIN_FLASH_NOTICE_KEY);
    if (!message) {
      return;
    }
    notice.textContent = message;
    notice.classList.remove("d-none");
    sessionStorage.removeItem(ADMIN_FLASH_NOTICE_KEY);
  } catch (error) {
    // Rien de bloquant.
  }
}

async function loadUncStats() {
  const STATUT_CLASS = { "Demandé": "text-warning", "En cours": "text-primary", "Provisionné": "text-success" };
  try {
    const data = await fetchAdminJson("/api/admin/unc-stats");
    setMetric("uncStatDemande", data.counts.demande ?? 0);
    setMetric("uncStatEnCours", data.counts.en_cours ?? 0);
    setMetric("uncStatProvisionne", data.counts.provisionne ?? 0);
    setMetric("uncStatAgents", data.agents ?? 0);
    const tbody = document.getElementById("uncDashboardBody");
    const toggle = document.getElementById("uncDashboardToggle");
    if (!tbody || !toggle || !data.detail.length) return;
    toggle.classList.remove("d-none");
    data.detail.forEach(e => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${e.prenom} ${e.nom}</td><td>${e.service}</td><td><code>${e.chemin}</code></td><td>${e.acces}</td><td class="${STATUT_CLASS[e.statut] || ""}">${e.statut}</td><td>${e.commentaire}</td>`;
      tbody.appendChild(tr);
    });
    toggle.addEventListener("click", () => {
      const list = document.getElementById("uncDashboardList");
      const hidden = list.classList.toggle("d-none");
      toggle.textContent = hidden ? "Afficher le détail" : "Masquer le détail";
    });
  } catch (e) {
    console.error(e);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  showAdminFlashNotice();
  try {
    const [users, services, resources] = await Promise.all([
      fetchAdminJson("/api/admin/users"),
      fetchAdminJson("/api/admin/services"),
      fetchAdminJson("/api/admin/resources")
    ]);
    setMetric("adminUsersCount", users.length);
    setMetric("adminPendingCount", users.filter((user) => user.status === "pending").length);
    setMetric("adminServicesCount", services.filter((service) => service.is_active).length);
    setMetric("adminResourcesCount", resources.filter((resource) => resource.is_active).length);
  } catch (error) {
    console.error(error);
  }
  await loadUncStats();
});
