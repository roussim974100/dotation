async function requestJson(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const csrfHeaders = {};
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && typeof getCsrfToken === "function") {
    csrfHeaders["X-CSRF-Token"] = await getCsrfToken();
  }
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...csrfHeaders, ...(options.headers || {}) },
    credentials: "same-origin",
    ...options
  });
  if (!response.ok) {
    let payload = null;
    try { payload = await response.json(); } catch (e) { payload = null; }
    const err = new Error(payload?.message || payload?.error || `HTTP ${response.status}`);
    err.status = response.status;
    throw err;
  }
  return response.status === 204 ? null : response.json();
}

function todayDateInputValue() {
  return new Date().toISOString().slice(0, 10);
}

function getEl(id) { return document.getElementById(id); }

function updateDateOrderWarning() {
  const missionEnd = getEl("p1_mission_end_at")?.value;
  const returnedAt = getEl("p1_returned_at")?.value;
  const warn = getEl("p1DateOrderWarning");
  if (warn) warn.classList.toggle("d-none", !(missionEnd && returnedAt && returnedAt < missionEnd));
}

function applyPhase1ValidatedState(restitution, unlockDays, id) {
  const validatedAt = restitution?.phase1ValidatedAt;
  const validatedBy = restitution?.phase1ValidatedBy;
  const badge = getEl("phase1ValidatedBadge");
  const modifyBar = getEl("phase1ModifyBar");
  const meta = getEl("phase1ValidatedMeta");
  const hint = getEl("phase1ActionHint");
  const saveBtn = getEl("savePhase1Btn");
  const validateBtn = getEl("validatePhase1Btn");
  const goBtn = getEl("goToPhase2Btn");

  if (goBtn) goBtn.href = `restitution.html?id=${encodeURIComponent(id)}`;

  if (validatedAt) {
    badge?.classList.remove("d-none");
    modifyBar?.classList.remove("d-none");
    saveBtn?.classList.add("d-none");
    validateBtn?.classList.add("d-none");
    if (hint) hint.textContent = "Phase 1 validée. Les services peuvent maintenant saisir l'état du matériel.";
    const d = new Date(validatedAt).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    if (meta) meta.textContent = `Validée le ${d} par ${validatedBy || "inconnu"}`;
    ["p1_mission_end_at", "p1_returned_at", "p1_return_reason", "p1_return_notes"].forEach(fid => {
      const el = getEl(fid);
      if (el) el.disabled = true;
    });
  } else {
    badge?.classList.add("d-none");
    modifyBar?.classList.add("d-none");
    saveBtn?.classList.remove("d-none");
    validateBtn?.classList.remove("d-none");
    ["p1_mission_end_at", "p1_returned_at", "p1_return_reason", "p1_return_notes"].forEach(fid => {
      const el = getEl(fid);
      if (el) el.disabled = false;
    });
  }
}

function buildPhase1Patch(keepPending = true) {
  return {
    missionEndAt: getEl("p1_mission_end_at")?.value || "",
    returnedAt: getEl("p1_returned_at")?.value || "",
    reason: getEl("p1_return_reason")?.value || "",
    notes: getEl("p1_return_notes")?.value.trim() || "",
    keepPending,
  };
}

