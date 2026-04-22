// Parc mutualisé — gestion des pools d'équipements partagés.

let _pools = [];
let _canManage = false;
let _csrfToken = "";

const ITEM_TYPE_LABELS = {
  ordinateur: "PC portable",
  clavier: "Clavier",
  souris: "Souris",
  ecran: "Écran",
  saccoche: "Saccoche / Housse",
  autre: "Autre",
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const [sessionRes, tokenRes] = await Promise.all([
      fetch("/api/session", { credentials: "same-origin" }),
      fetch("/api/csrf-token", { credentials: "same-origin" }),
    ]);
    if (!sessionRes.ok) { window.location.href = "/login"; return; }
    const me = await sessionRes.json();
    const tokenData = await tokenRes.json();
    _csrfToken = tokenData.token || tokenData.csrf_token || "";

    const perms = me.permissions || [];
    _canManage = perms.includes("pools.manage") || perms.includes("*");

    if (_canManage) {
      document.getElementById("newPoolBtn")?.classList.remove("d-none");
      document.getElementById("newPoolBtnEmpty")?.classList.remove("d-none");
    }

    await loadPools();
    bindPoolModal();
    bindItemModal();
    bindMemberModal();
    bindLinkModal();
  } catch (e) {
    console.error(e);
  }
});

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiJson(url, method = "GET", body = null) {
  const opts = {
    method,
    credentials: "same-origin",
    headers: { "X-CSRF-Token": _csrfToken },
  };
  if (body !== null) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error || r.statusText);
  }
  return r.json();
}

// ---------------------------------------------------------------------------
// Load & render
// ---------------------------------------------------------------------------

async function loadPools() {
  _pools = await apiJson("/api/pools");
  renderPools();
  document.getElementById("poolsCountValue").textContent = _pools.length;
}

function renderPools() {
  const container = document.getElementById("poolsList");
  const empty = document.getElementById("poolsEmptyState");
  if (!_pools.length) {
    container.innerHTML = "";
    empty.classList.remove("d-none");
    return;
  }
  empty.classList.add("d-none");
  container.innerHTML = _pools.map(renderPoolCard).join("");
  container.querySelectorAll("[data-pool-edit]").forEach((btn) =>
    btn.addEventListener("click", () => openPoolModal(_pools.find((p) => p.id === btn.dataset.poolEdit)))
  );
  container.querySelectorAll("[data-pool-delete]").forEach((btn) =>
    btn.addEventListener("click", () => deletePool(btn.dataset.poolDelete))
  );
  container.querySelectorAll("[data-item-add]").forEach((btn) =>
    btn.addEventListener("click", () => openItemModal(btn.dataset.itemAdd, null))
  );
  container.querySelectorAll("[data-item-edit]").forEach((btn) => {
    const pool = _pools.find((p) => p.id === btn.dataset.itemPool);
    const item = pool?.items.find((i) => i.id === Number(btn.dataset.itemEdit));
    btn.addEventListener("click", () => openItemModal(btn.dataset.itemPool, item));
  });
  container.querySelectorAll("[data-item-delete]").forEach((btn) =>
    btn.addEventListener("click", () => deleteItem(btn.dataset.itemPool, btn.dataset.itemDelete))
  );
  container.querySelectorAll("[data-member-add]").forEach((btn) =>
    btn.addEventListener("click", () => openMemberModal(btn.dataset.memberAdd))
  );
  container.querySelectorAll("[data-member-link]").forEach((btn) =>
    btn.addEventListener("click", () => openLinkModal(btn.dataset.memberLink, btn.dataset.memberId))
  );
  container.querySelectorAll("[data-member-delete]").forEach((btn) =>
    btn.addEventListener("click", () => deleteMember(btn.dataset.memberPool, btn.dataset.memberDelete))
  );
}

