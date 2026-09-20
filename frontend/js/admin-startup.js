// Checklist de démarrage (portail admin) : ce qu'il reste à faire pour bien démarrer, calculé sur l'état réel du serveur.
// Masquée quand tout est fait. Les points « #wizard » ouvrent l'assistant d'organisation.

(function () {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function render(data) {
    const box = document.getElementById("startupChecklist");
    if (!box) return;
    if (data.percent >= 100) {
      box.classList.add("d-none");
      return;
    }
    const href = (link) => (link === "#wizard" ? "admin-personnalisation.html?wizard=1" : link);
    box.innerHTML = `
      <section class="content-card" aria-labelledby="startupTitle">
        <div class="section-heading">
          <div><p class="panel-eyebrow">Démarrage</p><h2 class="section-title" id="startupTitle">Configuration : ${data.done} étape(s) sur ${data.total}</h2></div>
          <a class="btn btn-primary" href="admin-personnalisation.html?wizard=1">Assistant d'organisation</a>
        </div>
        <div class="progress mb-3" role="progressbar" aria-valuenow="${data.percent}" aria-valuemin="0" aria-valuemax="100" aria-label="Avancement de la configuration">
          <div class="progress-bar" style="width:${data.percent}%">${data.percent} %</div>
        </div>
        <ul class="list-unstyled mb-0">
          ${data.items.map((item) => `<li class="mb-1">${item.done ? "✅" : (item.required ? "⬜" : "▫️")}
            ${item.done ? esc(item.label) : `<a href="${esc(href(item.link))}">${esc(item.label)}</a>${item.required ? "" : ' <span class="small text-muted">(recommandé)</span>'}`}</li>`).join("")}
        </ul>
      </section>`;
    box.classList.remove("d-none");
  }

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      const response = await fetch("/api/admin/startup-checklist", { credentials: "same-origin", cache: "no-store" });
      if (response.ok) render(await response.json());
    } catch (_) {
      /* checklist facultative : silence */
    }
  });
})();
