const STATUS_LABELS = {
  draft: "À compléter", active: "Actif",
  partial_assignment: "Attribution partielle",
  awaiting_signature: "En attente de signature",
  returned: "Restitué", partial_return: "Restitution partielle",
  cancelled: "Annulé"
};

const TYPE_LABELS = {
  arrivee: "Arrivée", changement_service: "Changement de service",
  mise_a_jour: "Mise à jour", sortie: "Sortie"
};

const STATUS_COLORS = {
  draft:               "#FBBF24",
  active:              "#22C55E",
  partial_assignment:  "#F97316",
  awaiting_signature:  "#3B82F6",
  returned:            "#6366F1",
  partial_return:      "#A855F7",
  cancelled:           "#EF4444"
};

const STATUS_TEXT_COLORS = {
  draft:               "#92400E",
  active:              "#14532D",
  partial_assignment:  "#7C2D12",
  awaiting_signature:  "#1E3A5F",
  returned:            "#312E81",
  partial_return:      "#581C87",
  cancelled:           "#7F1D1D"
};

let filters = { period: "30d", service: "", type: "", statut: "", qualite: "", date_from: "", date_to: "", alerte_seuil: "30" };
let charts = {};
let allData = null;

async function init() {
  const session = await fetch("/api/session").then(r => r.ok ? r.json() : null);
  if (!session) {
    window.location.href = "/login";
    return;
  }

  updateUserMenu(session);
  await loadServiceOptions();
  bindFilterListeners();
  await loadStats();
}

function updateUserMenu(session) {
  const name = document.getElementById("userMenuName");
  const role = document.getElementById("userMenuRole");
  if (name) name.textContent = session.username || "";
  if (role) role.textContent = session.is_admin ? "Administrateur" : (session.groups || []).join(", ");
}

async function loadServiceOptions() {
  try {
    const services = await fetch("/api/reference/services").then(r => r.json());
    const select = document.getElementById("filterService");
    if (select) {
      services.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.label;
        opt.textContent = s.label;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("Erreur chargement services:", e);
  }
}

function bindFilterListeners() {
  document.querySelectorAll('[name="filter-period"]').forEach(radio => {
    radio.addEventListener("change", e => {
      filters.period = e.target.value;
      const customWrap = document.getElementById("filterCustomDateWrap");
      if (customWrap) customWrap.classList.toggle("d-none", filters.period !== "custom");
      if (filters.period !== "custom") {
        filters.date_from = "";
        filters.date_to = "";
      }
      loadStats();
    });
  });

  document.getElementById("filterDateFrom")?.addEventListener("change", e => {
    filters.date_from = e.target.value;
    loadStats();
  });

  document.getElementById("filterDateTo")?.addEventListener("change", e => {
    filters.date_to = e.target.value;
    loadStats();
  });

  document.getElementById("filterService")?.addEventListener("change", e => {
    filters.service = e.target.value;
    loadStats();
  });

  document.querySelectorAll('[name="filter-type"]').forEach(radio => {
    radio.addEventListener("change", e => {
      filters.type = e.target.value;
      loadStats();
    });
  });

  document.getElementById("filterStatut")?.addEventListener("change", e => {
    filters.statut = e.target.value;
    loadStats();
  });

  document.querySelectorAll('[name="filter-qualite"]').forEach(radio => {
    radio.addEventListener("change", e => {
      filters.qualite = e.target.value;
      loadStats();
    });
  });

  const seuilInput = document.getElementById("filterAlerteSeuil");
  const seuilLabel = document.getElementById("filterAlerteSeuilLabel");
  if (seuilInput) {
    seuilInput.addEventListener("input", () => {
      if (seuilLabel) seuilLabel.textContent = `${seuilInput.value} j`;
    });
    seuilInput.addEventListener("change", () => {
      filters.alerte_seuil = seuilInput.value;
      loadStats();
    });
  }
}

async function loadStats() {
  try {
    const params = new URLSearchParams(filters);
    const response = await fetch(`/api/admin/dashboard-stats?${params}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(errorData.error || `HTTP ${response.status}`);
    }
    const data = await response.json();
    allData = data;

    renderKpis(data.kpis);
    renderCharts(data);
    renderAlertes(data.alertes, data.kpis.alerte_seuil);
    renderServicesTable(data.by_service);
  } catch (error) {
    console.error("Erreur chargement stats:", error);
    showError("Impossible de charger les données : " + error.message);
  }
}

function renderKpis(kpis) {
  const byId = (id) => document.getElementById(id);
  if (byId("kpiTotal")) byId("kpiTotal").textContent = kpis.total || 0;
  if (byId("kpiActifs")) byId("kpiActifs").textContent = kpis.actifs || 0;
  if (byId("kpiRestitution")) byId("kpiRestitution").textContent = `${kpis.taux_restitution || 0}%`;
  if (byId("kpiAlertes")) byId("kpiAlertes").textContent = kpis.alertes_blocage || 0;

  // Timing KPIs
  if (byId("kpiAvgTreatment")) {
    const val = kpis.avg_treatment !== null && kpis.avg_treatment !== undefined ? parseFloat(kpis.avg_treatment).toFixed(1) : "—";
    byId("kpiAvgTreatment").textContent = val;
  }
  if (byId("kpiAvgRestitution")) {
    const val = kpis.avg_restitution !== null && kpis.avg_restitution !== undefined ? parseFloat(kpis.avg_restitution).toFixed(1) : "—";
    byId("kpiAvgRestitution").textContent = val;
  }
  if (byId("kpiPctFast")) {
    const val = kpis.pct_fast !== null && kpis.pct_fast !== undefined ? `${parseFloat(kpis.pct_fast).toFixed(0)}%` : "—";
    byId("kpiPctFast").textContent = val;
  }
}

function renderCharts(data) {
  if (!data.by_status || !data.by_service || !data.tendance || !data.by_resource) return;

  renderStatusChart(data.by_status);
  renderServicesChart(data.by_service);
  renderTendanceChart(data.tendance);
  renderResourcesChart(data.by_resource);
  if (data.timing_distribution) {
    renderTimingChart(data.timing_distribution);
  }
}

function renderStatusChart(by_status) {
  const ctx = document.getElementById("chartStatus");
  if (!ctx) return;

  if (charts.status) charts.status.destroy();

  const labels = by_status.map(s => s.label);
  const counts = by_status.map(s => s.count);
  const bgColors = by_status.map(s => STATUS_COLORS[s.status] || "#dfe8ee");
  const textColors = by_status.map(s => STATUS_TEXT_COLORS[s.status] || "#333");

  charts.status = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: counts,
        backgroundColor: bgColors,
        borderColor: "#ffffff",
        borderWidth: 3,
        hoverOffset: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            padding: 16,
            boxWidth: 14,
            font: { size: 12 }
          }
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label} : ${ctx.parsed}`
          }
        }
      }
    }
  });
}

