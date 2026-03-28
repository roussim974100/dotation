const publicRestitutionSignatureForm = document.getElementById("publicRestitutionSignatureForm");
const restitutionSignatureLoader = document.getElementById("restitutionSignatureLoader");
const restitutionSignatureErrorCard = document.getElementById("restitutionSignatureErrorCard");
const restitutionSignatureSuccessCard = document.getElementById("restitutionSignatureSuccessCard");
let restitutionSignatureBooted = false;

function getRestitutionTokenFromUrl() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
}

function formatPublicRestitutionDateTime(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

async function requestRestitutionSignatureJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    cache: "no-store",
    credentials: "same-origin",
    ...options
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    const requestError = new Error(payload?.error || `HTTP ${response.status}`);
    requestError.status = response.status;
    throw requestError;
  }
  return payload;
}

function showRestitutionSignatureError(message) {
  restitutionSignatureLoader?.classList.add("is-hidden");
  publicRestitutionSignatureForm?.classList.add("d-none");
  restitutionSignatureSuccessCard?.classList.add("d-none");
  restitutionSignatureErrorCard?.classList.remove("d-none");
  const errorText = document.getElementById("restitutionSignatureErrorText");
  if (errorText) {
    errorText.textContent = message;
  }
}

function failRestitutionSignatureBoot(error) {
  console.error("restitution_signature_boot_failed", error);
  const message = error?.message || "Impossible de charger ce lien de signature de restitution.";
  showRestitutionSignatureError(message);
}

function initPublicRestitutionSignaturePad() {
  const canvas = document.getElementById("publicRestitutionSignatureCanvas");
  const clearBtn = document.getElementById("clearPublicRestitutionSignatureBtn");
  const context = canvas?.getContext("2d");
  let drawing = false;
  let hasDrawn = false;

  if (!canvas || !context) {
    throw new Error("Le composant de signature de restitution est indisponible.");
  }

  function resizeCanvas() {
    const snapshot = hasDrawn ? canvas.toDataURL("image/png") : null;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.strokeStyle = "#173042";
    if (snapshot) {
      const image = new Image();
      image.onload = () => {
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
      };
      image.src = snapshot;
    }
  }

  function point(event) {
    const rect = canvas.getBoundingClientRect();
    const source = event.touches ? event.touches[0] : event;
    return {
      x: source.clientX - rect.left,
      y: source.clientY - rect.top
    };
  }

  function start(event) {
    event.preventDefault();
    drawing = true;
    hasDrawn = true;
    const { x, y } = point(event);
    context.beginPath();
    context.moveTo(x, y);
  }

  function move(event) {
    if (!drawing) {
      return;
    }
    event.preventDefault();
    const { x, y } = point(event);
    context.lineTo(x, y);
    context.stroke();
  }

  function stop() {
    if (!drawing) {
      return;
    }
    drawing = false;
    context.closePath();
  }

  function clear() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    hasDrawn = false;
  }

  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mouseup", stop);
  canvas.addEventListener("mouseleave", stop);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", stop);
  clearBtn?.addEventListener("click", clear);

  return {
    toDataUrl: () => (hasDrawn ? canvas.toDataURL("image/png") : ""),
    resize: resizeCanvas
  };
}

function renderPublicRestitutionItems(items = []) {
  const target = document.getElementById("publicRestitutionItems");
  if (!target) {
    return;
  }
  target.replaceChildren();
  if (!items.length) {
    const emptyText = document.createElement("p");
    emptyText.className = "panel-text mb-0";
    emptyText.textContent = "Aucun materiel n'a ete renseigne pour cette restitution.";
    target.appendChild(emptyText);
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "status-card";

    const label = document.createElement("span");
    label.className = "status-card__label";
    label.textContent = item.label || "-";

    const stateLabel = document.createElement("strong");
    stateLabel.textContent = item.stateLabel || "-";

    const details = document.createElement("div");
    details.className = "panel-text mb-0";
    details.textContent = item.details || "Sans detail complementaire";

    card.append(label, stateLabel, details);

    if (item.assignmentSummary) {
      const summary = document.createElement("div");
      summary.className = "panel-text mb-0 mt-2";
      const summaryStrong = document.createElement("strong");
      summaryStrong.textContent = item.assignmentSummary;
      summary.appendChild(summaryStrong);
      card.appendChild(summary);
    }

    if (item.notes) {
      const notes = document.createElement("div");
      notes.className = "panel-text mb-0 mt-2";
      const prefix = document.createElement("strong");
      prefix.textContent = "Commentaire : ";
      notes.append(prefix, document.createTextNode(item.notes));
      card.appendChild(notes);
    }

    target.appendChild(card);
  });
}