async function initPhase1Page() {
  const loader = getEl("phase1Loader");
  try {
    loader?.classList.remove("is-hidden");
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");
    if (!id) { alert("Aucune fiche sélectionnée."); window.location.href = "index.html"; return; }

    const result = await requestJson(`/api/forms/${encodeURIComponent(id)}`);
    if (!result?.data) { alert("Fiche introuvable."); window.location.href = "index.html"; return; }

    const status = result.summary?.status || result.data?.workflow?.status;
    if (!["active", "partial_return", "awaiting_signature", "returned"].includes(status)) {
      alert("Ce dossier n'est pas en phase de restitution.");
      window.location.href = "index.html";
      return;
    }

    // Si Phase 1 déjà validée et dossier non terminé → aller directement à Phase 2
    const currentRestitutionCheck = result.data.restitution || {};
    if (currentRestitutionCheck.phase1ValidatedAt && status !== "returned") {
      window.location.href = `restitution.html?id=${encodeURIComponent(id)}`;
      return;
    }

    // Hydrater l'en-tête
    const b = result.data.beneficiaire || {};
    if (getEl("phase1Title")) getEl("phase1Title").textContent = `${b.nom || ""} ${b.prenom || ""}`.trim() || "Dossier";
    if (getEl("phase1Subtitle")) getEl("phase1Subtitle").textContent = b.service || b.mandat || "Fiche active";
    const statusLabels = { active: "Attribution active", partial_return: "Restitution partielle", awaiting_signature: "En attente de signature", returned: "Restitution terminée" };
    if (getEl("phase1StatusPill")) getEl("phase1StatusPill").textContent = statusLabels[status] || status;

    // Hydrater les champs
    let currentRestitution = currentRestitutionCheck;
    if (getEl("p1_mission_end_at")) getEl("p1_mission_end_at").value = currentRestitution.missionEndAt || "";
    if (getEl("p1_returned_at")) getEl("p1_returned_at").value = currentRestitution.returnedAt || "";
    if (getEl("p1_return_reason")) getEl("p1_return_reason").value = currentRestitution.reason || "";
    if (getEl("p1_return_notes")) getEl("p1_return_notes").value = currentRestitution.notes || "";
    updateDateOrderWarning();

    getEl("p1_mission_end_at")?.addEventListener("change", updateDateOrderWarning);
    getEl("p1_returned_at")?.addEventListener("change", updateDateOrderWarning);

    // Récupérer la fenêtre de déverrouillage configurée
    const settings = await fetch("/api/settings/public").then(r => r.ok ? r.json() : null);
    const unlockDays = settings?.restitutionPhase1UnlockDays ?? 1;

    applyPhase1ValidatedState(currentRestitution, unlockDays, id);

    // Bouton "Enregistrer" (sans valider)
    getEl("savePhase1Btn")?.addEventListener("click", async () => {
      try {
        const patch = buildPhase1Patch(true);
        await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, { method: "PATCH", body: JSON.stringify(patch) });
        const updated = await requestJson(`/api/forms/${encodeURIComponent(id)}`);
        currentRestitution = updated?.data?.restitution || currentRestitution;
        applyPhase1ValidatedState(currentRestitution, unlockDays, id);
      } catch (e) {
        alert(e.message || "Erreur lors de l'enregistrement.");
      }
    });

    // Bouton "Valider Phase 1"
    getEl("validatePhase1Btn")?.addEventListener("click", async () => {
      const returnedAt = getEl("p1_returned_at")?.value;
      if (!returnedAt) { alert("La date de restitution du matériel est obligatoire pour valider la Phase 1."); return; }
      try {
        const patch = buildPhase1Patch(true);
        await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, { method: "PATCH", body: JSON.stringify(patch) });
        const resp = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution-phase1-validate`, { method: "POST" });
        currentRestitution = resp?.data?.restitution || currentRestitution;
        applyPhase1ValidatedState(currentRestitution, unlockDays, id);
        // Rediriger vers Phase 2 après un court délai
        setTimeout(() => { window.location.href = `restitution.html?id=${encodeURIComponent(id)}`; }, 800);
      } catch (e) {
        alert(e.message || "Erreur lors de la validation.");
      }
    });

    // Bouton "Modifier les dates" → modal unlock
    getEl("unlockPhase1Btn")?.addEventListener("click", () => {
      const validatedAt = currentRestitution?.phase1ValidatedAt;
      const elapsedDays = validatedAt ? (Date.now() - new Date(validatedAt).getTime()) / 86400000 : 0;
      const needsMotif = elapsedDays > unlockDays;
      const modalText = getEl("unlockPhase1ModalText");
      const motifWrap = getEl("unlockPhase1MotifWrap");
      const motifInput = getEl("unlockPhase1Motif");
      const errorEl = getEl("unlockPhase1Error");
      if (modalText) modalText.textContent = needsMotif
        ? `La fenêtre de modification libre (${unlockDays} j) est dépassée. Un motif est requis.`
        : "Vous pouvez déverrouiller les dates et les corriger librement.";
      motifWrap?.classList.toggle("d-none", !needsMotif);
      if (motifInput) motifInput.value = "";
      errorEl?.classList.add("d-none");
      new bootstrap.Modal(getEl("unlockPhase1Modal")).show();
    });

    // Confirmation déverrouillage
    getEl("unlockPhase1ConfirmBtn")?.addEventListener("click", async () => {
      const validatedAt = currentRestitution?.phase1ValidatedAt;
      const elapsedDays = validatedAt ? (Date.now() - new Date(validatedAt).getTime()) / 86400000 : 0;
      const needsMotif = elapsedDays > unlockDays;
      const motif = getEl("unlockPhase1Motif")?.value.trim() || "";
      const errorEl = getEl("unlockPhase1Error");
      if (needsMotif && !motif) {
        if (errorEl) { errorEl.textContent = "Le motif est obligatoire."; errorEl.classList.remove("d-none"); }
        return;
      }
      try {
        const resp = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution-phase1-unlock`, { method: "POST", body: JSON.stringify({ motif }) });
        currentRestitution = resp?.data?.restitution || currentRestitution;
        bootstrap.Modal.getInstance(getEl("unlockPhase1Modal"))?.hide();
        applyPhase1ValidatedState(currentRestitution, unlockDays, id);
      } catch (e) {
        if (errorEl) { errorEl.textContent = e.message || "Erreur lors du déverrouillage."; errorEl.classList.remove("d-none"); }
      }
    });

  } finally {
    loader?.classList.add("is-hidden");
  }
}

document.addEventListener("DOMContentLoaded", initPhase1Page);
