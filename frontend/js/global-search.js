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

  // Palette : pages et actions atteignables au clavier (Ctrl+K puis Entrée). Ce sont de simples LIENS : aucune action sensible
  // ne s'exécute d'ici (« Sauvegarder maintenant » ouvre la page de sauvegarde, où la confirmation a lieu).
  // perm : null = tous ; sinon "forms.create" | "forms.read_list" | "users.manage" | "db.manage" | "direction".
  const COMMANDS = [
    { label: "Nouvelle attribution", href: "form.html", perm: "forms.create", keys: "creer dossier arrivee nouveau" },
    { label: "Attributions en cours", href: "index.html", keys: "dossiers accueil liste" },
    { label: "Attributions finalisées", href: "assignments-completed.html", keys: "dossiers signes historique" },
    { label: "Restitutions en cours", href: "restitutions-pending.html", keys: "retour depart materiel" },
    { label: "Restitutions finalisées", href: "restitutions-completed.html", keys: "retours termines historique" },
    { label: "Parc matériel", href: "parc.html", perm: "forms.read_list", keys: "objets stock inventaire historique de vie" },
    { label: "Synthèse", href: "executive-dashboard.html", perm: "direction", keys: "tableau de bord direction indicateurs" },
    { label: "Administration", href: "admin.html", perm: "users.manage", keys: "portail admin configuration" },
    { label: "Comptes et droits", href: "admin-comptes.html", perm: "users.manage", keys: "utilisateurs groupes permissions" },
    { label: "Créer un compte", href: "admin-comptes.html#admin-users-create", perm: "users.manage", keys: "nouvel utilisateur mot de passe" },
    { label: "Services", href: "admin-services.html", perm: "users.manage", keys: "direction service catalogue" },
    { label: "Ressources", href: "admin-ressources.html", perm: "users.manage", keys: "catalogue materiel referentiel" },
    { label: "Ajouter une ressource", href: "admin-ressources.html#new", perm: "users.manage", keys: "creer nouvelle ressource assistant" },
    { label: "Ordre des ressources", href: "admin-ressources-ordre.html", perm: "users.manage", keys: "reorganiser trier" },
    { label: "Assistant d'organisation", href: "admin-personnalisation.html?wizard=1", perm: "users.manage", keys: "configuration demarrage type organisation beneficiaires" },
    { label: "Personnalisation", href: "admin-personnalisation.html", perm: "users.manage", keys: "logo theme couleurs mode sombre support dpo" },
    { label: "Sauvegarder maintenant", href: "admin-db.html#db-export", perm: "db.manage", keys: "exporter archive base de donnees telecharger" },
    { label: "Planifier la sauvegarde", href: "admin-db.html#db-schedule", perm: "db.manage", keys: "automatique frequence destination" },
    { label: "Restaurer une sauvegarde", href: "admin-db.html#db-restore", perm: "db.manage", keys: "importer analyser" },
    { label: "Journal", href: "logs.html", perm: "users.manage", keys: "traces audit historique actions" },
    { label: "Corbeille", href: "trash.html", perm: "users.manage", keys: "supprimes restaurer" },
    { label: "Mon profil", href: "account.html", keys: "compte e-mail mot de passe identite" },
    { label: "Aide", href: "help.html", keys: "documentation guide support" }
  ];
  let sessionPermissions = null;

  function fold(text) {
    return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  async function loadPermissions() {
    if (sessionPermissions) return sessionPermissions;
    try {
      const response = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
      const user = response.ok ? await response.json() : {};
      const permissions = user.permissions || [];
      const all = permissions.includes("*");
      sessionPermissions = {
        all, list: permissions, direction: Boolean(user.is_admin || (user.groups || []).includes("direction")),
        db: Boolean(all || permissions.includes("db.manage") || user.db_manage)
      };
    } catch (_error) {
      sessionPermissions = { all: false, list: [], direction: false, db: false };
    }
    return sessionPermissions;
  }

  function isAllowed(command, access) {
    if (!command.perm) return true;
    if (command.perm === "direction") return access.direction;
    if (command.perm === "db.manage") return access.db;
    return access.all || access.list.includes(command.perm);
  }

  // Commandes qui correspondent : tous les mots saisis doivent se trouver dans le libellé ou les mots-clés.
  function matchCommands(query, access, limit) {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return COMMANDS.filter((command) => isAllowed(command, access))
      .filter((command) => {
        const haystack = fold(`${command.label} ${command.keys || ""}`);
        return words.every((word) => haystack.includes(word));
      })
      .slice(0, limit)
      .map((command) => ({ kind: "command", label: command.label, href: command.href }));
  }

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
    void showDefaultCommands();
  }

  // Sans saisie : les raccourcis les plus utiles pour ce profil.
  async function showDefaultCommands() {
    const access = await loadPermissions();
    if (lastQuery) return;
    const wanted = ["Nouvelle attribution", "Parc matériel", "Administration", "Assistant d'organisation", "Sauvegarder maintenant", "Journal", "Mon profil"];
    currentResults = wanted.map((label) => COMMANDS.find((command) => command.label === label)).filter((command) => command && isAllowed(command, access))
      .map((command) => ({ kind: "command", label: command.label, href: command.href }));
    activeIndex = currentResults.length ? 0 : -1;
    renderResults();
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
      if (!query) void showDefaultCommands();
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
      const access = await loadPermissions();
      const commands = query ? matchCommands(query, access, 6) : [];
      currentResults = commands.concat(results.slice(0, MAX_RESULTS).map((form) => ({ kind: "form", ...form })));
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

    const rowHtml = (item, index) => {
      const isActive = index === activeIndex ? " is-active" : "";
      const aria = `role="option" data-gs-index="${index}" aria-selected="${index === activeIndex ? "true" : "false"}"`;
      if (item.kind === "command") {
        return `
        <li class="global-search__result${isActive}" ${aria} data-gs-href="${escapeHtml(item.href)}">
          <div class="global-search__result-main"><strong class="global-search__result-name">${escapeHtml(item.label)}</strong></div>
          <span class="global-search__result-status">Aller à</span>
        </li>`;
      }
      const fullName = escapeHtml(`${item.prenom || ""} ${item.nom || ""}`.trim() || "(sans nom)");
      const service = escapeHtml(item.service || "");
      const statusLabel = escapeHtml(STATUS_LABELS[item.status] || item.status || "");
      return `
        <li class="global-search__result${isActive}" ${aria} data-gs-id="${escapeHtml(item.id)}">
          <div class="global-search__result-main">
            <strong class="global-search__result-name">${fullName}</strong>
            ${service ? `<span class="global-search__result-service">${service}</span>` : ""}
          </div>
          <span class="global-search__result-status">${statusLabel}</span>
        </li>`;
    };
    let html = "";
    let lastKind = "";
    currentResults.forEach((item, index) => {
      if (item.kind !== lastKind) {
        html += `<li class="global-search__group" role="presentation">${item.kind === "command" ? "Pages et actions" : "Dossiers"}</li>`;
        lastKind = item.kind;
      }
      html += rowHtml(item, index);
    });
    list.innerHTML = html;

    list.querySelectorAll(".global-search__result").forEach((el) => {
      el.addEventListener("mouseenter", () => {
        const idx = Number(el.dataset.gsIndex);
        if (!Number.isNaN(idx)) {
          activeIndex = idx;
          updateActiveHighlight();
        }
      });
      el.addEventListener("click", () => {
        const idx = Number(el.dataset.gsIndex);
        if (!Number.isNaN(idx) && currentResults[idx]) activate(currentResults[idx]);
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
        activate(currentResults[activeIndex]);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
    }
  }

  function activate(item) {
    closeModal();
    window.location.href = item.kind === "command" ? item.href : `form.html?id=${encodeURIComponent(item.id)}`;
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
