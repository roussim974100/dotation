const restitutionLoader = document.getElementById("restitutionLoader");
const restitutionDetailList = document.getElementById("restitutionDetailList");

const restitutionStateLabels = {
  conforme: "Conforme",
  degrade: "Endommagé",
  non_restitue: "Non restitué",
  perdu: "Perdu",
  autre: "Autre"
};

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
  return Object.entries(details || {})
    .filter(([key, value]) => key !== "selected" && value)
    .map(([, value]) => Array.isArray(value) ? value.join(" - ") : value)
    .join(" - ");
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

    if (snapshot) {
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
    event.preventDefault();
    const point = getPoint(event);
    isDrawing = true;
    context.beginPath();
    context.moveTo(point.x, point.y);
  }

  function draw(event) {
    if (!isDrawing) {
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
      if (!dataUrl) {
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
  document.getElementById("restitutionSignatureReasonWrap")?.classList.toggle("d-none", mode === "signed");
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
          <div class="restitution-row__meta">${escapeHtml(selectedDetail(item.details) || "Aucun détail complémentaire")}</div>
        </div>
        <div>
          <label class="form-label d-block">État</label>
          <div class="choice-group restitution-choice-group" data-rest-group="${item.itemKey}">
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="conforme" ${currentState === "conforme" ? "checked" : ""}>
              <span>Conforme</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="degrade" ${currentState === "degrade" ? "checked" : ""}>
              <span>Endommagé</span>
            </label>
            <label class="choice-chip">
              <input type="radio" name="rest_state_${item.itemKey}" value="non_restitue" ${currentState === "non_restitue" ? "checked" : ""}>
              <span>Non restitué</span>
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
          <input class="form-control" id="rest_note_${item.itemKey}" value="${escapeHtml(state.notes || "")}" placeholder="Précisez l'état ou la situation">
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

async function shareRestitutionSignatureLink(id) {
  try {
    let result = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution-signature-link`);
    if (!result?.link || result.link.status !== "active" || !result.link.url) {
      result = await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution-signature-link`, {
        method: "POST"
      });
    }

    const absoluteUrl = new URL(result.link.url, window.location.origin).href;
    try {
      await navigator.clipboard.writeText(absoluteUrl);
      window.alert("Lien de signature de restitution copié.");
    } catch (error) {
      window.prompt("Copiez ce lien de signature de restitution :", absoluteUrl);
    }
  } catch (error) {
    window.alert(error.message || "Impossible de préparer le lien de signature de restitution.");
  }
}

function restoreRestitutionSignature(restitution, signaturePad) {
  const status = restitution?.signatureStatus || (restitution?.signatureDataUrl ? "signed" : "deferred");
  const radio = document.querySelector(`input[name="restitution_signature_status"][value="${status}"]`);
  if (radio) {
    radio.checked = true;
  }
  document.getElementById("restitution_signature_reason").value = restitution?.signatureReason || "";
  signaturePad.restore(status === "signed" ? (restitution?.signatureDataUrl || "") : "");
  toggleSignatureMode();
}

async function initRestitutionPage() {
  showRestitutionLoader();
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) {
    alert("Aucune fiche sélectionnée.");
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
  if (!["active", "partial_return"].includes(currentStatus)) {
    alert("La restitution n'est modifiable que si du matériel reste à récupérer.");
    window.location.href = "index.html";
    return;
  }

  const signaturePad = initSignaturePad("restitution_signature", "clearRestitutionSignatureBtn");
  document.querySelectorAll('input[name="restitution_signature_status"]').forEach((input) => {
    input.addEventListener("change", () => toggleSignatureMode());
  });

  document.getElementById("restitutionTitle").textContent = `${result.data.beneficiaire.nom} ${result.data.beneficiaire.prenom}`;
  document.getElementById("restitutionSubtitle").textContent = result.data.beneficiaire.service || result.data.beneficiaire.mandat || "Fiche active";
  document.getElementById("restitutionStatus").textContent = currentStatus === "partial_return" ? "Restitution partielle" : "Attribution active";
  document.getElementById("global_returned_at").value = result.data.restitution?.returnedAt || "";
  document.getElementById("global_return_reason").value = result.data.restitution?.reason || "";
  document.getElementById("global_return_notes").value = result.data.restitution?.notes || "";

  const materialItems = (result.items || []).filter((item) => item.category === "materiel");
  renderRestitutionItems(materialItems, result.data.restitution?.items || {});
  restoreRestitutionSignature(result.data.restitution || {}, signaturePad);

  document.getElementById("exportRestitutionPdfBtn")?.addEventListener("click", () => {
    window.location.href = `/api/forms/${encodeURIComponent(id)}/restitution-pdf`;
  });
  document.getElementById("shareRestitutionSignatureLinkBtn")?.addEventListener("click", () => {
    void shareRestitutionSignatureLink(id);
  });

  document.getElementById("saveRestitutionBtn").addEventListener("click", async () => {
    const returnedAt = document.getElementById("global_returned_at").value;
    if (!returnedAt) {
      alert("Veuillez renseigner la date de restitution.");
      return;
    }

    const itemStates = getItemStates(materialItems, returnedAt, result.data.restitution?.items || {});
    const signature = getRestitutionSignaturePayload(signaturePad, result.data.restitution || {});
    if (signature.signatureStatus !== "signed" && !signature.signatureReason) {
      alert("Veuillez préciser pourquoi la signature n'a pas pu être recueillie.");
      return;
    }
    if (signature.signatureStatus === "signed" && !signature.signatureDataUrl) {
      alert("Veuillez recueillir la signature ou choisir un autre statut de signature.");
      return;
    }

    const payload = {
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

    try {
      await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      alert("Restitution enregistrée.");
      window.location.href = "index.html";
    } catch (error) {
      alert("Impossible d'enregistrer la restitution.");
    }
  });

  requestAnimationFrame(() => {
    requestAnimationFrame(() => hideRestitutionLoader());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  void initRestitutionPage();
});
