const publicSignatureForm = document.getElementById("publicSignatureForm");
const signaturePageLoader = document.getElementById("signaturePageLoader");
const signatureErrorCard = document.getElementById("signatureErrorCard");
const signatureSuccessCard = document.getElementById("signatureSuccessCard");

function getTokenFromUrl() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
}

function formatPublicDateTime(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

async function requestPublicJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
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

function showPublicError(message) {
  signaturePageLoader.classList.add("is-hidden");
  publicSignatureForm.classList.add("d-none");
  signatureSuccessCard.classList.add("d-none");
  signatureErrorCard.classList.remove("d-none");
  document.getElementById("signatureErrorText").textContent = message;
}

function initPublicSignaturePad() {
  const canvas = document.getElementById("publicSignatureCanvas");
  const clearBtn = document.getElementById("clearPublicSignatureBtn");
  const context = canvas.getContext("2d");
  let drawing = false;
  let hasDrawn = false;

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
  clearBtn.addEventListener("click", clear);

  return {
    toDataUrl: () => (hasDrawn ? canvas.toDataURL("image/png") : ""),
    clear,
    resize: resizeCanvas
  };
}

function renderResourceList(targetId, items = []) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  target.replaceChildren();
  if (!items.length) {
    const emptyText = document.createElement("p");
    emptyText.className = "panel-text mb-0";
    emptyText.textContent = "Aucune ressource renseignée.";
    target.appendChild(emptyText);
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "status-card";

    const label = document.createElement("span");
    label.className = "status-card__label";
    label.textContent = item.service || "Service";

    const title = document.createElement("strong");
    title.textContent = item.label || "-";

    const details = document.createElement("div");
    details.className = "panel-text mb-0";
    details.textContent = item.details || "Sans détail complémentaire";

    card.append(label, title, details);

    if (item.assignmentSummary) {
      const summary = document.createElement("div");
      summary.className = "panel-text mb-0 mt-2";
      const summaryStrong = document.createElement("strong");
      summaryStrong.textContent = item.assignmentSummary;
      summary.appendChild(summaryStrong);
      card.appendChild(summary);
    }

    target.appendChild(card);
  });
}

function populatePublicForm(payload) {
  const formData = payload.form;
  document.getElementById("publicSignatureTitle").textContent = formData.title || "Dossier d'attribution";
  document.getElementById("publicSignatureExpiresAt").textContent = formatPublicDateTime(payload.link.expiresAt);
  document.getElementById("publicNom").textContent = formData.beneficiaire.nom || "-";
  document.getElementById("publicPrenom").textContent = formData.beneficiaire.prenom || "-";
  const qualiteVal = formData.beneficiaire.qualite;
  const qualiteTypes = window.APP_BRANDING?.beneficiaryTypes;
  const qualiteFound = qualiteTypes?.find((t) => t.value === qualiteVal);
  document.getElementById("publicQualite").textContent = qualiteFound ? qualiteFound.label : (qualiteVal === "elu" ? "Élu(e)" : "Agent");
  document.getElementById("publicService").textContent = formData.beneficiaire.service || formData.beneficiaire.fonction || "-";
  document.getElementById("publicMandat").textContent = formData.beneficiaire.mandat || "-";
  renderResourceList("publicMaterialResources", formData.resources.materiel || []);
  renderResourceList("publicImmaterialResources", formData.resources.immateriel || []);
  const rgpdTarget = document.getElementById("publicRgpdText");
  rgpdTarget.replaceChildren();
  (formData.rgpdText || []).forEach((line) => {
    const paragraph = document.createElement("p");
    paragraph.className = "rgpd-text";
    paragraph.textContent = line;
    rgpdTarget.appendChild(paragraph);
  });
}

function showSignatureSuccess(result) {
  const summary = result?.summary || {};
  const nom = [summary.prenom, summary.nom].filter(Boolean).join(" ") || "—";
  const now = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date());
  document.getElementById("successName").textContent = nom;
  document.getElementById("successDate").textContent = now;
  document.getElementById("successTitle").textContent = summary.title || "—";
  publicSignatureForm.classList.add("d-none");
  signatureSuccessCard.classList.remove("d-none");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function submitPublicSignature(signaturePad) {
  const token = getTokenFromUrl();
  const rgpdAccepted = document.getElementById("publicRgpdCheck").checked;
  const signatureDataUrl = signaturePad.toDataUrl();
  if (!rgpdAccepted) {
    showToast("La prise de connaissance RGPD est obligatoire.", "error");
    return;
  }
  if (!signatureDataUrl) {
    showToast("Merci de signer le dossier avant validation.", "error");
    return;
  }

  const btn = document.getElementById("submitPublicSignatureBtn");
  const originalLabel = btn.textContent;
  btn.classList.add("btn-loading");
  btn.textContent = "Envoi en cours…";

  try {
    const result = await requestPublicJson(`/api/signature/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      body: JSON.stringify({ rgpdAccepted, signatureDataUrl })
    });
    showSignatureSuccess(result);
  } catch (error) {
    btn.classList.remove("btn-loading");
    btn.textContent = originalLabel;
    const messages = {
      invalid_link: "Ce lien n'est plus valide.",
      expired: "Ce lien de signature a expiré.",
      used: "Ce dossier a déjà été signé.",
      revoked: "Ce lien de signature a été révoqué."
    };
    showPublicError(messages[error.message] || "Impossible de valider la signature.");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = getTokenFromUrl();
  if (!token) {
    showPublicError("Le lien de signature est invalide.");
    return;
  }

  try {
    const payload = await requestPublicJson(`/api/signature/${encodeURIComponent(token)}`);
    populatePublicForm(payload);
    signaturePageLoader.classList.add("is-hidden");
    publicSignatureForm.classList.remove("d-none");
    const signaturePad = initPublicSignaturePad();
    signaturePad.resize();
    document.getElementById("submitPublicSignatureBtn").addEventListener("click", () => {
      void submitPublicSignature(signaturePad);
    });
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature n'est pas reconnu.",
      expired: "Ce lien de signature a expiré.",
      used: "Ce dossier a déjà été signé.",
      revoked: "Ce lien de signature a été révoqué."
    };
    showPublicError(messages[error.message] || "Impossible de charger ce lien de signature.");
  }
});


// Page publique de signature d'attribution :
// consultation du dossier, validation RGPD et signature sans compte.
