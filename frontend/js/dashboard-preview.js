// Aperçus au survol (hover) des colonnes Avancement et Pilotage du tableau de bord.
// Dépend de getDraftById, escapeHtml, formatShortDate, getTimingOffsetLabel,
// collectRequestedResourcesFromPayload définis dans storage.js.
// Chargé après storage.js — toutes les fonctions appelées sont disponibles au runtime.

function buildDotationPreview(data) {
  // Petit résumé lisible utilisé dans le hover de l'état.
  if (!data) {
    return [];
  }

  const items = [];
  const pushItem = (label, detail) => {
    items.push(detail ? `${label} : ${detail}` : label);
  };

  // Ressources dynamiques (nouveau format)
  for (const resource of data.resources?.additional || []) {
    if (!resource.selected) continue;
    const fields = resource.fields || {};
    const fieldValues = Object.values(fields).map((v) => Array.isArray(v) ? v.join(", ") : String(v || "")).filter(Boolean);
    pushItem(resource.label || "Ressource", resource.details || fieldValues.join(" - "));
  }

  // Fallback pour les anciens dossiers avec materiel/immateriel hardcodé
  if (!items.length) {
    const OLD_META = new Set(["selected", "assignedAt", "label", "details"]);
    const materiel = data.materiel || {};
    const immateriel = data.immateriel || {};
    for (const [key, item] of Object.entries(materiel)) {
      if (item?.selected) {
        const label = item.label || key;
        const parts = Object.entries(item)
          .filter(([k]) => !OLD_META.has(k))
          .map(([, v]) => String(v || "").trim())
          .filter(Boolean);
        pushItem(label, item.details || parts.join(" · ") || "");
      }
    }
    for (const [key, item] of Object.entries(immateriel)) {
      if (item?.selected) {
        const label = item.label || key;
        const parts = Object.entries(item)
          .filter(([k]) => !OLD_META.has(k))
          .map(([, v]) => String(v || "").trim())
          .filter(Boolean);
        pushItem(label, item.details || parts.join(" · ") || "");
      }
    }
  }

  // Accès UNC
  const uncAcces = data.unc_acces || [];
  if (uncAcces.length) {
    const uncDetails = uncAcces.map((unc) => unc.chemin || "").filter(Boolean);
    pushItem(`Accès UNC (${uncAcces.length})`, uncDetails.join(", "));
  }

  return items;
}

function buildMissingProgressPreview(data) {
  if (!data) {
    return [];
  }

  const missing = [];
  const workflowStatus = data.workflow?.status || "draft";
  const beneficiaire = data.beneficiaire || {};
  const validation = data.validation || {};
  const resourceErrors = Array.isArray(data.meta?.resourceValidationErrors)
    ? data.meta.resourceValidationErrors.filter(Boolean)
    : [];

  if (!beneficiaire.nom) {
    missing.push("Nom");
  }
  if (!beneficiaire.prenom) {
    missing.push("Prénom");
  }
  if ((beneficiaire.qualite || "agent") === "elu") {
    if (!beneficiaire.mandat) {
      missing.push("Mandat");
    }
  } else if (!beneficiaire.service) {
    missing.push("Service");
  }

  if (!validation.rgpdAccepted) {
    missing.push("Validation RGPD");
  }

  if (!validation.signatureDataUrl && ["draft", "partial_assignment", "awaiting_signature"].includes(workflowStatus)) {
    missing.push("Signature du dossier");
  }

  return [...new Set([...resourceErrors, ...missing])];
}

function getHoverCard() {
  return document.getElementById("statusHoverCard");
}

function hideStatusPreview() {
  const card = getHoverCard();
  if (!card) {
    return;
  }
  card.classList.add("d-none");
}

function positionHoverCard(card, target) {
  const rect = target.getBoundingClientRect();
  const top = Math.min(window.innerHeight - card.offsetHeight - 12, rect.bottom + 10);
  const left = Math.min(window.innerWidth - card.offsetWidth - 12, rect.left);
  card.style.top = `${Math.max(12, top)}px`;
  card.style.left = `${Math.max(12, left)}px`;
}

