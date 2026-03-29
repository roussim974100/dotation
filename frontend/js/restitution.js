const restitutionLoader = document.getElementById("restitutionLoader");
const restitutionDetailList = document.getElementById("restitutionDetailList");

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    credentials: "same-origin",
    ...options
  });

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    const requestError = new Error(payload?.error || `HTTP ${response.status}`);
    requestError.status = response.status;
    throw requestError;
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function getDraftById(id) {
  return requestJson(`/api/forms/${encodeURIComponent(id)}`);
}

const restitutionStateLabels = {
  conforme: "Conforme",
  degrade: "Endommage",
  non_restitue: "Non restitue",
  perdu: "Perdu",
  autre: "Autre"
};

function todayDateInputValue() {
  return new Date().toISOString().slice(0, 10);
}

function showRestitutionLoader() {
  restitutionLoader?.classList.remove("is-hidden");
}

function hideRestitutionLoader() {
  restitutionLoader?.classList.add("is-hidden");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function selectedDetail(details) {
  const payload = details || {};
  const fields = payload.fields || {};
  const fieldValues = Object.values(fields)
    .map((value) => {
      if (value === true || value === "true" || value === "Oui" || value === "on") {
        return "Oui";
      }
      return Array.isArray(value) ? value.join(" - ") : String(value || "").trim();
    })
    .filter(Boolean);

  if (fieldValues.length) {
    return fieldValues.join(" - ");
  }

  if (payload.details) {
    return String(payload.details).trim();
  }

  return Object.entries(payload)
    .filter(([key, value]) => ![
      "selected",
      "id",
      "code",
      "label",
      "category",
      "issuerService",
      "issuer_service",
      "triggerKey",
      "trigger_key",
      "requiresReturn",
      "requires_return",
      "hasAssignmentDate",
      "has_assignment_date",
      "hasAssignmentCondition",
      "has_assignment_condition",
      "hasAssignmentNotes",
      "has_assignment_notes",
      "displayOrder",
      "display_order",
      "fieldSchema",
      "field_schema",
      "fields",
      "assignedAt",
      "conditionAttribution",
      "conditionNotes"
    ].includes(key) && value)
    .map(([, value]) => Array.isArray(value) ? value.join(" - ") : value)
    .join(" - ");
}

function isRestitutionEligibleItem(item) {
  if (item.category !== "materiel") {
    return false;
  }
  const details = item.details || {};
  if ("requiresReturn" in details || "requires_return" in details) {
    return Boolean(details.requiresReturn ?? details.requires_return);
  }
  return true;
}

function normalizeRestitutionState(value) {
  const mapping = {
    returned: "conforme",
    returned_damaged: "degrade",
    missing: "non_restitue",
    transferred: "autre",
    conforme: "conforme",
    degrade: "degrade",
    non_restitue: "non_restitue",
    perdu: "perdu",
    autre: "autre"
  };
  return mapping[value] || "conforme";
}

function showCommentForState(state) {
  return normalizeRestitutionState(state) !== "conforme";
}

function initSignaturePad(canvasId, clearButtonId) {
  const canvas = document.getElementById(canvasId);
  const clearButton = document.getElementById(clearButtonId);

  if (!canvas) {
    return { clear: () => {}, restore: () => {}, toDataUrl: () => "" };
  }

  const context = canvas.getContext("2d");
  let isDrawing = false;
  let hasDrawn = false;

  function setupContext() {
    if (!context) {
      return;
    }
    context.lineWidth = 2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#17354d";
  }

  function resizeCanvas() {
    const snapshot = hasDrawn ? canvas.toDataURL() : null;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    setupContext();

    if (snapshot && context) {
      const image = new Image();
      image.onload = () => {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        hasDrawn = true;
      };
      image.src = snapshot;
    }
  }

  function getPoint(event) {
    const rect = canvas.getBoundingClientRect();
    const source = event.touches?.[0] || event;
    return {
      x: source.clientX - rect.left,
      y: source.clientY - rect.top
    };
  }

  function startDrawing(event) {
    if (!context) {
      return;
    }
    event.preventDefault();
    const point = getPoint(event);
    isDrawing = true;
    context.beginPath();
    context.moveTo(point.x, point.y);
  }

  function draw(event) {
    if (!isDrawing || !context) {
      return;
    }
    event.preventDefault();
    const point = getPoint(event);
    context.lineTo(point.x, point.y);
    context.stroke();
    hasDrawn = true;
  }

  function stopDrawing() {
    isDrawing = false;
  }

  function clear() {
    if (!context) {
      return;
    }
    context.clearRect(0, 0, canvas.width, canvas.height);
    hasDrawn = false;
  }

  clearButton?.addEventListener("click", clear);
  canvas.addEventListener("mousedown", startDrawing);
  canvas.addEventListener("mousemove", draw);
  canvas.addEventListener("mouseup", stopDrawing);
  canvas.addEventListener("mouseleave", stopDrawing);
  canvas.addEventListener("touchstart", startDrawing, { passive: false });
  canvas.addEventListener("touchmove", draw, { passive: false });
  canvas.addEventListener("touchend", stopDrawing);
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  return {
    clear,
    restore(dataUrl) {
      clear();
      if (!dataUrl || !context) {
        return;
      }
      const image = new Image();
      image.onload = () => {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        hasDrawn = true;
      };
      image.src = dataUrl;
    },
    toDataUrl: () => (hasDrawn ? canvas.toDataURL("image/png") : "")
  };
}

function toggleSignatureMode() {
  const mode = document.querySelector('input[name="restitution_signature_status"]:checked')?.value || "signed";
  document.getElementById("restitutionSignatureCanvasWrap")?.classList.toggle("d-none", mode !== "signed");
  document.getElementById("restitutionSignatureReasonWrap")?.classList.toggle("d-none", mode !== "impossible");
  document.getElementById("restitutionLinkValidityWrap")?.classList.toggle("d-none", mode !== "deferred");
  const saveButton = document.getElementById("saveRestitutionBtn");
  if (saveButton) {
    saveButton.textContent = mode === "deferred"
      ? "Enregistrer et générer le lien"
      : "Enregistrer la restitution";
  }
}

function renderRestitutionItems(items, existingStates) {
  restitutionDetailList.innerHTML = items.map((item) => {
    const state = existingStates[item.itemKey] || {};
    const currentState = normalizeRestitutionState(state.state || state.condition);
    const showNotes = showCommentForState(currentState);

    return `
      <div class="restitution-row">
        <div>
          <div class="restitution-row__title">${escapeHtml(item.label)}</div>
          <div class="restitution-row__meta">${escapeHtml(selectedDetail(item.details) || "Aucun detail complementaire")}</div>
        </div>
        <div>
          <label class="form-label d-block">Etat</label>
          <div class="choice-group restitution-choice-group" data-rest-group="${item.itemKey}">
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="conforme" ${currentState === "conforme" ? "checked" : ""}>
              <span>Conforme</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="degrade" ${currentState === "degrade" ? "checked" : ""}>
              <span>Endommage</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="non_restitue" ${currentState === "non_restitue" ? "checked" : ""}>
              <span>Non restitue</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="perdu" ${currentState === "perdu" ? "checked" : ""}>
              <span>Perdu</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="autre" ${currentState === "autre" ? "checked" : ""}>
              <span>Autre</span>
            </label>
          </div>
        </div>
        <div id="rest_note_wrap_${item.itemKey}" class="${showNotes ? "" : "d-none"}">
          <label class="form-label" for="rest_note_${item.itemKey}">Commentaire</label>
          <input class="form-control" id="rest_note_${item.itemKey}" value="${escapeHtml(state.notes || "")}" placeholder="Precisez l'etat ou la situation">
        </div>
      </div>
    `;
  }).join("");

  items.forEach((item) => {
    document.querySelectorAll(`input[name="rest_state_${item.itemKey}"]`).forEach((input) => {
      input.addEventListener("change", () => {
        const wrap = document.getElementById(`rest_note_wrap_${item.itemKey}`);
        if (!wrap) {
          return;
        }
        wrap.classList.toggle("d-none", !showCommentForState(input.value));
      });
    });
  });
}

function deriveWorkflowStatus(itemStates) {
  const states = Object.values(itemStates);
  if (!states.length) {
    return "returned";
  }
  return states.some((state) => state.state === "non_restitue") ? "partial_return" : "returned";
}

function getItemStates(items, globalReturnedAt, existingStates = {}) {
  const states = {};
  items.forEach((item) => {
    const previous = existingStates[item.itemKey] || {};
    const state = normalizeRestitutionState(
      document.querySelector(`input[name="rest_state_${item.itemKey}"]:checked`)?.value || "conforme"
    );
    const notes = showCommentForState(state)
      ? (document.getElementById(`rest_note_${item.itemKey}`)?.value.trim() || "")
      : "";
    const previousState = normalizeRestitutionState(previous.state || previous.condition);
    const returnedAt = state === "non_restitue"
      ? ""
      : (previousState === state && previous.returnedAt ? previous.returnedAt : (globalReturnedAt || previous.returnedAt || ""));

    states[item.itemKey] = {
      state,
      returned: state === "conforme" || state === "degrade",
      returnedAt,
      condition: state,
      notes
    };
  });
  return states;
}

function getRestitutionSignaturePayload(signaturePad, existing) {
  const signatureStatus = document.querySelector('input[name="restitution_signature_status"]:checked')?.value || "signed";
  const signatureReason = document.getElementById("restitution_signature_reason")?.value.trim() || "";
  const signatureDataUrl = signatureStatus === "signed" ? signaturePad.toDataUrl() || existing?.signatureDataUrl || "" : "";
  const signedAt = signatureStatus === "signed" && signatureDataUrl ? (existing?.signedAt || new Date().toISOString()) : "";

  return {
    signatureStatus,
    signatureReason,
    signatureDataUrl,
    signedAt
  };
}

function restoreRestitutionSignature(restitution, signaturePad) {
  const status = restitution?.signatureStatus || (restitution?.signatureDataUrl ? "signed" : "deferred");
  const radio = document.querySelector(`input[name="restitution_signature_status"][value="${status}"]`);
  if (radio) {
    radio.checked = true;
  }
  const reasonField = document.getElementById("restitution_signature_reason");
  if (reasonField) {
    reasonField.value = restitution?.signatureReason || "";
  }
  signaturePad.restore(status === "signed" ? (restitution?.signatureDataUrl || "") : "");
  toggleSignatureMode();
}

function getRestitutionLinkValidityDays() {
  const field = document.getElementById("restitution_link_validity_days");
  const rawValue = Number.parseInt(field?.value || "7", 10);
  const sanitized = Number.isFinite(rawValue) ? Math.min(30, Math.max(1, rawValue)) : 7;
  if (field) {
    field.value = String(sanitized);
  }
  return sanitized;
}

function applyRestitutionReadOnlyMode() {
  document.getElementById("restitutionSubtitle").textContent = "Consultation de la restitution finalisée. Les informations restent visibles, sans modification possible.";
  document.getElementById("restitutionStatus").textContent = "Restitution terminée";
  document.querySelector(".action-bar__hint")?.replaceChildren(
    document.createTextNode("Consultation seule : la restitution est déjà finalisée.")
  );
  document.getElementById("saveRestitutionBtn")?.classList.add("d-none");
  document.getElementById("clearRestitutionSignatureBtn")?.classList.add("d-none");
  document.getElementById("restitution_signature")?.classList.add("signature-box--readonly");

  document.querySelectorAll(
    "#restitution-context input, #restitution-context select, #restitution-context textarea, " +
    "#restitution-items input, #restitution-items textarea, #restitution-signature input, #restitution-signature textarea"
  ).forEach((field) => {
    field.disabled = true;
  });
}

async function initRestitutionPage() {
  try {
    showRestitutionLoader();
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");
    if (!id) {
      alert("Aucune fiche selectionnee.");
      window.location.href = "index.html";
      return;
    }

    const result = await getDraftById(id);
    if (!result?.data) {
      alert("Fiche introuvable.");
      window.location.href = "index.html";
      return;
    }

    const currentStatus = result.summary?.status || result.data?.workflow?.status;
    if (!["active", "partial_return", "awaiting_signature", "returned"].includes(currentStatus)) {
      alert("La restitution n'est disponible que pour les dossiers avec materiel a restituer ou deja restitue.");
      window.location.href = "index.html";
      return;
    }
    const readOnlyMode = currentStatus === "returned";

    const signaturePad = initSignaturePad("restitution_signature", "clearRestitutionSignatureBtn");
    document.querySelectorAll('input[name="restitution_signature_status"]').forEach((input) => {
      input.addEventListener("change", () => toggleSignatureMode());
    });

    document.getElementById("restitutionTitle").textContent = `${result.data.beneficiaire.nom} ${result.data.beneficiaire.prenom}`;
    document.getElementById("restitutionSubtitle").textContent = result.data.beneficiaire.service || result.data.beneficiaire.mandat || "Fiche active";
    document.getElementById("restitutionStatus").textContent = currentStatus === "partial_return"
      ? "Restitution partielle"
      : (currentStatus === "awaiting_signature" ? "En attente de signature" : (currentStatus === "returned" ? "Restitution terminée" : "Attribution active"));
    document.getElementById("global_returned_at").value = result.data.restitution?.returnedAt || todayDateInputValue();
    document.getElementById("global_return_reason").value = result.data.restitution?.reason || "";
    document.getElementById("global_return_notes").value = result.data.restitution?.notes || "";

    const materialItems = (result.items || []).filter((item) => isRestitutionEligibleItem(item));
    renderRestitutionItems(materialItems, result.data.restitution?.items || {});
    let currentRestitution = result.data.restitution || {};
    restoreRestitutionSignature(currentRestitution, signaturePad);
    if (readOnlyMode) {
      applyRestitutionReadOnlyMode();
    }

    function buildRestitutionPayload(forceDeferredSignature = false) {
      const returnedAt = document.getElementById("global_returned_at").value || todayDateInputValue();
      document.getElementById("global_returned_at").value = returnedAt;
      if (!returnedAt) {
        throw new Error("Veuillez renseigner la date de restitution.");
      }

      const itemStates = getItemStates(materialItems, returnedAt, currentRestitution?.items || {});
      let signature = getRestitutionSignaturePayload(signaturePad, currentRestitution || {});

      if (forceDeferredSignature) {
        signature = {
          signatureStatus: "deferred",
          signatureReason: "",
          signatureDataUrl: "",
          signedAt: ""
        };
      }

      if (signature.signatureStatus === "impossible" && !signature.signatureReason && !forceDeferredSignature) {
        throw new Error("Veuillez preciser pourquoi la signature n'a pas pu etre recueillie sur place.");
      }
      if (signature.signatureStatus === "signed" && !signature.signatureDataUrl) {
        throw new Error("Veuillez recueillir la signature sur place ou choisir un autre mode de signature.");
      }

      return {
        status: deriveWorkflowStatus(itemStates),
        returnedAt,
        reason: document.getElementById("global_return_reason").value,
        notes: document.getElementById("global_return_notes").value.trim(),
        items: itemStates,
        signatureStatus: signature.signatureStatus,
        signatureReason: signature.signatureReason,
        signatureDataUrl: signature.signatureDataUrl,
        signedAt: signature.signedAt
      };
    }

    async function saveRestitution(payload) {
      const response = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      currentRestitution = response?.data?.restitution || {
        ...currentRestitution,
        ...payload
      };
      return response;
    }

    function createRestitutionWorkflowSteps(labels, activeIndex = 0) {
      return labels.map((label, index) => ({
        label,
        status: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending"
      }));
    }

    async function showRestitutionInfoDialog(title, text, items = []) {
      const steps = items.length
        ? items.map((label) => ({ label, status: "error" }))
        : [{ label: text, status: "error" }];
      await window.askWorkflowDialog({
        title,
        text,
        steps,
        hideSpinner: true,
        showConfirm: true,
        confirmLabel: "OK"
      });
    }

    async function shareRestitutionSignatureLink() {
      try {
        await saveRestitution(buildRestitutionPayload(true));

        const linkResult = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution-signature-link`, {
          method: "POST",
          body: JSON.stringify({
            validityDays: getRestitutionLinkValidityDays()
          })
        });

        await window.playCompletionCelebration("boat");
        await window.askWorkflowDialog({
          title: "Lien de signature prêt",
          text: "La restitution est enregistrée et le lien de signature à distance est désormais disponible pour l'envoi par e-mail ou la copie du lien.",
          steps: [
            { label: "Restitution enregistrée", status: "done" },
            { label: "Lien de signature préparé", status: "done" }
          ],
          hideSpinner: true,
          showConfirm: true,
          confirmLabel: "OK"
        });
        window.location.href = "index.html";
      } catch (error) {
        window.closeWorkflowDialog();
        await showRestitutionInfoDialog(
          "Erreur de restitution",
          error.message || "Impossible de générer le lien de signature de restitution."
        );
      }
    }

    document.getElementById("saveRestitutionBtn")?.addEventListener("click", async () => {
      const workflowLabels = [
        "Préparation des éléments de restitution",
        "Vérification des états et de la signature",
        "Enregistrement de la restitution",
        "Finalisation du retour au tableau de bord"
      ];
      try {
        window.showWorkflowDialog({
          title: "Enregistrement de la restitution",
          text: "La restitution est en cours de préparation.",
          steps: createRestitutionWorkflowSteps(workflowLabels, 0)
        });

        const selectedSignatureMode = document.querySelector('input[name="restitution_signature_status"]:checked')?.value || "signed";
        window.showWorkflowDialog({
          title: "Enregistrement de la restitution",
          text: "La cohérence des états et du mode de signature est en cours de vérification.",
          steps: createRestitutionWorkflowSteps(workflowLabels, 1)
        });
        if (selectedSignatureMode === "deferred") {
          window.showWorkflowDialog({
            title: "Enregistrement de la restitution",
            text: "La restitution est enregistrée et le lien de signature va être préparé.",
            steps: createRestitutionWorkflowSteps(workflowLabels, 2)
          });
          await shareRestitutionSignatureLink();
          return;
        }

        window.showWorkflowDialog({
          title: "Enregistrement de la restitution",
          text: "Les informations sont en cours d'enregistrement.",
          steps: createRestitutionWorkflowSteps(workflowLabels, 2)
        });
        const response = await saveRestitution(buildRestitutionPayload(false));
        window.showWorkflowDialog({
          title: "Enregistrement de la restitution",
          text: "La restitution a été enregistrée. L'application finalise maintenant le retour vers le tableau de bord.",
          steps: workflowLabels.map((label) => ({ label, status: "done" }))
        });
        if (["returned", "awaiting_signature"].includes(response?.summary?.status || "")) {
          await window.playCompletionCelebration("boat");
        }
        await window.askWorkflowDialog({
          title: "Restitution enregistrée",
          text: "La restitution est maintenant à jour.",
          steps: workflowLabels.map((label) => ({ label, status: "done" })),
          hideSpinner: true,
          showConfirm: true,
          confirmLabel: "OK"
        });
        window.location.href = "index.html";
      } catch (error) {
        window.closeWorkflowDialog();
        await showRestitutionInfoDialog(
          "Erreur de restitution",
          error.message || "Impossible d'enregistrer la restitution."
        );
      }
    });

    requestAnimationFrame(() => {
      requestAnimationFrame(() => hideRestitutionLoader());
    });
  } catch (error) {
    console.error("Erreur lors du chargement de la restitution", error);
    hideRestitutionLoader();
    alert("Impossible de charger la restitution.");
    window.location.href = "index.html";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void initRestitutionPage();
});
// Écran interne de restitution :
// préparation du retour, collecte des états et partage du lien public.
