// Parc : stocks des ressources suivies par quantité (niveaux par taille, réception / ajustement / perte, seuil d'alerte, historique).
// S'appuie sur parc.js (parcEl, parcEsc, parcDate, parcCsrf, parcCanManage) ; initParcStock() est appelée par parc.js.

// Définitions en objet : ajouter un type de mouvement manuel = ajouter une entrée.
const STOCK_KINDS = {
  receipt: { label: "Réception", title: "Réception de stock", quantityHint: "Nombre d'exemplaires reçus", noteRequired: false, min: 1 },
  adjustment: { label: "Ajustement", title: "Ajustement d'inventaire", quantityHint: "Écart constaté (négatif pour retirer)", noteRequired: true, min: null },
  loss: { label: "Perte", title: "Perte ou casse en stock", quantityHint: "Nombre d'exemplaires perdus", noteRequired: false, min: 1 }
};
const STOCK_MOVEMENT_LABELS = {
  receipt: "Réception", adjustment: "Ajustement d'inventaire", loss: "Perte / casse en stock", assigned: "Remise à un agent",
  assign_correction: "Correction de quantité", returned: "Retour en stock", returned_degraded: "Retour dégradé (hors stock)",
  lost_by_holder: "Non restitué", released: "Dossier supprimé : remise annulée"
};
const STOCK_ERRORS = {
  invalid_quantity: "Quantité invalide.", note_required: "Justifiez l'ajustement par une note.",
  invalid_threshold: "Seuil invalide.", not_quantity_resource: "Cette ressource n'est pas suivie par quantité.", forbidden: "Action non autorisée."
};

let stockLevels = [];
let stockDialog = null; // { mode: "kind" | "threshold" | "history", code, kind }

function stockLevel(code) { return stockLevels.find((level) => level.resource_code === code); }

function stockChips(level) {
  const chips = [];
  if (level.inconsistent) chips.push('<span class="status-chip status-chip--cancelled">Stock négatif : à vérifier</span>');
  if (level.low) chips.push('<span class="status-chip status-chip--partial_assignment">Stock bas</span>');
  return chips.join(" ");
}

