// Diagnostic d'un dossier de restitution reste « en cours » (partial_return) + cloture forcee quand la seule
// raison est un objet « Non restitue » qui ne reviendra jamais individuellement (ex. materiel mutualise).
// Scope volontairement limite a ce cas : les autres raisons de blocage (signature a distance non recueillie...)
// sont juste signalees, sans action de forcage ici.

const STATUS_LABELS = {
  active: "Attribution active",
  partial_return: "Restitution partielle",
  awaiting_signature: "En attente de signature",
  returned: "Restitution terminée",
  cancelled: "Annulé"
};

const FIXED_ITEM_LABELS = {
  ordinateur: "Ordinateur", ecran: "Écran", telephone: "Téléphone", tablette: "Tablette", vehicule: "Véhicule",
  badge: "Badge d'accès", cles: "Clé(s)", veste: "Veste", chaussuresSecurite: "Chaussures de sécurité",
  autre: "Autre matériel", vpn: "VPN", email: "Email", zoneAlarme: "Zone alarme"
};

function blocageEsc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function itemLabel(data, itemKey) {
  const resource = (data.resources?.additional || []).find((r) => String(r.code || r.id) === String(itemKey));
  return resource?.label || FIXED_ITEM_LABELS[itemKey] || itemKey;
}

async function initRestitutionBlockagePage() {
  const id = new URLSearchParams(window.location.search).get("id");
  const loader = document.getElementById("blocageLoader");
  const reasonBody = document.getElementById("blocageReasonBody");
  const forceCard = document.getElementById("blocageForceCard");

  if (!id) {
    reasonBody.innerHTML = "<p class=\"text-danger\">Aucun dossier indiqué (paramètre « id » manquant dans l'adresse).</p>";
    loader?.classList.add("is-hidden");
    return;
  }

  try {
    const session = await getSessionInfo();
    const canForceClose = Boolean(session?.permissions?.includes("*") || session?.permissions?.includes("forms.restitution"));

    const form = await requestJson(`/api/forms/${encodeURIComponent(id)}`);
    const data = form.data;
    const status = data.workflow?.status || "draft";
    const fullName = `${data.beneficiaire?.prenom || ""} ${data.beneficiaire?.nom || ""}`.trim();

    document.getElementById("blocageTitle").textContent = fullName || form.summary?.title || "Dossier";
    document.getElementById("blocageSubtitle").textContent = data.beneficiaire?.service ? `Service : ${data.beneficiaire.service}` : "";
    document.getElementById("blocageStatusPill").textContent = STATUS_LABELS[status] || status;

    if (status !== "partial_return") {
      reasonBody.innerHTML = `<p>Ce dossier n'est pas (ou plus) bloqué : son statut actuel est « ${blocageEsc(STATUS_LABELS[status] || status)} ».</p>`;
      loader?.classList.add("is-hidden");
      return;
    }

    const items = data.restitution?.items || {};
    const pendingItems = Object.entries(items).filter(([, state]) => (state || {}).state === "non_restitue");

    if (!pendingItems.length) {
      reasonBody.innerHTML = `
        <p>Ce dossier reste « en cours » pour une autre raison que celle couverte par cet outil (par exemple une signature à distance pas encore recueillie).</p>
        <p>Vérifiez le mode de signature de la restitution sur <a href="restitution.html?id=${encodeURIComponent(id)}">la page de restitution</a>.</p>
      `;
      loader?.classList.add("is-hidden");
      return;
    }

    reasonBody.innerHTML = `
      <p>${pendingItems.length > 1 ? "Ces objets sont" : "Cet objet est"} marqué « Non restitué », ce qui maintient le dossier « en cours » tant que ce n'est pas résolu :</p>
      <ul>
        ${pendingItems.map(([key, state]) => `<li><strong>${blocageEsc(itemLabel(data, key))}</strong>${state.notes ? ` — ${blocageEsc(state.notes)}` : ""}</li>`).join("")}
      </ul>
      <p>Pour résoudre normalement : rouvrez <a href="restitution.html?id=${encodeURIComponent(id)}">la page de restitution</a> et repassez l'objet sur « Restitué », « Perdu » ou « Autre ».</p>
    `;

    if (canForceClose) {
      forceCard.classList.remove("d-none");
      document.getElementById("forceCloseBtn").addEventListener("click", async () => {
        const confirmed = await askConfirm(
          "Clôturer ce dossier malgré " + (pendingItems.length > 1 ? "ces objets" : "cet objet") + " marqué « Non restitué » ? " +
          "L'état de l'objet n'est pas modifié dans l'historique ; seul le dossier passe à « Terminée ». Action journalisée.",
          { confirmLabel: "Clôturer quand même", cancelLabel: "Annuler" }
        );
        if (!confirmed) return;
        try {
          await requestJson(`/api/forms/${encodeURIComponent(id)}/restitution`, {
            method: "PATCH",
            body: JSON.stringify({ closeAnyway: true })
          });
          showToast("Dossier clôturé.", "success");
          await initRestitutionBlockagePage();
        } catch (error) {
          showToast(error.message || "Impossible de clôturer le dossier.", "error");
        }
      });
    }

    loader?.classList.add("is-hidden");
  } catch (error) {
    reasonBody.innerHTML = `<p class="text-danger">${blocageEsc(error.message === "not_found" ? "Ce dossier n'existe pas ou plus." : "Impossible de charger ce dossier.")}</p>`;
    loader?.classList.add("is-hidden");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void initRestitutionBlockagePage();
});
