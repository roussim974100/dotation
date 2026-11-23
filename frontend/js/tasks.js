// Page « Mes tâches » : toutes les tâches qui me concernent (celles de mon service, celles des administrateurs), filtrables, avec
// « Fait » sur chaque ligne et l'historique des 30 derniers jours (pour rouvrir une erreur). Les composants (tableaux, « Fait »,
// « Rouvrir ») viennent de notifications.js : un seul endroit à maintenir.
(function () {
  "use strict";

  const N = window.AQuaiNotifications;
  const kindsSelect = document.getElementById("tasksKindFilter");
  const lateOnly = document.getElementById("tasksLateOnly");
  const container = document.getElementById("tasksContainer");
  const recentContainer = document.getElementById("recentContainer");
  const summary = document.getElementById("tasksSummary");
  let tasks = [];

  const SERVICE_KINDS = { service_provision: "Fait : fourni", service_deprovision: "Fait : fermé" };

  async function getJson(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error(url);
    }
    return response.json();
  }

  function visibleTasks() {
    const kind = kindsSelect.value;
    return tasks
      .filter((task) => !kind || task.kind === kind)
      .map((task) => {
        if (!lateOnly.checked || !SERVICE_KINDS[task.kind]) {
          return lateOnly.checked ? null : task;  // « seulement en retard » : les tâches sans ancienneté disparaissent
        }
        const items = task.items.filter((item) => item.late);
        return items.length ? { ...task, items, count: items.length } : null;
      })
      .filter(Boolean);
  }

  function renderTasks() {
    const shown = visibleTasks();
    container.innerHTML = "";
    if (!shown.length) {
      container.innerHTML = `<p class="notification-empty">${tasks.length ? "Aucune tâche ne correspond à ce filtre." : "Rien à faire pour le moment."}</p>`;
    }
    shown.forEach((task) => {
      const kind = N.NOTIFICATION_KINDS[task.kind];
      if (!kind) {
        return;
      }
      const section = document.createElement("section");
      section.className = "tasks-page__section";
      const heading = document.createElement("h3");
      heading.className = "h5";
      heading.textContent = kind.title(task);
      const detail = document.createElement("p");
      detail.className = "panel-text";
      detail.textContent = kind.detail(task);
      section.append(heading, detail);
      const body = document.createElement("div");
      section.appendChild(body);
      if (SERVICE_KINDS[task.kind]) {
        N.mountServiceTasks(body, task, { doneLabel: SERVICE_KINDS[task.kind], onChange: loadRecent, onEmpty: () => reload(false) });
      } else {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-primary";
        button.textContent = kind.actionLabel;
        button.addEventListener("click", () => kind.run(task));
        body.appendChild(button);
      }
      container.appendChild(section);
    });
    summary.textContent = shown.length ? `${shown.length} liste${shown.length > 1 ? "s" : ""} de tâches affichée${shown.length > 1 ? "s" : ""}.` : "Aucune tâche affichée.";
  }

  function fillKindFilter() {
    const current = kindsSelect.value;
    kindsSelect.innerHTML = '<option value="">Toutes les tâches</option>' + tasks
      .map((task) => `<option value="${N.esc(task.kind)}">${N.esc(N.NOTIFICATION_KINDS[task.kind]?.title(task) || task.kind)}</option>`).join("");
    kindsSelect.value = tasks.some((task) => task.kind === current) ? current : "";
  }

  async function loadRecent() {
    try {
      const data = await getJson("/api/service-tasks/recent");
      N.mountRecentDone(recentContainer, data.items || [], { onChange: () => reload(true) });
    } catch (error) {
      recentContainer.textContent = "Impossible de charger l'historique.";
    }
  }

  async function reload(withRecent = true) {
    try {
      const data = await getJson("/api/notifications");
      tasks = data.tasks || [];
      fillKindFilter();
      renderTasks();
      window.updateNotificationBadge?.(tasks.length);
    } catch (error) {
      container.textContent = "Impossible de charger vos tâches. Rechargez la page.";
    }
    if (withRecent) {
      await loadRecent();
    }
  }

  kindsSelect.addEventListener("change", renderTasks);
  lateOnly.addEventListener("change", renderTasks);
  reload(true);
})();
