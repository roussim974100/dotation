// QR code d'un lien de signature (3.66.0) : quand la personne est là, elle le scanne avec son téléphone au lieu de recevoir le lien
// par e-mail. Le QR est généré dans le navigateur par la bibliothèque embarquée js/vendor/qrcode-generator.js (MIT, aucune requête
// réseau : fonctionne sur un intranet sans accès à Internet). Ce fichier ne fait qu'afficher ; les liens sont créés par storage.js.

const SIGNATURE_QR_LOCAL_HOSTS = ["localhost", "127.0.0.1", "::1", "[::1]"];

function signatureQrEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

// Un lien construit sur localhost n'est utilisable que depuis cet ordinateur : le téléphone qui scannerait n'y accède pas.
function isLocalSignatureUrl(url) {
  try {
    return SIGNATURE_QR_LOCAL_HOSTS.includes(new URL(url).hostname);
  } catch (error) {
    return false;
  }
}

function buildSignatureQrSvg(text) {
  if (typeof qrcode !== "function") {
    throw new Error("Le générateur de QR code n'est pas chargé.");
  }
  const code = qrcode(0, "M"); // taille automatique, correction d'erreur moyenne
  code.addData(String(text));
  code.make();
  return code.createSvgTag({ cellSize: 8, margin: 4, scalable: true, alt: "QR code du lien de signature", title: "Lien de signature" });
}

// Affiche le QR avec un nombre ENTIER de pixels par module : à une échelle fractionnaire, les bords deviennent flous et certains
// lecteurs ne le décodent plus (constaté : 7,8 px par module illisible, 8 px lisible).
function sizeSignatureQr(svg) {
  if (!svg) return;
  const viewBox = (svg.getAttribute("viewBox") || "").split(/\s+/).map(Number);
  const cells = viewBox[2] / 8; // cellSize de buildSignatureQrSvg
  if (!Number.isFinite(cells) || cells <= 0) return;
  const available = Math.min(340, window.innerWidth - 100);
  const pixels = Math.max(3, Math.floor(available / cells));
  svg.setAttribute("shape-rendering", "crispEdges");
  svg.style.width = `${cells * pixels}px`;
  svg.style.height = `${cells * pixels}px`;
}

function closeSignatureQrDialog() {
  const modal = document.getElementById("signatureQrModal");
  if (!modal) return;
  modal.classList.add("d-none");
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = "";
}

// options : { url, title, subtitle, expiresAt }
function showSignatureQrDialog(options = {}) {
  const url = String(options.url || "");
  if (!url) {
    showToast("Aucun lien de signature à afficher.", "error");
    return;
  }
  let svg;
  try {
    svg = buildSignatureQrSvg(url);
  } catch (error) {
    showToast(error.message || "Impossible de générer le QR code.", "error");
    return;
  }
  let modal = document.getElementById("signatureQrModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.className = "password-generator-modal d-none";
    modal.id = "signatureQrModal";
    modal.setAttribute("aria-hidden", "true");
    document.body.appendChild(modal);
  }
  const expiry = options.expiresAt ? new Date(options.expiresAt) : null;
  const expiryText = expiry && !Number.isNaN(expiry.getTime())
    ? `Ce lien est valable jusqu'au ${expiry.toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short" })}.` : "";
  modal.innerHTML = `
    <div class="password-generator-modal__backdrop" data-signature-qr-close="true"></div>
    <div class="password-generator-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="signatureQrTitle">
      <div class="password-generator-modal__header">
        <div>
          <p class="panel-eyebrow">Signature en face à face</p>
          <h2 class="section-title" id="signatureQrTitle">${signatureQrEscape(options.title || "Lien de signature")}</h2>
        </div>
        <button class="btn btn-outline-secondary btn-sm" type="button" data-signature-qr-close="true">Fermer</button>
      </div>
      <div class="password-generator-modal__content text-center">
        ${options.subtitle ? `<p class="mb-2">${signatureQrEscape(options.subtitle)}</p>` : ""}
        <p class="small text-muted mb-2">Demandez à la personne de scanner ce code avec l'appareil photo de son téléphone : la page de signature s'ouvre.</p>
        <div class="signature-qr" style="background:#fff;padding:12px;border-radius:12px;display:inline-block;max-width:100%;line-height:0" data-signature-qr-image="true">${svg}</div>
        ${isLocalSignatureUrl(url)
          ? '<p class="small text-danger mt-2 mb-0" role="alert">Ce lien pointe vers cet ordinateur (localhost) : un téléphone ne pourra pas l\'ouvrir. Ouvrez l\'application avec l\'adresse du serveur.</p>' : ""}
        ${expiryText ? `<p class="small text-muted mt-2 mb-0">${signatureQrEscape(expiryText)}</p>` : ""}
        <p class="small mt-2 mb-0 text-break"><a href="${signatureQrEscape(url)}" target="_blank" rel="noopener noreferrer">${signatureQrEscape(url)}</a></p>
      </div>
      <div class="password-generator-modal__actions password-generator-modal__actions--sticky">
        <button class="btn btn-outline-primary" type="button" id="signatureQrCopy">Copier le lien</button>
        <button class="btn btn-primary" type="button" data-signature-qr-close="true">Fermer</button>
      </div>
    </div>`;
  modal.classList.remove("d-none");
  modal.setAttribute("aria-hidden", "false");
  sizeSignatureQr(modal.querySelector("[data-signature-qr-image] svg"));
  modal.querySelectorAll("[data-signature-qr-close]").forEach((button) => button.addEventListener("click", closeSignatureQrDialog));
  modal.querySelector("#signatureQrCopy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
      showToast("Lien copié.", "success");
    } catch (error) {
      window.prompt("Copiez ce lien :", url);
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.getElementById("signatureQrModal")?.classList.contains("d-none") === false) closeSignatureQrDialog();
});