function renderPoolCard(pool) {
  const manageButtons = _canManage
    ? `<button class="btn btn-sm btn-outline-secondary" data-pool-edit="${escHtml(pool.id)}">Modifier</button>
       <button class="btn btn-sm btn-outline-danger" data-pool-delete="${escHtml(pool.id)}">Supprimer</button>`
    : "";

  const itemsHtml = pool.items.length
    ? pool.items.map((item) => `
      <tr>
        <td><span class="badge bg-secondary">${escHtml(ITEM_TYPE_LABELS[item.resource_type] || item.resource_type)}</span></td>
        <td>${escHtml(item.label)}</td>
        <td class="text-muted">${item.serial_number ? escHtml(item.serial_number) : "—"}</td>
        <td class="text-muted small">${item.notes ? escHtml(item.notes) : ""}</td>
        <td class="text-end">${_canManage ? `
          <button class="btn btn-xs btn-outline-secondary me-1" data-item-edit="${item.id}" data-item-pool="${escHtml(pool.id)}">Modifier</button>
          <button class="btn btn-xs btn-outline-danger" data-item-delete="${item.id}" data-item-pool="${escHtml(pool.id)}">Retirer</button>` : ""}</td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="text-muted text-center py-2">Aucun équipement</td></tr>`;

  const membersHtml = pool.members.length
    ? pool.members.map((m) => `
      <li class="pool-member">
        <span class="pool-member__name">${escHtml(m.beneficiary_name || "—")}</span>
        ${m.service ? `<span class="pool-member__service">${escHtml(m.service)}</span>` : ""}
        ${m.form_id
          ? `<a class="pool-member__link" href="form.html?id=${escHtml(m.form_id)}" target="_blank">Voir le dossier</a>`
          : (_canManage ? `<button class="btn btn-xs btn-outline-secondary pool-member__link" data-member-link="${escHtml(pool.id)}" data-member-id="${m.id}">Lier un dossier</button>` : `<span class="text-muted small">Sans dossier</span>`)
        }
        ${_canManage ? `<button class="btn btn-xs btn-outline-danger ms-auto" data-member-delete="${m.id}" data-member-pool="${escHtml(pool.id)}">Retirer</button>` : ""}
      </li>`).join("")
    : `<li class="text-muted small py-1">Aucun utilisateur</li>`;

  return `
<div class="pool-card content-card mb-3" data-pool-id="${escHtml(pool.id)}">
  <div class="pool-card__header">
    <div>
      <h4 class="pool-card__title">${escHtml(pool.label)}</h4>
      ${pool.notes ? `<p class="pool-card__notes">${escHtml(pool.notes)}</p>` : ""}
    </div>
    <div class="pool-card__actions">
      ${manageButtons}
    </div>
  </div>

  <div class="pool-card__body">
    <div class="pool-card__section">
      <div class="pool-card__section-header">
        <p class="panel-eyebrow mb-0">Équipements</p>
        ${_canManage ? `<button class="btn btn-xs btn-outline-primary" data-item-add="${escHtml(pool.id)}">+ Ajouter</button>` : ""}
      </div>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <tbody>${itemsHtml}</tbody>
        </table>
      </div>
    </div>

    <div class="pool-card__section">
      <div class="pool-card__section-header">
        <p class="panel-eyebrow mb-0">Utilisateurs <span class="badge bg-secondary">${pool.members.length}</span></p>
        ${_canManage ? `<button class="btn btn-xs btn-outline-primary" data-member-add="${escHtml(pool.id)}">+ Ajouter</button>` : ""}
      </div>
      <ul class="pool-members-list">${membersHtml}</ul>
    </div>
  </div>
</div>`;
}

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Modal parc
// ---------------------------------------------------------------------------

function bindPoolModal() {
  document.getElementById("newPoolBtn")?.addEventListener("click", () => openPoolModal(null));
  document.getElementById("newPoolBtnEmpty")?.addEventListener("click", () => openPoolModal(null));
  document.getElementById("poolModalSaveBtn")?.addEventListener("click", savePool);
}

function openPoolModal(pool) {
  document.getElementById("poolModalId").value = pool?.id || "";
  document.getElementById("poolModalLabel2").value = pool?.label || "";
  document.getElementById("poolModalNotes").value = pool?.notes || "";
  document.getElementById("poolModalLabel").textContent = pool ? "Modifier le parc" : "Nouveau parc";
  const modal = bootstrap.Modal.getOrCreate(document.getElementById("poolModal"));
  modal.show();
  setTimeout(() => document.getElementById("poolModalLabel2").focus(), 300);
}

async function savePool() {
  const id = document.getElementById("poolModalId").value;
  const label = document.getElementById("poolModalLabel2").value.trim();
  const notes = document.getElementById("poolModalNotes").value.trim();
  if (!label) { alert("Le nom du parc est requis."); return; }
  try {
    if (id) {
      await apiJson(`/api/pools/${id}`, "PUT", { label, notes });
    } else {
      await apiJson("/api/pools", "POST", { label, notes });
    }
    bootstrap.Modal.getInstance(document.getElementById("poolModal"))?.hide();
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

async function deletePool(poolId) {
  const pool = _pools.find((p) => p.id === poolId);
  if (!pool) return;
  if (!confirm(`Supprimer le parc « ${pool.label} » et tout son contenu ?`)) return;
  try {
    await apiJson(`/api/pools/${poolId}`, "DELETE");
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Modal équipement
// ---------------------------------------------------------------------------

function bindItemModal() {
  document.getElementById("itemModalSaveBtn")?.addEventListener("click", saveItem);
}

function openItemModal(poolId, item) {
  document.getElementById("itemModalPoolId").value = poolId;
  document.getElementById("itemModalItemId").value = item?.id || "";
  document.getElementById("itemModalType").value = item?.resource_type || "";
  document.getElementById("itemModalLabel2").value = item?.label || "";
  document.getElementById("itemModalSerial").value = item?.serial_number || "";
  document.getElementById("itemModalNotes").value = item?.notes || "";
  document.getElementById("itemModalLabel").textContent = item ? "Modifier l'équipement" : "Ajouter un équipement";
  bootstrap.Modal.getOrCreate(document.getElementById("itemModal")).show();
}

async function saveItem() {
  const poolId = document.getElementById("itemModalPoolId").value;
  const itemId = document.getElementById("itemModalItemId").value;
  const resource_type = document.getElementById("itemModalType").value;
  const label = document.getElementById("itemModalLabel2").value.trim();
  const serial_number = document.getElementById("itemModalSerial").value.trim();
  const notes = document.getElementById("itemModalNotes").value.trim();
  if (!resource_type || !label) { alert("Le type et le libellé sont requis."); return; }
  try {
    if (itemId) {
      await apiJson(`/api/pools/${poolId}/items/${itemId}`, "PUT", { resource_type, label, serial_number, notes });
    } else {
      await apiJson(`/api/pools/${poolId}/items`, "POST", { resource_type, label, serial_number, notes });
    }
    bootstrap.Modal.getInstance(document.getElementById("itemModal"))?.hide();
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

async function deleteItem(poolId, itemId) {
  if (!confirm("Retirer cet équipement du parc ?")) return;
  try {
    await apiJson(`/api/pools/${poolId}/items/${itemId}`, "DELETE");
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Modal membre
// ---------------------------------------------------------------------------

function bindMemberModal() {
  document.getElementById("memberModalSaveBtn")?.addEventListener("click", saveMember);
  bindFormSearch("memberModalFormSearch", "memberModalFormResults", "memberModalFormId", "memberModalFormChosen", "memberModalName");
}

function openMemberModal(poolId) {
  document.getElementById("memberModalPoolId").value = poolId;
  document.getElementById("memberModalFormSearch").value = "";
  document.getElementById("memberModalFormResults").classList.add("d-none");
  document.getElementById("memberModalFormId").value = "";
  document.getElementById("memberModalFormChosen").classList.add("d-none");
  document.getElementById("memberModalName").value = "";
  bootstrap.Modal.getOrCreate(document.getElementById("memberModal")).show();
}

async function saveMember() {
  const pool_id = document.getElementById("memberModalPoolId").value;
  const form_id = document.getElementById("memberModalFormId").value || null;
  const beneficiary_name = document.getElementById("memberModalName").value.trim() || null;
  if (!form_id && !beneficiary_name) { alert("Sélectionnez un dossier ou saisissez un nom."); return; }
  try {
    await apiJson(`/api/pools/${pool_id}/members`, "POST", { form_id, beneficiary_name });
    bootstrap.Modal.getInstance(document.getElementById("memberModal"))?.hide();
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

async function deleteMember(poolId, memberId) {
  if (!confirm("Retirer cet utilisateur du parc ?")) return;
  try {
    await apiJson(`/api/pools/${poolId}/members/${memberId}`, "DELETE");
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Modal liaison dossier
// ---------------------------------------------------------------------------

function bindLinkModal() {
  document.getElementById("linkModalSaveBtn")?.addEventListener("click", saveLinkMember);
  bindFormSearch("linkModalSearch", "linkModalResults", "linkModalFormId", "linkModalChosen", null);
}

function openLinkModal(poolId, memberId) {
  document.getElementById("linkModalPoolId").value = poolId;
  document.getElementById("linkModalMemberId").value = memberId;
  document.getElementById("linkModalSearch").value = "";
  document.getElementById("linkModalResults").classList.add("d-none");
  document.getElementById("linkModalFormId").value = "";
  document.getElementById("linkModalChosen").classList.add("d-none");
  bootstrap.Modal.getOrCreate(document.getElementById("linkModal")).show();
}

async function saveLinkMember() {
  const pool_id = document.getElementById("linkModalPoolId").value;
  const member_id = document.getElementById("linkModalMemberId").value;
  const form_id = document.getElementById("linkModalFormId").value;
  if (!form_id) { alert("Sélectionnez un dossier."); return; }
  try {
    await apiJson(`/api/pools/${pool_id}/members/${member_id}`, "PUT", { form_id });
    bootstrap.Modal.getInstance(document.getElementById("linkModal"))?.hide();
    await loadPools();
  } catch (e) {
    alert(`Erreur : ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Recherche dossier (partagée entre modals)
// ---------------------------------------------------------------------------

function bindFormSearch(inputId, resultsId, hiddenId, chosenId, clearInputId) {
  const input = document.getElementById(inputId);
  const results = document.getElementById(resultsId);
  const hidden = document.getElementById(hiddenId);
  const chosen = document.getElementById(chosenId);
  if (!input) return;

  let debounce = null;
  input.addEventListener("input", () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (q.length < 2) { results.classList.add("d-none"); return; }
    debounce = setTimeout(() => searchForms(q, results, hidden, chosen, input, clearInputId), 280);
  });
}

async function searchForms(q, resultsEl, hiddenEl, chosenEl, inputEl, clearInputId) {
  try {
    const data = await apiJson(`/api/forms?search=${encodeURIComponent(q)}`);
    const rows = (Array.isArray(data) ? data : data.items || []).slice(0, 8);
    if (!rows.length) { resultsEl.innerHTML = '<div class="pool-form-result pool-form-result--empty">Aucun dossier trouvé</div>'; resultsEl.classList.remove("d-none"); return; }
    resultsEl.innerHTML = rows.map((f) =>
      `<div class="pool-form-result" data-id="${escHtml(f.id)}" data-name="${escHtml(`${f.prenom} ${f.nom}`)}">
        <strong>${escHtml(f.prenom)} ${escHtml(f.nom)}</strong>
        ${f.service ? `<span class="text-muted"> — ${escHtml(f.service)}</span>` : ""}
      </div>`
    ).join("");
    resultsEl.classList.remove("d-none");
    resultsEl.querySelectorAll(".pool-form-result[data-id]").forEach((row) => {
      row.addEventListener("click", () => {
        hiddenEl.value = row.dataset.id;
        inputEl.value = "";
        resultsEl.classList.add("d-none");
        if (clearInputId) document.getElementById(clearInputId).value = "";
        if (chosenEl) {
          chosenEl.textContent = row.dataset.name;
          chosenEl.classList.remove("d-none");
        }
      });
    });
  } catch (e) {
    console.error(e);
  }
}
