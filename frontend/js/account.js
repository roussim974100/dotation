// Page "Mon profil" : e-mail modifiable, nom/prenom renseignables une seule fois, identifiant fige.

const ACCOUNT_ERRORS = {
  invalid_email: "Adresse e-mail invalide.",
  invalid_name: "Le nom et le prénom ne doivent contenir que des lettres, espaces, apostrophes ou tirets.",
  identity_locked: "Ces informations ne peuvent plus être modifiées : contactez un administrateur."
};

const ACCOUNT_STATUS_LABELS = { active: "Actif", pending: "En attente de validation", disabled: "Désactivé" };

let accountProfile = null;

function accountEl(id) {
  return document.getElementById(id);
}

function accountEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function accountCsrf() {
  const response = await fetch("/api/csrf-token", { credentials: "same-origin" });
  return (await response.json()).token || "";
}

function renderAccount(profile) {
  accountProfile = profile;
  accountEl("acc_username").value = profile.username;
  [["first_name", "acc_first_name"], ["last_name", "acc_last_name"]].forEach(([key, id]) => {
    const input = accountEl(id);
    input.value = profile[key];
    input.readOnly = profile.locked[key];
  });
  accountEl("acc_email").value = profile.email;

  const editableNames = !profile.locked.first_name || !profile.locked.last_name;
  accountEl("acc_names_help").textContent = editableNames
    ? "Renseignable une seule fois : une fois enregistrés, seul un administrateur pourra modifier votre nom et votre prénom."
    : "Nom et prénom verrouillés : contactez un administrateur pour les corriger.";

  const rows = [
    ["Groupes", profile.groups.map((group) => group.label).join(", ") || "—"],
    ["Service", profile.service || "—"],
    ["Statut", ACCOUNT_STATUS_LABELS[profile.status] || profile.status],
    ["Compte créé le", profile.created_at ? new Date(profile.created_at).toLocaleDateString("fr-FR") : "—"]
  ];
  accountEl("accountAccess").innerHTML = rows.map(([label, value]) =>
    `<dt class="col-5 text-muted fw-normal">${accountEscape(label)}</dt><dd class="col-7">${accountEscape(value)}</dd>`).join("");
}

function showAccountMessage(level, text) {
  const box = accountEl("accountResult");
  box.className = `alert alert-${level} mt-3`;
  box.textContent = text;
}

async function loadAccount() {
  try {
    const response = await fetch("/api/account", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error();
    renderAccount(await response.json());
  } catch (error) {
    showAccountMessage("danger", "Impossible de charger votre profil.");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = accountEl("accountForm");
  if (!form) return;
  accountEl("accountPasswordBtn").addEventListener("click", () => openPasswordChangeModal());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = accountEl("accountError");
    errorBox.classList.add("d-none");
    const payload = { email: accountEl("acc_email").value.trim() };
    const settingNames = [];
    [["first_name", "acc_first_name"], ["last_name", "acc_last_name"]].forEach(([key, id]) => {
      const value = accountEl(id).value.trim();
      if (!accountProfile.locked[key] && value) {
        payload[key] = value;
        settingNames.push(key);
      }
    });
    if (settingNames.length && !(await askConfirm("Votre nom et votre prénom ne pourront plus être modifiés par vous après enregistrement. Confirmer ?", { confirmLabel: "Enregistrer définitivement" }))) {
      return;
    }
    const button = accountEl("accountSaveBtn");
    button.disabled = true;
    try {
      const response = await fetch("/api/account", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": await accountCsrf() },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        errorBox.textContent = ACCOUNT_ERRORS[data.error] || data.message || "Enregistrement impossible.";
        errorBox.classList.remove("d-none");
        return;
      }
      renderAccount(data);
      showAccountMessage("success", "Vos informations ont été enregistrées.");
    } catch (error) {
      errorBox.textContent = "Erreur de connexion au serveur.";
      errorBox.classList.remove("d-none");
    } finally {
      button.disabled = false;
    }
  });

  loadAccount();
});
