// Notifications : panneau de la cloche et fenêtres d'action. Chargé À LA DEMANDE par ui.js (premier clic sur la cloche) :
// aucune page HTML n'a à le déclarer. Dépend de ui.js (showToast, getCsrfToken, updateNotificationBadge).
// Les types de notification sont décrits par l'objet NOTIFICATION_KINDS : en ajouter un = ajouter une entrée ici (et son
// calcul côté serveur, models/notifications.py), sans toucher au panneau.
(function () {
  "use strict";

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;

  const goTo = (task) => window.location.assign(task.link);

  const NOTIFICATION_KINDS = {
    backup_failed: {
      title: () => "La sauvegarde automatique a échoué",
      detail: (task) => task.message || "Vérifiez la configuration des sauvegardes.",
      actionLabel: "Voir les sauvegardes",
      run: goTo,
    },
    update_available: {
      title: (task) => `Nouvelle version disponible : ${task.latest}`,
      detail: (task) => (task.current ? `Version installée : ${task.current}. Lisez les notes de version avant de mettre à jour.` : "Lisez les notes de version avant de mettre à jour."),
      actionLabel: "Voir la mise à jour",
      run: goTo,
    },
    signups_pending: {
      title: (task) => plural(task.count, "demande d'inscription à traiter", "demandes d'inscription à traiter"),
      detail: () => "Validez ou refusez les comptes en attente.",
      actionLabel: "Voir les demandes",
      run: goTo,
    },
    service_provision: {
      title: (task) => plural(task.count, "ressource à fournir", "ressources à fournir"),
      detail: () => "Préparez ou créez ce qui a été attribué (compte, accès, matériel), puis cliquez « Fait » : la tâche disparaît pour tout votre service.",
      actionLabel: "Voir la liste",
      run: (task) => openServiceTasksModal(task, "Ressources à fournir", "Fait : fourni"),
    },
    service_deprovision: {
      title: (task) => plural(task.count, "ressource à fermer", "ressources à fermer"),
      detail: () => "Des personnes quittent l'organisation : désactivez leurs comptes et accès, puis cliquez « Fait ».",
      actionLabel: "Voir la liste",
      run: (task) => openServiceTasksModal(task, "Ressources à fermer", "Fait : fermé"),
    },
    resources_missing_service: {
      title: (task) => `${plural(task.count, "ressource sans service référent", "ressources sans service référent")}`,
      detail: () => "Choisissez le service de chacune : ses titulaires seront prévenus des actions à mener.",
      actionLabel: "Choisir les services",
      run: (task) => openAssignServicesModal(task),
    },
  };

  let panel = null;
  let lastFocus = null;

  function bell() {
    return document.getElementById("notificationBell");
  }

  async function fetchTasks() {
    const response = await fetch("/api/notifications", { credentials: "same-origin" });
    if (!response.ok) {
      throw new Error("notifications_unavailable");
    }
    return response.json();
  }

  function renderTask(task, index) {
    const kind = NOTIFICATION_KINDS[task.kind];
    if (!kind) {
      return "";
    }
    const urgent = task.severity === "urgent" ? '<span class="notification-item__urgent">⚠ Urgent</span> ' : "";
    const late = task.late_count ? ` <span class="notification-item__urgent">⏰ ${esc(plural(task.late_count, "en retard", "en retard"))}</span>` : "";
    return `<li class="notification-item">
      <p class="notification-item__title">${urgent}${esc(kind.title(task))}${late}</p>
      <p class="notification-item__detail">${esc(kind.detail(task))}</p>
      <button type="button" class="btn btn-sm btn-primary" data-notification-run="${index}">${esc(kind.actionLabel)}</button>
    </li>`;
  }

  function renderPanel(data) {
    if (!panel) {
      return;
    }
    const tasks = data.tasks || [];
    const body = tasks.length
      ? `<ul class="notification-list">${tasks.map(renderTask).join("")}</ul>`
      : '<p class="notification-empty">Rien à faire pour le moment.</p>';
    panel.innerHTML = `<h2 class="notification-panel__title" id="notificationPanelTitle" tabindex="-1">Notifications</h2>${body}
      <p class="notification-panel__all"><a href="tasks.html">Tout voir dans « Mes tâches »</a></p>`;
    panel.querySelectorAll("[data-notification-run]").forEach((button) => {
      button.addEventListener("click", () => {
        const task = tasks[Number(button.dataset.notificationRun)];
        closePanel(false);
        NOTIFICATION_KINDS[task.kind]?.run(task);
      });
    });
    window.updateNotificationBadge?.(tasks.length);
  }

  function positionPanel() {
    const anchor = bell();
    if (!panel || !anchor) {
      return;
    }
    const rect = anchor.getBoundingClientRect();
    const width = Math.min(360, window.innerWidth - 16);
    panel.style.width = `${width}px`;
    panel.style.top = `${Math.round(rect.bottom + 8)}px`;
    panel.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
  }

  async function openPanel() {
    if (panel) {
      return;
    }
    lastFocus = document.activeElement;
    // Rattaché au <body> : le cadre des listes a un backdrop-filter qui piégerait un élément fixe (cf. menu « ⋯ »).
    panel = document.createElement("div");
    panel.id = "notificationPanel";
    panel.className = "notification-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-labelledby", "notificationPanelTitle");
    panel.innerHTML = '<h2 class="notification-panel__title" id="notificationPanelTitle" tabindex="-1">Notifications</h2><p class="notification-empty">Chargement…</p>';
    document.body.appendChild(panel);
    bell()?.setAttribute("aria-expanded", "true");
    positionPanel();
    document.addEventListener("keydown", onKeydown);
    document.addEventListener("click", onOutsideClick, true);
    window.addEventListener("resize", positionPanel);
    try {
      renderPanel(await fetchTasks());
    } catch (error) {
      if (panel) {
        panel.innerHTML = '<h2 class="notification-panel__title" id="notificationPanelTitle" tabindex="-1">Notifications</h2><p class="notification-empty">Impossible de charger les notifications.</p>';
      }
    }
    panel?.querySelector("#notificationPanelTitle")?.focus();
  }

  function closePanel(restoreFocus = true) {
    if (!panel) {
      return;
    }
    panel.remove();
    panel = null;
    bell()?.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", onKeydown);
    document.removeEventListener("click", onOutsideClick, true);
    window.removeEventListener("resize", positionPanel);
    if (restoreFocus) {
      (lastFocus && document.contains(lastFocus) ? lastFocus : bell())?.focus();
    }
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      closePanel();
    }
  }

  function onOutsideClick(event) {
    if (panel && !panel.contains(event.target) && !bell()?.contains(event.target)) {
      closePanel(false);
    }
  }

  function togglePanel() {
    return panel ? closePanel() : openPanel();
  }

  // ─── Choix du service référent des ressources (tâche des administrateurs) ────────────────────────────────────
  function openAssignServicesModal(task) {
    if (document.getElementById("assignServicesModal")) {
      return;
    }
    const services = task.services || [];
    const options = (selectedId) => `<option value="">— Choisir un service —</option>${services
      .map((service) => `<option value="${esc(service.id)}"${service.id === selectedId ? " selected" : ""}>${esc(service.label)}</option>`)
      .join("")}`;
    const groups = (task.groups || []).map((group, index) => {
      const names = group.resources.map((resource) => resource.label);
      const shown = names.slice(0, 4).join(", ") + (names.length > 4 ? `… (+ ${names.length - 4})` : "");
      const legacy = group.legacy_service || "(aucun service renseigné)";
      return `<div class="assign-services__group">
        <label class="form-label" for="assignService${index}">
          <strong>${esc(legacy)}</strong> — ${esc(plural(group.resources.length, "ressource", "ressources"))}
        </label>
        <p class="assign-services__resources">${esc(shown)}</p>
        <select class="form-select" id="assignService${index}" data-group="${index}">${options(group.suggested_service_id)}</select>
        ${group.suggested_service_id ? '<p class="form-text mb-0">Suggestion pré-remplie : vous pouvez la changer.</p>' : ""}
      </div>`;
    }).join("");

    const backdrop = document.createElement("div");
    backdrop.id = "assignServicesModal";
    backdrop.className = "password-change-modal__backdrop";
    backdrop.innerHTML = `
      <div class="password-change-modal__dialog assign-services" role="dialog" aria-modal="true" aria-labelledby="assignServicesTitle">
        <h3 id="assignServicesTitle">Choisir le service référent</h3>
        <p class="form-text mt-0">Chaque ressource doit appartenir à un service du catalogue : ses titulaires reçoivent les notifications. Rien n'est modifié avant que vous validiez ; vous pouvez laisser un groupe pour plus tard.</p>
        ${groups}
        <div id="assignServicesFeedback" role="status"></div>
        <div class="password-change-modal__actions">
          <button class="btn btn-outline-secondary" type="button" id="assignServicesCancel">Plus tard</button>
          <button class="btn btn-primary" type="button" id="assignServicesSubmit">Valider les choix</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const close = () => {
      document.removeEventListener("keydown", onEscape);
      backdrop.remove();
      (bell() || null)?.focus();
    };
    const onEscape = (event) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("keydown", onEscape);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        close();
      }
    });
    backdrop.querySelector("#assignServicesCancel").addEventListener("click", close);
    backdrop.querySelector("#assignServicesSubmit").addEventListener("click", async () => {
      const feedback = backdrop.querySelector("#assignServicesFeedback");
      const assignments = [];
      backdrop.querySelectorAll("select[data-group]").forEach((select) => {
        if (select.value) {
          assignments.push({ resource_ids: task.groups[Number(select.dataset.group)].resources.map((resource) => resource.id), service_id: select.value });
        }
      });
      if (!assignments.length) {
        feedback.className = "password-change-modal__feedback password-change-modal__feedback--error";
        feedback.textContent = "Choisissez au moins un service, ou fermez avec « Plus tard ».";
        return;
      }
      const submit = backdrop.querySelector("#assignServicesSubmit");
      submit.disabled = true;
      try {
        const response = await fetch("/api/admin/resources/services", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
          body: JSON.stringify({ assignments }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "erreur");
        }
        window.updateNotificationBadge?.(data.count);
        close();
        showToast(`${plural(data.assigned, "ressource rattachée", "ressources rattachées")} à son service.`, "success");
        if (data.count) {
          openPanel();
        }
      } catch (error) {
        feedback.className = "password-change-modal__feedback password-change-modal__feedback--error";
        feedback.textContent = "Impossible d'enregistrer ces choix. Rechargez la page et réessayez.";
        submit.disabled = false;
      }
    });
    backdrop.querySelector("select")?.focus();
  }

  // ─── Tâches de service : à fournir / à fermer, avec « Fait » partagé par tout le service ──────────────────────────
  // L'ancienneté est dite en toutes lettres (« En retard », « Escaladée »), jamais seulement par la couleur.
  function ageLabel(item, lateDays, escalateDays) {
    const days = `${item.age_days} j`;
    if (item.escalated) {
      return `<span class="service-tasks__late service-tasks__late--escalated">⚠ Escaladée aux administrateurs · ${days}</span>`;
    }
    if (item.late) {
      return `<span class="service-tasks__late">⏰ En retard · ${days}</span>`;
    }
    return esc(days);
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "erreur");
    }
    return data;
  }

  // Dessine le tableau des lignes d'une tâche de service dans `container` ; « Fait » enregistre et retire la ligne.
  // hooks : { doneLabel, onChange(data), onEmpty() }
  function mountServiceTasks(container, task, hooks = {}) {
    const rows = (task.items || []).map((item, index) => `<tr data-row="${index}">
        <td data-label="Personne">${esc(item.who)}</td>
        <td data-label="Ressource">${esc(item.label)}${item.unattended ? '<br><span class="form-text">Service sans titulaire : pris en charge par les administrateurs.</span>' : ""}</td>
        <td data-label="Service">${esc(item.service)}</td>
        <td data-label="Ancienneté">${ageLabel(item)}</td>
        <td data-label="Actions" class="service-tasks__actions">
          ${item.can_open ? `<a class="btn btn-sm btn-outline-secondary" href="form.html?id=${encodeURIComponent(item.form_id)}">Ouvrir le dossier</a>` : ""}
          <button type="button" class="btn btn-sm btn-primary" data-done="${index}">${esc(hooks.doneLabel || "Fait")}</button>
        </td>
      </tr>`).join("");
    container.innerHTML = `
      ${task.truncated ? '<p class="form-text">Liste limitée aux premières lignes ; les suivantes apparaîtront au fur et à mesure.</p>' : ""}
      <div class="table-responsive">
        <table class="table align-middle service-tasks__table">
          <thead><tr><th>Personne</th><th>Ressource</th><th>Service</th><th>Ancienneté</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="service-tasks__feedback" role="status"></div>`;
    const feedback = container.querySelector(".service-tasks__feedback");
    container.querySelectorAll("[data-done]").forEach((button) => {
      button.addEventListener("click", async () => {
        const item = task.items[Number(button.dataset.done)];
        button.disabled = true;
        try {
          const data = await postJson("/api/service-tasks/done", { kind: task.kind, form_id: item.form_id, item_key: item.item_key });
          container.querySelector(`tr[data-row="${button.dataset.done}"]`)?.remove();
          window.updateNotificationBadge?.(data.count);
          feedback.className = "service-tasks__feedback";
          feedback.textContent = `${item.label} : terminé pour tout le service.`;
          hooks.onChange?.(data);
          if (!container.querySelector("tbody tr")) {
            hooks.onEmpty?.();
          }
        } catch (error) {
          button.disabled = false;
          feedback.className = "service-tasks__feedback password-change-modal__feedback password-change-modal__feedback--error";
          feedback.textContent = "Impossible d'enregistrer. Un collègue l'a peut-être déjà fait : rechargez la page.";
        }
      });
    });
  }

  // Ce qui a été terminé ces 30 derniers jours : permet de vérifier, et de rouvrir un « Fait » enregistré par erreur.
  function mountRecentDone(container, items, hooks = {}) {
    if (!items.length) {
      container.innerHTML = '<p class="notification-empty">Rien de terminé ces 30 derniers jours.</p>';
      return;
    }
    const kindLabel = (kind) => (kind === "service_deprovision" ? "À fermer" : "À fournir");
    const rows = items.map((item, index) => `<tr data-row="${index}">
        <td data-label="Personne">${esc(item.who)}</td>
        <td data-label="Ressource">${esc(item.label)} <span class="text-muted">(${kindLabel(item.kind)})</span></td>
        <td data-label="Service">${esc(item.service)}</td>
        <td data-label="Terminé">${esc(String(item.done_at || "").slice(0, 10))} par ${esc(item.done_by)}</td>
        <td data-label="Actions" class="service-tasks__actions"><button type="button" class="btn btn-sm btn-outline-secondary" data-reopen="${index}">Rouvrir</button></td>
      </tr>`).join("");
    container.innerHTML = `
      <div class="table-responsive">
        <table class="table align-middle service-tasks__table">
          <thead><tr><th>Personne</th><th>Ressource</th><th>Service</th><th>Terminé</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="service-tasks__feedback" role="status"></div>`;
    const feedback = container.querySelector(".service-tasks__feedback");
    container.querySelectorAll("[data-reopen]").forEach((button) => {
      button.addEventListener("click", async () => {
        const item = items[Number(button.dataset.reopen)];
        button.disabled = true;
        try {
          const data = await postJson("/api/service-tasks/reopen", { kind: item.kind, form_id: item.form_id, item_key: item.item_key });
          window.updateNotificationBadge?.(data.count);
          feedback.textContent = `${item.label} : la tâche est rouverte pour tout le service.`;
          hooks.onChange?.(data);
        } catch (error) {
          button.disabled = false;
          feedback.textContent = "Impossible de rouvrir : la tâche a peut-être déjà changé. Rechargez la page.";
        }
      });
    });
  }

  function openServiceTasksModal(task, title, doneLabel) {
    if (document.getElementById("serviceTasksModal")) {
      return;
    }
    const backdrop = document.createElement("div");
    backdrop.id = "serviceTasksModal";
    backdrop.className = "password-change-modal__backdrop";
    backdrop.innerHTML = `
      <div class="password-change-modal__dialog service-tasks" role="dialog" aria-modal="true" aria-labelledby="serviceTasksTitle">
        <h3 id="serviceTasksTitle" tabindex="-1">${esc(title)}</h3>
        <div id="serviceTasksBody"></div>
        <div class="password-change-modal__actions">
          <a class="btn btn-link" href="tasks.html">Tout voir dans « Mes tâches »</a>
          <button class="btn btn-outline-secondary" type="button" id="serviceTasksClose">Fermer</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const close = () => {
      document.removeEventListener("keydown", onEscape);
      backdrop.remove();
      bell()?.focus();
    };
    const onEscape = (event) => {
      if (event.key === "Escape") {
        close();
      }
    };
    document.addEventListener("keydown", onEscape);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        close();
      }
    });
    backdrop.querySelector("#serviceTasksClose").addEventListener("click", close);
    mountServiceTasks(backdrop.querySelector("#serviceTasksBody"), task, {
      doneLabel,
      onEmpty: () => {
        close();
        showToast("Plus rien à faire dans cette liste.", "success");
      },
    });
    backdrop.querySelector("#serviceTasksTitle").focus();
  }

  window.AQuaiNotifications = { togglePanel, openPanel, closePanel, NOTIFICATION_KINDS, mountServiceTasks, mountRecentDone, esc, plural };
})();
