// Fiche d'un dossier : « Tâches des services » — ce qui reste à faire (service, ancienneté, retard) puis ce qui est fait (par qui,
// quand). Données : GET /api/forms/<id>/service-tasks. Rien n'est affiché pour un dossier neuf, sans tâche, ou sans droit de lecture.
(function () {
  "use strict";

  const container = document.getElementById("serviceTasksHistory");
  const formId = new URLSearchParams(window.location.search).get("id");
  if (!container || !formId) {
    return;
  }

  // Un type de tâche = deux libellés (à faire / fait) : en ajouter un se fait ici, sans toucher au rendu.
  const KINDS = {
    service_provision: { open: "À fournir", done: "Fourni" },
    service_deprovision: { open: "À fermer", done: "Fermé" },
  };

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const formatDate = (iso) => (iso ? new Date(iso).toLocaleDateString("fr-FR") : "");

  function describe(item) {
    const kind = KINDS[item.kind] || { open: "À faire", done: "Terminé" };
    if (item.state === "done") {
      return `<li class="list-group-item">
        <strong>✓ ${esc(kind.done)}</strong> — ${esc(item.label)}
        <span class="text-muted">· ${esc(item.service)} · par ${esc(item.done_by)} le ${esc(formatDate(item.done_at))}</span>
      </li>`;
    }
    let age = `${item.age_days} j`;
    if (item.escalated) {
      age = `<span class="service-tasks__late service-tasks__late--escalated">⚠ Escaladée · ${item.age_days} j</span>`;
    } else if (item.late) {
      age = `<span class="service-tasks__late">⏰ En retard · ${item.age_days} j</span>`;
    }
    const unattended = item.unattended ? ' <span class="text-muted">(service sans titulaire : administrateurs)</span>' : "";
    return `<li class="list-group-item">
      <strong>⏳ ${esc(kind.open)}</strong> — ${esc(item.label)}
      <span class="text-muted">· ${esc(item.service)}</span> · ${age}${unattended}
    </li>`;
  }

  async function load() {
    try {
      const response = await fetch(`/api/forms/${encodeURIComponent(formId)}/service-tasks`, { credentials: "same-origin" });
      if (!response.ok) {
        return;  // pas de droit de lecture, dossier introuvable : on n'affiche rien
      }
      const items = (await response.json()).items || [];
      container.classList.toggle("d-none", !items.length);
      container.innerHTML = items.length
        ? `<p class="panel-eyebrow mb-1">Tâches des services</p><ul class="list-group">${items.map(describe).join("")}</ul>`
        : "";
    } catch (error) {
      /* l'absence de cet encart ne doit jamais gêner la fiche */
    }
  }

  load();
})();