function populatePublicRestitutionForm(payload) {
  const formData = payload?.form || {};
  const beneficiaire = formData.beneficiaire || {};
  const restitution = formData.restitution || {};
  document.getElementById("publicRestitutionSignatureTitle").textContent = `Restitution - ${formData.title || "Dossier"}`;
  document.getElementById("publicRestitutionExpiresAt").textContent = formatPublicRestitutionDateTime(payload?.link?.expiresAt);
  document.getElementById("publicRestitutionNom").textContent = beneficiaire.nom || "-";
  document.getElementById("publicRestitutionPrenom").textContent = beneficiaire.prenom || "-";
  document.getElementById("publicRestitutionQualite").textContent = beneficiaire.qualite === "elu" ? "Elu(e)" : "Agent";
  document.getElementById("publicRestitutionService").textContent = beneficiaire.service || beneficiaire.fonction || "-";
  document.getElementById("publicRestitutionMandat").textContent = beneficiaire.mandat || "-";
  document.getElementById("publicRestitutionReturnedAt").textContent = formatPublicRestitutionDateTime(restitution.returnedAt);
  document.getElementById("publicRestitutionReason").textContent = restitution.reason || "-";
  document.getElementById("publicRestitutionNotes").textContent = restitution.notes || "-";
  const decisionInput = document.querySelector(`input[name="publicRestitutionDecision"][value="${restitution.signataireDecision || "confirmed"}"]`);
  if (decisionInput) {
    decisionInput.checked = true;
  }
  document.getElementById("publicRestitutionReservationComment").value = restitution.signataireComment || "";
  renderPublicRestitutionItems(Array.isArray(restitution.items) ? restitution.items : []);
}

function syncReservationVisibility() {
  const selectedDecision = document.querySelector('input[name="publicRestitutionDecision"]:checked')?.value || "confirmed";
  document.getElementById("publicRestitutionReservationWrap")?.classList.toggle("d-none", selectedDecision !== "with_reservation");
}

async function submitPublicRestitutionSignature(signaturePad) {
  const token = getRestitutionTokenFromUrl();
  const signatureDataUrl = signaturePad.toDataUrl();
  const signataireDecision = document.querySelector('input[name="publicRestitutionDecision"]:checked')?.value || "confirmed";
  const signataireComment = document.getElementById("publicRestitutionReservationComment")?.value.trim() || "";
  if (!signatureDataUrl) {
    window.alert("Merci de signer la restitution avant validation.");
    return;
  }
  if (signataireDecision === "with_reservation" && !signataireComment) {
    window.alert("Merci de preciser votre reserve ou votre reclamation avant validation.");
    return;
  }

  try {
    await requestRestitutionSignatureJson(`/api/restitution-signature/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      body: JSON.stringify({ signatureDataUrl, signataireDecision, signataireComment })
    });
    publicRestitutionSignatureForm.classList.add("d-none");
    restitutionSignatureSuccessCard.classList.remove("d-none");
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature n'est plus valide.",
      expired: "Ce lien de signature a expire.",
      used: "Cette restitution a deja ete signee.",
      revoked: "Ce lien de signature a ete revoque.",
      reservation_comment_required: "Merci de renseigner votre reclamation avant validation."
    };
    showRestitutionSignatureError(messages[error.message] || "Impossible de valider la signature de restitution.");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = getRestitutionTokenFromUrl();
  if (!token) {
    showRestitutionSignatureError("Le lien de signature de restitution est invalide.");
    return;
  }

  window.setTimeout(() => {
    if (!restitutionSignatureBooted) {
      showRestitutionSignatureError("Le chargement de la page de signature de restitution a Ã©chouÃ©. Rechargez la page si le problÃ¨me persiste.");
    }
  }, 8000);

  try {
    const payload = await requestRestitutionSignatureJson(`/api/restitution-signature/${encodeURIComponent(token)}`);
    populatePublicRestitutionForm(payload);
    restitutionSignatureLoader.classList.add("is-hidden");
    publicRestitutionSignatureForm.classList.remove("d-none");
    document.querySelectorAll('input[name="publicRestitutionDecision"]').forEach((input) => {
      input.addEventListener("change", syncReservationVisibility);
    });
    syncReservationVisibility();
    const signaturePad = initPublicRestitutionSignaturePad();
    signaturePad.resize();
    document.getElementById("submitPublicRestitutionSignatureBtn")?.addEventListener("click", () => {
      void submitPublicRestitutionSignature(signaturePad);
    });
    restitutionSignatureBooted = true;
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature de restitution n'est pas reconnu.",
      expired: "Ce lien de signature de restitution a expire.",
      used: "Cette restitution a deja ete signee.",
      revoked: "Ce lien de signature de restitution a ete revoque."
    };
    showRestitutionSignatureError(messages[error.message] || "Impossible de charger ce lien de signature de restitution.");
  }
});

window.addEventListener("error", (event) => {
  if (!restitutionSignatureBooted) {
    failRestitutionSignatureBoot(event.error || new Error(event.message || "Erreur JavaScript"));
  }
});

window.addEventListener("unhandledrejection", (event) => {
  if (!restitutionSignatureBooted) {
    failRestitutionSignatureBoot(
      event.reason instanceof Error ? event.reason : new Error(String(event.reason || "Promesse rejetee"))
    );
  }
});

// Page publique de signature de restitution :
// consultation, reserve eventuelle et validation finale.