async function showStatusPreview(target, id) {
  const card = getHoverCard();
  if (!card) {
    return;
  }

  card.innerHTML = '<p class="status-hover-card__hint">Chargement des ressources...</p>';
  card.classList.remove("d-none");
  positionHoverCard(card, target);

  const result = await getDraftById(id);
  if (!result || !result.data) {
    card.innerHTML = '<p class="status-hover-card__hint">Impossible de charger le détail.</p>';
    positionHoverCard(card, target);
    return;
  }
  const previewItems = buildDotationPreview(result.data);
  const missingItems = buildMissingProgressPreview(result.data);
  const sections = [];
  if (previewItems.length) {
    sections.push(`<h4>Ressources attribuées</h4><ul>${previewItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
  }
  if (missingItems.length) {
    sections.push(`<h4>À compléter pour finaliser</h4><ul class="status-hover-card__missing-list">${missingItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
  }
  card.innerHTML = sections.length
    ? sections.join("")
    : '<p class="status-hover-card__hint">Aucune ressource renseignée.</p>';
  positionHoverCard(card, target);
}

function bindStatusPreviews() {
  // Le hover charge à la demande le détail d'une fiche pour éviter d'alourdir la liste initiale.
  document.querySelectorAll("[data-status-preview-id]").forEach((chip) => {
    if (chip.dataset.previewBound) {
      return;
    }
    chip.addEventListener("mouseenter", () => {
      void showStatusPreview(chip, chip.dataset.statusPreviewId);
    });
    chip.addEventListener("mouseleave", hideStatusPreview);
    chip.dataset.previewBound = "true";
  });
}

function buildTimingPreview(data) {
  if (!data) {
    return [];
  }

  const restitution = data.restitution || {};
  const restitutionItems = restitution.items || {};
  const isRestitution = Boolean(
    restitution.returnedAt
    || Object.keys(restitutionItems).length
    || (["returned", "partial_return", "awaiting_signature"].includes(data.workflow?.status) && (restitution.reason || restitution.returnedAt))
  );

  if (isRestitution) {
    return buildRestitutionTimingPreview(data, restitution, restitutionItems);
  }
  return buildAttributionTimingPreview(data);
}

function buildRestitutionTimingPreview(data, restitution, restitutionItems) {
  const sections = [];
  const returnDate = restitution.returnedAt || "";
  if (returnDate) {
    const offsetLabel = getTimingOffsetLabel(returnDate);
    sections.push(`Date de fin de fonction : ${formatShortDate(returnDate)}${offsetLabel ? ` (${offsetLabel})` : ""}`);
  } else {
    sections.push("Date de fin de fonction non renseignée");
  }

  const additional = data.resources?.additional || [];
  const returnedStates = ["returned", "returned_damaged", "transferred", "conforme", "degrade"];

  if (additional.length) {
    // Nouveau format dynamique
    const returnableResources = additional.filter((r) => r.requiresReturn && r.selected);
    const returnedCount = returnableResources.filter((r) => {
      const code = r.id || r.code;
      const item = restitutionItems[code];
      return item && returnedStates.includes(item.state);
    }).length;
    sections.push(`Progression restitution : ${returnedCount}/${returnableResources.length} ressource(s) restituée(s)`);
    const pendingLabels = returnableResources
      .filter((r) => {
        const code = r.id || r.code;
        const item = restitutionItems[code];
        return !item || !returnedStates.includes(item.state);
      })
      .map((r) => r.label || r.id || r.code);
    if (pendingLabels.length) {
      sections.push(`En attente de restitution : ${pendingLabels.join(", ")}`);
    }
  } else {
    // Ancien format (materiel/immateriel hardcodé)
    const materiel = data.materiel || {};
    const immateriel = data.immateriel || {};
    const allOld = [
      ...Object.entries(materiel).filter(([, v]) => v?.selected).map(([k, v]) => ({ key: k, label: v.label || k })),
      ...Object.entries(immateriel).filter(([, v]) => v?.selected).map(([k, v]) => ({ key: k, label: v.label || k })),
    ];
    const returnedCount = allOld.filter(({ key }) => {
      const item = restitutionItems[key];
      return item && returnedStates.includes(item.state);
    }).length;
    sections.push(`Progression restitution : ${returnedCount}/${allOld.length} ressource(s) restituée(s)`);
    const pendingLabels = allOld
      .filter(({ key }) => {
        const item = restitutionItems[key];
        return !item || !returnedStates.includes(item.state);
      })
      .map(({ label }) => label);
    if (pendingLabels.length) {
      sections.push(`En attente de restitution : ${pendingLabels.join(", ")}`);
    }
  }

  return sections;
}

function buildAttributionTimingPreview(data) {
  const sections = [];
  const startAt = data.meta?.startAt || "";
  const dossierType = data.dossier?.type || "";
  const workflowStatus = data.workflow?.status || "draft";
  const isOnboarded = ["active", "returned", "partial_return", "cancelled"].includes(workflowStatus);
  if (dossierType !== "mise_a_jour") {
    if (startAt) {
      const offsetLabel = isOnboarded ? "" : getTimingOffsetLabel(startAt);
      sections.push(`Prise de fonction : ${formatShortDate(startAt)}${offsetLabel ? ` (${offsetLabel})` : ""}`);
    } else {
      sections.push("Prise de fonction non renseignée");
    }
  }
  const requested = collectRequestedResourcesFromPayload(data);
  const completed = requested.filter((r) => r.isCompleted);
  const missing = requested.filter((r) => !r.isCompleted);
  sections.push(`Progression : ${completed.length}/${requested.length} ressource(s) attribuée(s)`);
  if (missing.length) {
    const additional = data.resources?.additional || [];
    const materiel = data.materiel || {};
    const immateriel = data.immateriel || {};
    const missingLabels = missing.map((r) => {
      const fromAdditional = additional.find((a) => (a.id || a.code) === r.key);
      if (fromAdditional) return fromAdditional.label || r.key;
      const fromMat = materiel[r.key];
      if (fromMat) return fromMat.label || r.key;
      const fromImm = immateriel[r.key];
      if (fromImm) return fromImm.label || r.key;
      return r.key;
    });
    sections.push(`En attente : ${missingLabels.join(", ")}`);
  }
  return sections;
}

async function showTimingPreview(target, id) {
  const card = getHoverCard();
  if (!card) {
    return;
  }
  card.innerHTML = '<p class="status-hover-card__hint">Chargement...</p>';
  card.classList.remove("d-none");
  positionHoverCard(card, target);

  const result = await getDraftById(id);
  if (!result || !result.data) {
    card.innerHTML = '<p class="status-hover-card__hint">Impossible de charger le détail.</p>';
    positionHoverCard(card, target);
    return;
  }
  const items = buildTimingPreview(result.data);
  card.innerHTML = items.length
    ? `<h4>Pilotage</h4><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : '<p class="status-hover-card__hint">Aucune information de pilotage.</p>';
  positionHoverCard(card, target);
}

function bindTimingPreviews() {
  document.querySelectorAll("[data-timing-preview-id]").forEach((chip) => {
    if (chip.dataset.timingPreviewBound) {
      return;
    }
    chip.addEventListener("mouseenter", () => {
      void showTimingPreview(chip, chip.dataset.timingPreviewId);
    });
    chip.addEventListener("mouseleave", hideStatusPreview);
    chip.dataset.timingPreviewBound = "true";
  });
}
