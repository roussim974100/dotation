const publicAdjustmentSignatureForm = document.getElementById("publicAdjustmentSignatureForm");
const adjustmentSignatureLoader = document.getElementById("adjustmentSignatureLoader");
const adjustmentSignatureErrorCard = document.getElementById("adjustmentSignatureErrorCard");
const adjustmentSignatureSuccessCard = document.getElementById("adjustmentSignatureSuccessCard");
let adjustmentSignatureBooted = false;

function getAdjustmentTokenFromUrl() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
}

function formatPublicAdjustmentDateTime(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

async function requestAdjustmentSignatureJson(url, options = {}) {
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

function showAdjustmentSignatureError(message) {
  adjustmentSignatureLoader?.classList.add("is-hidden");
  publicAdjustmentSignatureForm?.classList.add("d-none");
  adjustmentSignatureSuccessCard?.classList.add("d-none");
  adjustmentSignatureErrorCard?.classList.remove("d-none");
  const errorText = document.getElementById("adjustmentSignatureErrorText");
  if (errorText) {
    errorText.textContent = message;
  }
}

function failAdjustmentSignatureBoot(error) {
  console.error("adjustment_signature_boot_failed", error);
  const message = error?.message || "Impossible de charger ce lien de signature d'ajustement.";
  showAdjustmentSignatureError(message);
}

function initPublicAdjustmentSignaturePad() {
  const canvas = document.getElementById("publicAdjustmentSignatureCanvas");
  const clearBtn = document.getElementById("clearPublicAdjustmentSignatureBtn");
  const context = canvas?.getContext("2d");
  let drawing = false;
  let hasDrawn = false;

  if (!canvas || !context) {
    throw new Error("Le composant de signature est indisponible.");
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

function renderPublicAdjustmentSummary(adjustment = {}) {
  const target = document.getElementById("publicAdjustmentSummary");
  if (!target) {
    return;
  }
  target.replaceChildren();
  const retraits = Array.isArray(adjustment.retraits) ? adjustment.retraits : [];
  const ajouts = Array.isArray(adjustment.ajouts) ? adjustment.ajouts : [];
  const service = adjustment.service;

  if (!retraits.length && !ajouts.length && !service) {
    const emptyText = document.createElement("p");
    emptyText.className = "panel-text mb-0";
    emptyText.textContent = "Aucun détail disponible pour cet ajustement.";
    target.appendChild(emptyText);
    return;
  }

  retraits.forEach((item) => {
    const card = document.createElement("div");
    card.className = "status-card";
    const label = document.createElement("span");
    label.className = "status-card__label";
    label.textContent = `Retrait — ${item.label || "-"}`;
    const stateLabel = document.createElement("strong");
    stateLabel.textContent = item.stateLabel || "-";
    card.append(label, stateLabel);
    if (item.notes) {
      const notes = document.createElement("div");
      notes.className = "panel-text mb-0 mt-2";
      const prefix = document.createElement("strong");
      prefix.textContent = "Remarque : ";
      notes.append(prefix, document.createTextNode(item.notes));
      card.appendChild(notes);
    }
    target.appendChild(card);
  });

  ajouts.forEach((item) => {
    const card = document.createElement("div");
    card.className = "status-card";
    const label = document.createElement("span");
    label.className = "status-card__label";
    label.textContent = "Ajout";
    const stateLabel = document.createElement("strong");
    stateLabel.textContent = item.label || "-";
    card.append(label, stateLabel);
    target.appendChild(card);
  });

  if (service) {
    const card = document.createElement("div");
    card.className = "status-card";
    const label = document.createElement("span");
    label.className = "status-card__label";
    label.textContent = "Changement de service";
    const stateLabel = document.createElement("strong");
    stateLabel.textContent = `${service.from || "—"} → ${service.to || "—"}`;
    card.append(label, stateLabel);
    target.appendChild(card);
  }
}

function populatePublicAdjustmentForm(payload) {
  const formData = payload?.form || {};
  const beneficiaire = formData.beneficiaire || {};
  document.getElementById("publicAdjustmentSignatureTitle").textContent = `Ajustement — ${formData.title || "Dossier"}`;
  document.getElementById("publicAdjustmentExpiresAt").textContent = formatPublicAdjustmentDateTime(payload?.link?.expiresAt);
  document.getElementById("publicAdjustmentNom").textContent = beneficiaire.nom || "-";
  document.getElementById("publicAdjustmentPrenom").textContent = beneficiaire.prenom || "-";
  document.getElementById("publicAdjustmentService").textContent = beneficiaire.service || beneficiaire.fonction || "-";
  renderPublicAdjustmentSummary(formData.adjustment || {});
}

function showAdjustmentSuccess() {
  publicAdjustmentSignatureForm.classList.add("d-none");
  adjustmentSignatureSuccessCard.classList.remove("d-none");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function submitPublicAdjustmentSignature(signaturePad) {
  const token = getAdjustmentTokenFromUrl();
  const signatureDataUrl = signaturePad.toDataUrl();
  if (!signatureDataUrl) {
    showToast("Merci de signer avant validation.", "error");
    return;
  }

  const btn = document.getElementById("submitPublicAdjustmentSignatureBtn");
  const originalLabel = btn.textContent;
  btn.classList.add("btn-loading");
  btn.textContent = "Envoi en cours…";

  try {
    await requestAdjustmentSignatureJson(`/api/adjustment-signature/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      body: JSON.stringify({ signatureDataUrl })
    });
    showAdjustmentSuccess();
  } catch (error) {
    btn.classList.remove("btn-loading");
    btn.textContent = originalLabel;
    const messages = {
      invalid_link: "Ce lien de signature n'est plus valide.",
      expired: "Ce lien de signature a expiré.",
      used: "Cet ajustement a déjà été signé.",
      revoked: "Ce lien de signature a été révoqué.",
      no_pending_adjustment: "Cet ajustement n'est plus en attente de signature.",
      already_signed: "Cet ajustement est déjà signé.",
    };
    showAdjustmentSignatureError(messages[error.message] || "Impossible de valider la signature de l'ajustement.");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = getAdjustmentTokenFromUrl();
  if (!token) {
    showAdjustmentSignatureError("Le lien de signature d'ajustement est invalide.");
    return;
  }

  window.setTimeout(() => {
    if (!adjustmentSignatureBooted) {
      showAdjustmentSignatureError("Le chargement de la page de signature a échoué. Rechargez la page si le problème persiste.");
    }
  }, 8000);

  try {
    const payload = await requestAdjustmentSignatureJson(`/api/adjustment-signature/${encodeURIComponent(token)}`);
    populatePublicAdjustmentForm(payload);
    adjustmentSignatureLoader.classList.add("is-hidden");
    publicAdjustmentSignatureForm.classList.remove("d-none");
    const signaturePad = initPublicAdjustmentSignaturePad();
    signaturePad.resize();
    document.getElementById("submitPublicAdjustmentSignatureBtn")?.addEventListener("click", () => {
      void submitPublicAdjustmentSignature(signaturePad);
    });
    adjustmentSignatureBooted = true;
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature d'ajustement n'est pas reconnu.",
      expired: "Ce lien de signature d'ajustement a expiré.",
      used: "Cet ajustement a déjà été signé.",
      revoked: "Ce lien de signature d'ajustement a été révoqué.",
      no_pending_adjustment: "Cet ajustement n'est plus en attente de signature.",
    };
    showAdjustmentSignatureError(messages[error.message] || "Impossible de charger ce lien de signature d'ajustement.");
  }
});

window.addEventListener("error", (event) => {
  if (!adjustmentSignatureBooted) {
    failAdjustmentSignatureBoot(event.error || new Error(event.message || "Erreur JavaScript"));
  }
});

window.addEventListener("unhandledrejection", (event) => {
  if (!adjustmentSignatureBooted) {
    failAdjustmentSignatureBoot(
      event.reason instanceof Error ? event.reason : new Error(String(event.reason || "Promesse rejetee"))
    );
  }
});

// Page publique de signature d'ajustement : consultation du geste puis signature.
