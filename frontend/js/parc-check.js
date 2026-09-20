// Parc : « À vérifier » = lignes attribuées sans identifiant (absentes du parc) et doublons probables d'identifiants.
// S'appuie sur parc.js (parcEl, parcEsc, parcChip, parcCsrf, parcCanManage, loadParc, loadParcStats) ; initParcCheck() est appelée par parc.js.

// Libellés du statut d'un DOSSIER (défini en objet : ajouter un statut = ajouter une entrée).
const CHECK_FORM_STATUS = {
  draft: "Brouillon", awaiting_signature: "En attente de signature", partial_assignment: "Attribution partielle",
  active: "Attribué", partial_return: "Restitution partielle", returned: "Restitué"
};

let checkData = { incomplete: [], duplicates: [] };

function checkIncompleteHtml(lines) {
  if (!lines.length) return "";
  const shown = lines.slice(0, 100);
  return `
    <h3 class="h6 mt-3">Lignes attribuées sans identifiant <span class="text-muted fw-normal">(${lines.length}) — absentes du parc</span></h3>
    <p class="small text-muted">Ces ressources sont suivies objet par objet, mais aucun numéro (série, badge, immatriculation…) n'a été saisi dans le dossier : elles n'apparaissent donc pas dans le parc. Ouvrez le dossier pour compléter l'identifiant.</p>
    <div class="table-responsive"><table class="table table-sm align-middle">
      <thead><tr><th>Ressource</th><th>Agent</th><th>Dossier</th><th class="text-end"></th></tr></thead>
      <tbody>${shown.map((line) => `
        <tr><td>${parcEsc(line.resource_label)}</td><td>${parcEsc(line.holder_label || "—")}</td>
          <td>${parcEsc(CHECK_FORM_STATUS[line.status] || line.status)}</td>
          <td class="text-end"><a class="btn btn-sm btn-outline-primary" href="form.html?id=${encodeURIComponent(line.form_id)}">Ouvrir le dossier</a></td></tr>`).join("")}
      </tbody></table></div>
    ${lines.length > shown.length ? `<p class="small text-muted">${lines.length - shown.length} autre(s) ligne(s) non affichée(s).</p>` : ""}`;
}

function checkDuplicatesHtml(groups) {
  if (!groups.length) return "";
  return `
    <h3 class="h6 mt-4">Doublons probables <span class="text-muted fw-normal">(${groups.length})</span></h3>
    <p class="small text-muted">Ces identifiants se ressemblent (« Badge 40 » et « 40 » par exemple) : il s'agit peut-être du même objet saisi de deux façons. Choisissez celui à <strong>conserver</strong> : l'autre y est fusionné et son historique est repris.</p>
    ${groups.map((group, index) => `
      <article class="border rounded p-3 mb-2">
        <div class="fw-semibold mb-2">${parcEsc(group.resource_label)} · numéro « ${parcEsc(group.key)} »</div>
        <ul class="list-unstyled mb-0">${group.units.map((unit) => `
          <li class="d-flex flex-wrap align-items-center gap-2 py-1">
            <code>${parcEsc(unit.identifier)}</code> ${parcChip(unit.status)}
            <span class="small text-muted">${parcEsc(unit.holder_label || "")}</span>
            ${parcCanManage ? `<button class="btn btn-sm btn-outline-primary ms-auto" type="button" data-check-keep="${parcEsc(unit.id)}" data-check-group="${index}">Conserver celui-ci</button>` : ""}
          </li>`).join("")}
        </ul>
      </article>`).join("")}`;
}

function renderParcCheck() {
  const panel = parcEl("parcCheck");
  if (!panel) return;
  const total = checkData.incomplete.length + checkData.duplicates.length;
  panel.classList.toggle("d-none", total === 0);
  parcEl("parcCheckCount").textContent = String(total);
  parcEl("parcCheckBody").innerHTML = checkIncompleteHtml(checkData.incomplete) + checkDuplicatesHtml(checkData.duplicates);
}

async function loadParcCheck() {
  const response = await fetch("/api/units/to-check", { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) return;
  checkData = await response.json();
  renderParcCheck();
}

async function mergeDuplicateGroup(groupIndex, keepId) {
  const group = checkData.duplicates[groupIndex];
  const keep = group?.units.find((unit) => unit.id === keepId);
  if (!keep) return;
  const others = group.units.filter((unit) => unit.id !== keepId);
  const names = others.map((unit) => `« ${unit.identifier} »`).join(", ");
  if (!(await askConfirm(`Conserver « ${keep.identifier} » et y fusionner ${names} ? Les fiches fusionnées disparaissent, leur historique est repris sur « ${keep.identifier} ».`, { confirmLabel: "Fusionner" }))) return;
  for (const other of others) {
    const response = await fetch(`/api/units/${encodeURIComponent(other.id)}/actions`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": await parcCsrf() },
      body: JSON.stringify({ action: "merge", target_unit_id: keepId, notes: "Fusion de doublon probable" })
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      showToast(data.message || `Fusion impossible (erreur ${response.status}).`, "error");
      break;
    }
  }
  await loadParcCheck();
  if (typeof loadParc === "function") loadParc();
  if (typeof loadParcStats === "function") loadParcStats();
  showToast("Doublon fusionné.", "success");
}

function initParcCheck() {
  if (!parcEl("parcCheck")) return;
  loadParcCheck();
  parcEl("parcCheck").addEventListener("click", (event) => {
    const keep = event.target.closest("[data-check-keep]");
    if (keep) mergeDuplicateGroup(Number(keep.dataset.checkGroup), keep.dataset.checkKeep);
  });
}
