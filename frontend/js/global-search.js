// Recherche globale : command palette déclenchée par Ctrl+K / Cmd+K.
// Injecte une modale et un bouton trigger dans .header-actions sur toutes les
// pages authentifiées qui chargent ce script. Utilise GET /api/forms?search=X
// (endpoint existant, LIKE SQL sur nom/prenom/title).

(function () {
  const MODAL_ID = "globalSearchModal";
  const INPUT_ID = "globalSearchInput";
  const RESULTS_ID = "globalSearchResults";
  const TRIGGER_ID = "globalSearchTrigger";
  const MAX_RESULTS = 15;
  const DEBOUNCE_MS = 200;
  const MIN_QUERY_LENGTH = 2;

  const STATUS_LABELS = {
    draft: "Brouillon",
    partial_assignment: "Attribution partielle",
    awaiting_signature: "En attente de signature",
    active: "Actif",
    returned: "Restitué",
    partial_return: "Restitution partielle",
    cancelled: "Annulé",
  };

  const FILTER_CONFIG = {
    active: { status: true, timing: true, qualite: true, service: true, sort: true },
    history_assignments: { status: true, timing: true, qualite: true, service: true, sort: true },
    restitutions_pending: { status: true, timing: true, qualite: true, service: true, sort: true },
    history_restitutions: { status: true, timing: true, qualite: true, service: true, sort: true },
  };

  const FILTER_OPTIONS = {
    status: [
      { label: "À compléter", value: "draft" },
      { label: "Attribution partielle", value: "partial_assignment" },
      { label: "En attente de signature", value: "awaiting_signature" },
      { label: "Attribution active", value: "active" },
      { label: "Restitution partielle", value: "partial_return" },
      { label: "Restitué", value: "returned" },
      { label: "Annulé", value: "cancelled" },
    ],
    timing: [
      { label: "Prêt / Dans les temps", value: "ok" },
      { label: "En danger", value: "warning" },
      { label: "En retard", value: "late" },
      { label: "À planifier", value: "neutral" },
    ],
    qualite: [
      { label: "Agent", value: "agent" },
      { label: "Élu(e)", value: "elu" },
    ],
  };

  let debounceTimer = null;
  let currentResults = [];
  let activeIndex = -1;
  let lastQuery = "";

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  function buildModal() {
    if (document.getElementById(MODAL_ID)) return;
    const modal = document.createElement("div");
    modal.id = MODAL_ID;
    modal.className = "global-search d-none";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-label", "Recherche et filtres");
    modal.innerHTML = `
      <div class="global-search__backdrop" data-gs-close></div>
      <div class="global-search__panel" role="document">
        <div class="global-search__header">
          <span class="global-search__icon" aria-hidden="true">🔍</span>
          <input id="${INPUT_ID}" type="search" class="global-search__input"
                 placeholder="Rechercher un dossier par nom, prénom, service…"
                 autocomplete="off" spellcheck="false"
                 aria-controls="${RESULTS_ID}" aria-autocomplete="list">
          <kbd class="global-search__esc">Esc</kbd>
        </div>
        <div id="globalSearchFilters" class="global-search__filters"></div>
        <ul id="${RESULTS_ID}" class="global-search__results" role="listbox"></ul>
        <div class="global-search__footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> naviguer</span>
          <span><kbd>Entrée</kbd> ouvrir</span>
          <span><kbd>Esc</kbd> fermer</span>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.addEventListener("mousedown", (event) => {
      const panel = modal.querySelector(".global-search__panel");
      if (panel && !panel.contains(event.target)) {
        closeModal();
      }
    });

    const input = document.getElementById(INPUT_ID);
    input.addEventListener("input", onInput);
    input.addEventListener("keydown", onInputKeyDown);
  }

  function buildTriggerButton() {
    const actions = document.querySelector(".app-header .header-actions");
    if (!actions || document.getElementById(TRIGGER_ID)) return;
    const btn = document.createElement("button");
    btn.id = TRIGGER_ID;
    btn.type = "button";
    btn.className = "btn btn-outline-light global-search__trigger";
    btn.setAttribute("title", "Rechercher un dossier (Ctrl+K)");
    btn.setAttribute("aria-label", "Ouvrir la recherche globale");
    btn.innerHTML = `
      <span class="global-search__trigger-icon" aria-hidden="true">🔍</span>
      <span class="global-search__trigger-label">Rechercher</span>
      <kbd class="global-search__trigger-kbd" aria-hidden="true">Ctrl+K</kbd>
    `;
    btn.addEventListener("click", openModal);
    actions.insertBefore(btn, actions.firstChild);
  }

  function getCurrentView() {
    const body = document.querySelector("body[data-dashboard-view]");
    return body ? body.dataset.dashboardView : null;
  }

  function getActiveFilters() {
    const filters = {};
    const statusFilter = document.getElementById("statusFilter");
    const timingFilter = document.getElementById("timingFilter");
    const qualiteFilter = document.getElementById("qualiteFilter");
    const serviceFilter = document.getElementById("serviceFilter");
    const sortFilter = document.getElementById("sortFilter");

    if (statusFilter && statusFilter.value) filters.status = statusFilter.value;
    if (timingFilter && timingFilter.value) filters.timing = timingFilter.value;
    if (qualiteFilter && qualiteFilter.value) filters.qualite = qualiteFilter.value;
    if (serviceFilter && serviceFilter.value) filters.service = serviceFilter.value;
    if (sortFilter && sortFilter.value) filters.sort = sortFilter.value;

    return filters;
  }

  function renderQuickFilters() {
    const view = getCurrentView();
    const config = FILTER_CONFIG[view];
    if (!config) return;

    const filtersDiv = document.getElementById("globalSearchFilters");
    if (!filtersDiv) return;

    const activeFilters = getActiveFilters();
    let html = "";

    if (config.status) {
      html += '<div class="global-search__filter-group">';
      html += '<span class="global-search__filter-label">Avancement</span>';
      html += '<div class="global-search__filter-chips">';
      FILTER_OPTIONS.status.forEach((opt) => {
        const isActive = activeFilters.status === opt.value;
        const cls = isActive ? "is-active" : "";
        html += `<button type="button" class="global-search__filter-chip ${cls}" data-filter-type="status" data-filter-value="${escapeHtml(opt.value)}" title="${escapeHtml(opt.label)}">${escapeHtml(opt.label)}</button>`;
      });
      html += "</div></div>";
    }

    if (config.timing) {
      html += '<div class="global-search__filter-group">';
      html += '<span class="global-search__filter-label">Pilotage</span>';
      html += '<div class="global-search__filter-chips">';
      FILTER_OPTIONS.timing.forEach((opt) => {
        const isActive = activeFilters.timing === opt.value;
        const cls = isActive ? "is-active" : "";
        html += `<button type="button" class="global-search__filter-chip ${cls}" data-filter-type="timing" data-filter-value="${escapeHtml(opt.value)}" title="${escapeHtml(opt.label)}">${escapeHtml(opt.label)}</button>`;
      });
      html += "</div></div>";
    }

    if (config.qualite) {
      html += '<div class="global-search__filter-group">';
      html += '<span class="global-search__filter-label">Qualité</span>';
      html += '<div class="global-search__filter-chips">';
      FILTER_OPTIONS.qualite.forEach((opt) => {
        const isActive = activeFilters.qualite === opt.value;
        const cls = isActive ? "is-active" : "";
        html += `<button type="button" class="global-search__filter-chip ${cls}" data-filter-type="qualite" data-filter-value="${escapeHtml(opt.value)}" title="${escapeHtml(opt.label)}">${escapeHtml(opt.label)}</button>`;
      });
      html += "</div></div>";
    }

    filtersDiv.innerHTML = html;
    filtersDiv.querySelectorAll(".global-search__filter-chip").forEach((btn) => {
      btn.addEventListener("mousedown", (e) => e.preventDefault());
      btn.addEventListener("click", onFilterChipClick);
    });
  }

  function onFilterChipClick(event) {
    const filterType = event.target.dataset.filterType;
    const filterValue = event.target.dataset.filterValue;
    const selectId = filterType + "Filter";
    const select = document.getElementById(selectId);

    if (select) {
      const isActive = event.target.classList.contains("is-active");
      select.value = isActive ? "" : filterValue;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      renderQuickFilters();
    }

    const input = document.getElementById(INPUT_ID);
    const currentQuery = input ? input.value.trim() : "";
    void runSearch(currentQuery);
  }

  function openModal() {
    buildModal();
    const modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    modal.classList.remove("d-none");
    document.body.classList.add("global-search-open");
    const input = document.getElementById(INPUT_ID);
    if (input) {
      input.value = "";
      input.focus();
    }
    lastQuery = "";
    currentResults = [];
    activeIndex = -1;
    renderResults();
    renderQuickFilters();
  }

  function closeModal() {
    const modal = document.getElementById(MODAL_ID);
    if (modal) modal.classList.add("d-none");
    document.body.classList.remove("global-search-open");
    currentResults = [];
    activeIndex = -1;
    lastQuery = "";
    clearTimeout(debounceTimer);
  }

  function isOpen() {
    const modal = document.getElementById(MODAL_ID);
    return modal && !modal.classList.contains("d-none");
  }

  function onInput(event) {
    const query = event.target.value.trim();
    clearTimeout(debounceTimer);
    const hasActiveFilters = Object.values(getActiveFilters()).some(Boolean);
    if (query.length < MIN_QUERY_LENGTH && !hasActiveFilters) {
      lastQuery = query;
      currentResults = [];
      activeIndex = -1;
      renderResults();
      return;
    }
    debounceTimer = setTimeout(() => { void runSearch(query); }, DEBOUNCE_MS);
  }

  async function runSearch(query) {
    lastQuery = query;
    try {
      const params = new URLSearchParams();
      if (query) params.set("search", query);
      const activeFilters = getActiveFilters();
      if (activeFilters.status) params.set("status", activeFilters.status);
      const res = await fetch(`/api/forms?${params.toString()}`, {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        renderUnauthenticated();
        return;
      }
      if (!res.ok) {
        renderError();
        return;
      }
      const data = await res.json();
      // Ignore les résultats obsolètes si une nouvelle saisie est intervenue.
      if (lastQuery !== query) return;
      let results = Array.isArray(data) ? data : [];
      // Filtres client-side (timing et qualite non supportés par le backend)
      if (activeFilters.timing) {
        results = results.filter((r) => r.timingStatus === activeFilters.timing);
      }
      if (activeFilters.qualite) {
        results = results.filter((r) => r.beneficiaryType === activeFilters.qualite);
      }
      currentResults = results.slice(0, MAX_RESULTS);
      activeIndex = currentResults.length ? 0 : -1;
      renderResults();
    } catch (_error) {
      renderError();
    }
  }

  function renderResults() {
    const list = document.getElementById(RESULTS_ID);
    if (!list) return;

    if (!currentResults.length) {
      if (lastQuery.length >= MIN_QUERY_LENGTH) {
        list.innerHTML = `<li class="global-search__empty">Aucun dossier ne correspond à « ${escapeHtml(lastQuery)} ».</li>`;
      } else {
        list.innerHTML = `<li class="global-search__empty">Tapez au moins ${MIN_QUERY_LENGTH} caractères pour rechercher.</li>`;
      }
      return;
    }

    list.innerHTML = currentResults.map((item, index) => {
      const fullName = escapeHtml(`${item.prenom || ""} ${item.nom || ""}`.trim() || "(sans nom)");
      const service = escapeHtml(item.service || "");
      const statusLabel = escapeHtml(STATUS_LABELS[item.status] || item.status || "");
      const isActive = index === activeIndex ? " is-active" : "";
      return `
        <li class="global-search__result${isActive}" role="option"
            data-gs-index="${index}" data-gs-id="${escapeHtml(item.id)}"
            aria-selected="${index === activeIndex ? "true" : "false"}">
          <div class="global-search__result-main">
            <strong class="global-search__result-name">${fullName}</strong>
            ${service ? `<span class="global-search__result-service">${service}</span>` : ""}
          </div>
          <span class="global-search__result-status">${statusLabel}</span>
        </li>
      `;
    }).join("");

    list.querySelectorAll(".global-search__result").forEach((el) => {
      el.addEventListener("mouseenter", () => {
        const idx = Number(el.dataset.gsIndex);
        if (!Number.isNaN(idx)) {
          activeIndex = idx;
          updateActiveHighlight();
        }
      });
      el.addEventListener("click", () => {
        const id = el.dataset.gsId;
        if (id) navigateTo(id);
      });
    });
  }

  function updateActiveHighlight() {
    const list = document.getElementById(RESULTS_ID);
    if (!list) return;
    list.querySelectorAll(".global-search__result").forEach((el) => {
      const idx = Number(el.dataset.gsIndex);
      const isActive = idx === activeIndex;
      el.classList.toggle("is-active", isActive);
      el.setAttribute("aria-selected", isActive ? "true" : "false");
    });
  }

  function renderError() {
    const list = document.getElementById(RESULTS_ID);
    if (list) {
      list.innerHTML = `<li class="global-search__empty global-search__empty--error">Erreur de connexion au serveur.</li>`;
    }
  }

  function renderUnauthenticated() {
    const list = document.getElementById(RESULTS_ID);
    if (list) {
      list.innerHTML = `<li class="global-search__empty">Session expirée. Reconnectez-vous pour rechercher.</li>`;
    }
  }

  function moveActive(delta) {
    if (!currentResults.length) return;
    const length = currentResults.length;
    activeIndex = (activeIndex + delta + length) % length;
    updateActiveHighlight();
    const el = document.querySelector(`#${RESULTS_ID} .global-search__result.is-active`);
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest" });
    }
  }

  function onInputKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveActive(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveActive(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0 && currentResults[activeIndex]) {
        navigateTo(currentResults[activeIndex].id);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
    }
  }

  function navigateTo(id) {
    closeModal();
    window.location.href = `form.html?id=${encodeURIComponent(id)}`;
  }

  function onGlobalKeyDown(event) {
    const isKKey = event.key === "k" || event.key === "K";
    if (isKKey && (event.ctrlKey || event.metaKey)) {
      // Évite le conflit dans les champs de saisie classiques : on force l'ouverture.
      event.preventDefault();
      if (isOpen()) {
        closeModal();
      } else {
        openModal();
      }
    } else if (event.key === "Escape" && isOpen()) {
      event.preventDefault();
      closeModal();
    }
  }

  function init() {
    buildTriggerButton();
    document.addEventListener("keydown", onGlobalKeyDown);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