function stockCardHtml(level) {
  const rows = level.variants.length ? level.variants : [{ variant: "", on_hand: 0, held: 0, last_movement: "" }];
  const actions = parcCanManage ? Object.entries(STOCK_KINDS).map(([kind, meta]) =>
    `<button class="btn btn-sm btn-outline-primary" type="button" data-stock-kind="${kind}" data-stock-code="${parcEsc(level.resource_code)}">${meta.label}</button>`).join("")
    + `<button class="btn btn-sm btn-outline-secondary" type="button" data-stock-threshold="${parcEsc(level.resource_code)}">Seuil</button>` : "";
  return `
    <article class="border rounded p-3 mb-3">
      <div class="d-flex flex-wrap justify-content-between gap-2 mb-2">
        <div>
          <strong>${parcEsc(level.label)}</strong> ${stockChips(level)}
          <div class="small text-muted">${level.on_hand} en stock · ${level.held} chez des agents · seuil d'alerte ${level.threshold === null ? "non défini" : level.threshold}</div>
        </div>
        <div class="draft-actions">${actions}
          <button class="btn btn-sm btn-outline-secondary" type="button" data-stock-history="${parcEsc(level.resource_code)}">Historique</button>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead><tr><th>${level.has_variant ? "Taille / variante" : "Stock"}</th><th class="text-end">En stock</th><th class="text-end">Chez des agents</th><th>Dernier mouvement</th></tr></thead>
          <tbody>${rows.map((row) => `
            <tr><td>${parcEsc(row.variant || (level.has_variant ? "Sans taille" : "Total"))}</td>
              <td class="text-end${row.on_hand < 0 ? " text-danger fw-bold" : ""}">${row.on_hand}</td>
              <td class="text-end">${row.held}</td><td>${parcEsc(parcDate(row.last_movement))}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>
    </article>`;
}

function renderParcStock() {
  const section = parcEl("parcStock");
  if (!section) return;
  section.classList.toggle("d-none", !stockLevels.length);
  parcEl("parcStockBody").innerHTML = stockLevels.map(stockCardHtml).join("");
}

async function loadParcStock() {
  const response = await fetch("/api/stock", { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) return;
  stockLevels = (await response.json()).resources || [];
  renderParcStock();
}

function stockOpenDialog(dialog, title, bodyHtml) {
  stockDialog = dialog;
  parcEl("stockModalTitle").textContent = title;
  parcEl("stockModalBody").innerHTML = bodyHtml;
  const modal = parcEl("stockModal");
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
}

function closeStockModal() {
  const modal = parcEl("stockModal");
  modal.classList.add("d-none");
  modal.setAttribute("aria-hidden", "true");
  stockDialog = null;
}

function stockErrorHtml() { return '<div class="alert alert-danger small d-none" id="stockError" role="alert"></div>'; }

function stockShowError(message) {
  const box = parcEl("stockError");
  box.textContent = message;
  box.classList.remove("d-none");
}

function openStockKind(code, kind) {
  const level = stockLevel(code);
  const meta = STOCK_KINDS[kind];
  const variants = (level?.variants || []).map((row) => row.variant).filter(Boolean);
  stockOpenDialog({ mode: "kind", code, kind }, `${meta.title} · ${level?.label || code}`, `
    ${stockErrorHtml()}
    ${level?.has_variant ? `<div class="mb-3"><label class="form-label" for="stockVariant">Taille / variante</label>
      <input class="form-control" id="stockVariant" list="stockVariants" autocomplete="off" placeholder="Ex. M">
      <datalist id="stockVariants">${variants.map((variant) => `<option value="${parcEsc(variant)}">`).join("")}</datalist></div>` : ""}
    <div class="mb-3"><label class="form-label" for="stockQuantity">${parcEsc(meta.quantityHint)}</label>
      <input class="form-control" id="stockQuantity" type="number" step="1"${meta.min === null ? "" : ` min="${meta.min}"`} required></div>
    <div class="mb-3"><label class="form-label" for="stockNote">Note${meta.noteRequired ? " (obligatoire)" : " (facultative)"}</label>
      <input class="form-control" id="stockNote" maxlength="300" autocomplete="off"></div>
    <button class="btn btn-primary" type="button" data-stock-submit="true">Enregistrer</button>`);
}

function openStockThreshold(code) {
  const level = stockLevel(code);
  stockOpenDialog({ mode: "threshold", code }, `Seuil d'alerte · ${level?.label || code}`, `
    ${stockErrorHtml()}
    <p class="small text-muted">Une alerte « Stock bas » s'affiche quand le total en stock atteint ce seuil. Laissez vide pour ne pas être alerté.</p>
    <div class="mb-3"><label class="form-label" for="stockThreshold">Seuil (nombre d'exemplaires)</label>
      <input class="form-control" id="stockThreshold" type="number" min="0" step="1" value="${level?.threshold ?? ""}"></div>
    <button class="btn btn-primary" type="button" data-stock-submit="true">Enregistrer</button>`);
}

async function openStockHistory(code) {
  const level = stockLevel(code);
  stockOpenDialog({ mode: "history", code }, `Historique · ${level?.label || code}`, '<p class="text-muted">Chargement…</p>');
  const response = await fetch(`/api/stock/${encodeURIComponent(code)}/movements?limit=200`, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) { parcEl("stockModalBody").innerHTML = '<p class="text-danger">Impossible de charger l\'historique.</p>'; return; }
  const movements = (await response.json()).movements || [];
  parcEl("stockModalBody").innerHTML = movements.length ? `
    <div class="table-responsive"><table class="table table-sm align-middle">
      <thead><tr><th>Date</th><th>Mouvement</th><th>Variante</th><th class="text-end">Qté</th><th>Agent / note</th></tr></thead>
      <tbody>${movements.map((move) => `
        <tr><td>${parcEsc(parcDate(move.occurred_at))}</td><td>${parcEsc(STOCK_MOVEMENT_LABELS[move.movement_type] || move.movement_type)}</td>
          <td>${parcEsc(move.variant || "—")}</td>
          <td class="text-end${move.quantity < 0 ? " text-danger" : ""}">${move.quantity > 0 ? "+" : ""}${move.quantity}</td>
          <td>${parcEsc([move.holder_label, move.notes].filter(Boolean).join(" · ") || "—")}</td></tr>`).join("")}
      </tbody></table></div>` : '<p class="text-muted">Aucun mouvement.</p>';
}

async function submitStockDialog() {
  const dialog = stockDialog;
  if (!dialog) return;
  let url, method, body;
  if (dialog.mode === "kind") {
    const meta = STOCK_KINDS[dialog.kind];
    const quantity = parseInt(parcEl("stockQuantity").value, 10);
    const note = parcEl("stockNote").value.trim();
    if (!Number.isInteger(quantity) || quantity === 0 || (meta.min !== null && quantity < meta.min)) return stockShowError(STOCK_ERRORS.invalid_quantity);
    if (meta.noteRequired && !note) return stockShowError(STOCK_ERRORS.note_required);
    url = `/api/stock/${encodeURIComponent(dialog.code)}/movements`;
    method = "POST";
    body = { kind: dialog.kind, quantity, variant: parcEl("stockVariant")?.value.trim() || "", notes: note };
  } else if (dialog.mode === "threshold") {
    url = `/api/stock/${encodeURIComponent(dialog.code)}/threshold`;
    method = "PUT";
    body = { threshold: parcEl("stockThreshold").value.trim() };
  } else {
    return;
  }
  const response = await fetch(url, {
    method, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": await parcCsrf() }, body: JSON.stringify(body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return stockShowError(STOCK_ERRORS[data.error] || data.message || `Erreur ${response.status}`);
  stockLevels = data.resources || stockLevels;
  renderParcStock();
  closeStockModal();
  showToast("Stock mis à jour.", "success");
}

function initParcStock() {
  if (!parcEl("parcStock")) return;
  loadParcStock();
  document.addEventListener("click", (event) => {
    const kind = event.target.closest("[data-stock-kind]");
    if (kind) return openStockKind(kind.dataset.stockCode, kind.dataset.stockKind);
    const threshold = event.target.closest("[data-stock-threshold]");
    if (threshold) return openStockThreshold(threshold.dataset.stockThreshold);
    const history = event.target.closest("[data-stock-history]");
    if (history) return openStockHistory(history.dataset.stockHistory);
    if (event.target.closest("[data-stock-submit]")) return submitStockDialog();
    if (event.target.closest("[data-stock-close]")) return closeStockModal();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && stockDialog) closeStockModal(); });
}