function renderServicesChart(by_service) {
  const ctx = document.getElementById("chartServices");
  if (!ctx) return;

  if (charts.services) charts.services.destroy();

  const labels = by_service.slice(0, 10).map(s => s.service);
  const counts = by_service.slice(0, 10).map(s => s.count);

  charts.services = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Dossiers",
        data: counts,
        backgroundColor: "#97d8ae",
        borderColor: "#0a4d28",
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true } }
    }
  });
}

function renderTendanceChart(tendance) {
  const ctx = document.getElementById("chartTendance");
  if (!ctx) return;

  if (charts.tendance) charts.tendance.destroy();

  const labels = tendance.map(t => t.label);
  const counts = tendance.map(t => t.count);

  charts.tendance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "Dossiers créés",
        data: counts,
        borderColor: "#18436d",
        backgroundColor: "rgba(24, 67, 109, 0.1)",
        borderWidth: 2,
        fill: true,
        tension: 0.3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } }
    }
  });
}

function renderResourcesChart(by_resource) {
  const ctx = document.getElementById("chartResources");
  if (!ctx) return;

  if (charts.resources) charts.resources.destroy();

  const labels = by_resource.slice(0, 10).map(r => r.label);
  const counts = by_resource.slice(0, 10).map(r => r.count);

  charts.resources = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Attribuées",
        data: counts,
        backgroundColor: "#f1d48b",
        borderColor: "#694b00",
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true } }
    }
  });
}

function renderTimingChart(timing_distribution) {
  const ctx = document.getElementById("chartTiming");
  if (!ctx) return;

  if (charts.timing) charts.timing.destroy();

  const labels = timing_distribution.map(t => t.label);
  const counts = timing_distribution.map(t => t.count);
  const bgColors = timing_distribution.map(t => t.color);

  charts.timing = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [{
        data: counts,
        backgroundColor: bgColors,
        borderColor: "#fff",
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" }
      }
    }
  });
}

function renderAlertes(alertes, seuil) {
  const container = document.getElementById("alertesContainer");
  const title = document.getElementById("alertesSectionTitle");
  if (title) title.textContent = `Dossiers bloqués (> ${seuil || 30} jours)`;
  if (!container) return;

  if (!alertes || alertes.length === 0) {
    container.innerHTML = "<p class=\"text-muted\">Aucune alerte — tous les dossiers sont à jour.</p>";
    return;
  }

  const rows = alertes.map(a => `
    <tr>
      <td><strong>${a.nom} ${a.prenom}</strong></td>
      <td>${a.service}</td>
      <td><span class="badge bg-danger">${a.jours_blocage} j</span></td>
      <td>${STATUS_LABELS[a.status] || a.status}</td>
      <td class="text-end">
        <a href="form.html?id=${encodeURIComponent(a.id)}" class="btn btn-sm btn-primary">Ouvrir</a>
      </td>
    </tr>
  `).join("");

  container.innerHTML = `
    <table class="table align-middle draft-table">
      <thead>
        <tr>
          <th>Nom</th>
          <th>Service</th>
          <th>Jours bloqués</th>
          <th>Statut</th>
          <th class="text-end">Actions</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
}

function renderServicesTable(by_service) {
  const container = document.getElementById("servicesContainer");
  if (!container || !by_service) return;

  const rows = by_service.slice(0, 20).map(s => `
    <tr style="cursor:pointer" onclick="window.location.href='/index.html?service=${encodeURIComponent(s.service)}'">
      <td><strong>${s.service}</strong></td>
      <td>${s.count}</td>
    </tr>
  `).join("");

  container.innerHTML = `
    <table class="table align-middle draft-table">
      <thead>
        <tr>
          <th>Service</th>
          <th>Dossiers</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
}

function showError(message) {
  console.error(message);
  const container = document.getElementById("alertesContainer");
  if (container) container.innerHTML = `<p class="text-danger">${message}</p>`;
}

// Initialiser au chargement
document.addEventListener("DOMContentLoaded", init);
