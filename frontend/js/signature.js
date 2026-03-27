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
  if (!items.length) {
    target.innerHTML = "<p class=\"panel-text mb-0\">Aucune ressource renseignée.</p>";
    return;
  }
  target.innerHTML = items.map((item) => `
    <div class="status-card">
      <span class="status-card__label">${item.service || "Service"}</span>
      <strong>${item.label}</strong>
      <div class="panel-text mb-0">${item.details || "Sans détail complémentaire"}</div>
      ${item.assignmentSummary ? `<div class="panel-text mb-0 mt-2"><strong>${item.assignmentSummary}</strong></div>` : ""}
    </div>
  `).join("");
}

function populatePublicForm(payload) {
  const formData = payload.form;
  document.getElementById("publicSignatureTitle").textContent = formData.title || "Dossier d'attribution";
  document.getElementById("publicSignatureExpiresAt").textContent = formatPublicDateTime(payload.link.expiresAt);
  document.getElementById("publicNom").textContent = formData.beneficiaire.nom || "-";
  document.getElementById("publicPrenom").textContent = formData.beneficiaire.prenom || "-";
  document.getElementById("publicQualite").textContent = formData.beneficiaire.qualite === "elu" ? "Élu(e)" : "Agent";
  document.getElementById("publicService").textContent = formData.beneficiaire.service || formData.beneficiaire.fonction || "-";
  document.getElementById("publicMandat").textContent = formData.beneficiaire.mandat || "-";
  renderResourceList("publicMaterialResources", formData.resources.materiel || []);
  renderResourceList("publicImmaterialResources", formData.resources.immateriel || []);
  document.getElementById("publicRgpdText").innerHTML = (formData.rgpdText || []).map((line) => `<p class="rgpd-text">${line}</p>`).join("");
}

async function submitPublicSignature(signaturePad) {
  const token = getTokenFromUrl();
  const rgpdAccepted = document.getElementById("publicRgpdCheck").checked;
  const signatureDataUrl = signaturePad.toDataUrl();
  if (!rgpdAccepted) {
    window.alert("La prise de connaissance RGPD est obligatoire.");
    return;
  }
  if (!signatureDataUrl) {
    window.alert("Merci de signer le dossier avant validation.");
    return;
  }

  try {
    await requestPublicJson(`/api/signature/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      body: JSON.stringify({ rgpdAccepted, signatureDataUrl })
    });
    publicSignatureForm.classList.add("d-none");
    signatureSuccessCard.classList.remove("d-none");
  } catch (error) {
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
