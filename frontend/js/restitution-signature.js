const publicRestitutionSignatureForm = document.getElementById("publicRestitutionSignatureForm");
const restitutionSignatureLoader = document.getElementById("restitutionSignatureLoader");
const restitutionSignatureErrorCard = document.getElementById("restitutionSignatureErrorCard");
const restitutionSignatureSuccessCard = document.getElementById("restitutionSignatureSuccessCard");

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
  restitutionSignatureLoader.classList.add("is-hidden");
  publicRestitutionSignatureForm.classList.add("d-none");
  restitutionSignatureSuccessCard.classList.add("d-none");
  restitutionSignatureErrorCard.classList.remove("d-none");
  document.getElementById("restitutionSignatureErrorText").textContent = message;
}

function initPublicRestitutionSignaturePad() {
  const canvas = document.getElementById("publicRestitutionSignatureCanvas");
  const clearBtn = document.getElementById("clearPublicRestitutionSignatureBtn");
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
    resize: resizeCanvas
  };
}

function renderPublicRestitutionItems(items = []) {
  const target = document.getElementById("publicRestitutionItems");
  if (!target) {
    return;
  }
  if (!items.length) {
    target.innerHTML = "<p class=\"panel-text mb-0\">Aucun matériel n'a été renseigné pour cette restitution.</p>";
    return;
  }
  target.innerHTML = items.map((item) => `
    <div class="status-card">
      <span class="status-card__label">${item.label}</span>
      <strong>${item.stateLabel}</strong>
      <div class="panel-text mb-0">${item.details || "Sans détail complémentaire"}</div>
      ${item.notes ? `<div class="panel-text mb-0 mt-2"><strong>Commentaire :</strong> ${item.notes}</div>` : ""}
    </div>
  `).join("");
}

function populatePublicRestitutionForm(payload) {
  const formData = payload.form;
  const restitution = formData.restitution || {};
  document.getElementById("publicRestitutionSignatureTitle").textContent = `Restitution - ${formData.title || "Dossier"}`;
  document.getElementById("publicRestitutionExpiresAt").textContent = formatPublicRestitutionDateTime(payload.link.expiresAt);
  document.getElementById("publicRestitutionNom").textContent = formData.beneficiaire.nom || "-";
  document.getElementById("publicRestitutionPrenom").textContent = formData.beneficiaire.prenom || "-";
  document.getElementById("publicRestitutionQualite").textContent = formData.beneficiaire.qualite === "elu" ? "Élu(e)" : "Agent";
  document.getElementById("publicRestitutionService").textContent = formData.beneficiaire.service || formData.beneficiaire.fonction || "-";
  document.getElementById("publicRestitutionMandat").textContent = formData.beneficiaire.mandat || "-";
  document.getElementById("publicRestitutionReturnedAt").textContent = formatPublicRestitutionDateTime(restitution.returnedAt);
  document.getElementById("publicRestitutionReason").textContent = restitution.reason || "-";
  document.getElementById("publicRestitutionNotes").textContent = restitution.notes || "-";
  renderPublicRestitutionItems(restitution.items || []);
}

async function submitPublicRestitutionSignature(signaturePad) {
  const token = getRestitutionTokenFromUrl();
  const signatureDataUrl = signaturePad.toDataUrl();
  if (!signatureDataUrl) {
    window.alert("Merci de signer la restitution avant validation.");
    return;
  }

  try {
    await requestRestitutionSignatureJson(`/api/restitution-signature/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      body: JSON.stringify({ signatureDataUrl })
    });
    publicRestitutionSignatureForm.classList.add("d-none");
    restitutionSignatureSuccessCard.classList.remove("d-none");
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature n'est plus valide.",
      expired: "Ce lien de signature a expiré.",
      used: "Cette restitution a déjà été signée.",
      revoked: "Ce lien de signature a été révoqué."
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

  try {
    const payload = await requestRestitutionSignatureJson(`/api/restitution-signature/${encodeURIComponent(token)}`);
    populatePublicRestitutionForm(payload);
    restitutionSignatureLoader.classList.add("is-hidden");
    publicRestitutionSignatureForm.classList.remove("d-none");
    const signaturePad = initPublicRestitutionSignaturePad();
    signaturePad.resize();
    document.getElementById("submitPublicRestitutionSignatureBtn").addEventListener("click", () => {
      void submitPublicRestitutionSignature(signaturePad);
    });
  } catch (error) {
    const messages = {
      invalid_link: "Ce lien de signature de restitution n'est pas reconnu.",
      expired: "Ce lien de signature de restitution a expiré.",
      used: "Cette restitution a déjà été signée.",
      revoked: "Ce lien de signature de restitution a été révoqué."
    };
    showRestitutionSignatureError(messages[error.message] || "Impossible de charger ce lien de signature de restitution.");
  }
});
