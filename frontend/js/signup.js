// Gère l'inscription avec génération assistée de mot de passe
// et affichage des erreurs de parcours.
function applySignupError() {
  const errorBox = document.getElementById("signupError");
  if (!errorBox) {
    return;
  }

  const error = new URLSearchParams(window.location.search).get("error");
  if (!error) {
    return;
  }

  const messages = {
    missing_fields: "Tous les champs sont obligatoires.",
    invalid_username: "L'identifiant doit contenir entre 3 et 64 caracteres et n'utiliser que des lettres, chiffres, points, tirets ou underscores.",
    user_exists: "Cet identifiant existe deja.",
    password_mismatch: "La confirmation du mot de passe ne correspond pas.",
    password_too_short: "Le mot de passe doit contenir au moins 12 caracteres.",
    password_missing_upper: "Le mot de passe doit contenir au moins une majuscule.",
    password_missing_lower: "Le mot de passe doit contenir au moins une minuscule.",
    password_missing_digit: "Le mot de passe doit contenir au moins un chiffre.",
    password_missing_special: "Le mot de passe doit contenir au moins un caractere special."
  };

  errorBox.textContent = messages[error] || "Impossible de traiter la demande d'inscription.";
  errorBox.classList.remove("d-none");
}

function generateThemedPassword(theme = "licorne") {
  const themes = {
    licorne: {
      first: ["Licorne", "Arcane", "Cristal", "Aurore", "Etoile", "Nuage", "Paillet", "Corail"],
      second: ["violet", "sucre", "soie", "nacre", "brume", "velours", "lumiere", "satin"]
    },
    starwars: {
      first: ["Jedi", "Yoda", "Leia", "Andor", "Lando", "Ahsoka", "Rey", "Kenobi"],
      second: ["galaxie", "sabre", "force", "etoile", "rebel", "nebuleuse", "holo", "hyper"]
    },
    marvel: {
      first: ["Marvel", "Stark", "Thor", "Vision", "Loki", "Wanda", "Rocket", "Panther"],
      second: ["vibranium", "quantum", "cosmos", "hero", "arc", "multivers", "storm", "shield"]
    },
    film_francais: {
      first: ["Amelie", "Belmondo", "Truffaut", "Renoir", "Tautou", "Noiret", "Depardieu", "Audiard"],
      second: ["cinema", "paris", "camera", "dialogue", "lumiere", "ecran", "replique", "studio"]
    },
    publier: {
      first: ["Publier", "Leman", "Mairie", "Alpes", "Geneve", "Rive", "Port", "Chablais"],
      second: ["lac", "maison", "service", "rivage", "commune", "montagne", "horizon", "village"]
    }
  };
  const symbols = ["!", "@", "#", "$", "%"];
  const source = themes[theme] || themes.licorne;
  const left = source.first[Math.floor(Math.random() * source.first.length)];
  const right = source.second[Math.floor(Math.random() * source.second.length)];
  const digits = String(Math.floor(10 + Math.random() * 90));
  const symbol = symbols[Math.floor(Math.random() * symbols.length)];
  return `${left}-${right}${digits}${symbol}`;
}

function initPasswordGeneratorModal() {
  const modal = document.getElementById("passwordGeneratorModal");
  if (!modal) {
    return;
  }

  const themeSelect = document.getElementById("passwordThemeSelect");
  const valueField = document.getElementById("generatedPasswordValue");
  const refreshBtn = document.getElementById("refreshGeneratedPasswordBtn");
  const copyBtn = document.getElementById("copyGeneratedPasswordBtn");
  const applyBtn = document.getElementById("applyGeneratedPasswordBtn");
  let currentPassword = "";

  const refreshPassword = () => {
    currentPassword = generateThemedPassword(themeSelect?.value || "licorne");
    if (valueField) {
      valueField.value = currentPassword;
    }
  };

  const closeModal = () => {
    modal.classList.add("d-none");
    modal.setAttribute("aria-hidden", "true");
  };

  const openModal = () => {
    modal.classList.remove("d-none");
    modal.setAttribute("aria-hidden", "false");
    refreshPassword();
  };

  themeSelect?.addEventListener("change", refreshPassword);
  refreshBtn?.addEventListener("click", refreshPassword);
  copyBtn?.addEventListener("click", async () => {
    if (!currentPassword) {
      refreshPassword();
    }
    await navigator.clipboard.writeText(currentPassword);
  });
  applyBtn?.addEventListener("click", () => {
    if (!currentPassword) {
      refreshPassword();
    }
    const passwordInput = document.getElementById("signup_password");
    const confirmInput = document.getElementById("signup_password_confirm");
    if (passwordInput) {
      passwordInput.value = currentPassword;
    }
    if (confirmInput) {
      confirmInput.value = currentPassword;
    }
    closeModal();
  });
  modal.querySelectorAll("[data-password-modal-close='true']").forEach((element) => {
    element.addEventListener("click", closeModal);
  });

  document.getElementById("generateSignupPasswordBtn")?.addEventListener("click", openModal);
}

document.addEventListener("DOMContentLoaded", () => {
  applySignupError();
  initPasswordGeneratorModal();
  document.getElementById("copySignupPasswordBtn")?.addEventListener("click", async () => {
    const passwordInput = document.getElementById("signup_password");
    if (!passwordInput?.value) {
      return;
    }
    await navigator.clipboard.writeText(passwordInput.value);
  });
});
