function getAppText(path, fallback = "") {
  const keys = path.split(".");
  let current = window.APP_TEXT || {};
  for (const key of keys) {
    current = current?.[key];
  }
  return current ?? fallback;
}

function applyLoginTexts() {
  document.querySelectorAll("[data-text]").forEach((element) => {
    const value = getAppText(element.dataset.text, element.textContent);
    element.textContent = value;
  });

  document.querySelectorAll("[data-placeholder]").forEach((element) => {
    element.placeholder = getAppText(element.dataset.placeholder, element.placeholder);
  });

  document.title = getAppText("login.title", document.title);
}

function applyLoginMessages() {
  const errorBox = document.getElementById("loginError");
  const noticeBox = document.getElementById("loginNotice");
  if (!errorBox || !noticeBox) {
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const error = params.get("error");
  const notice = params.get("notice");

  const errorMessages = {
    invalid: getAppText("login.errorInvalid", "Identifiants invalides."),
    session: getAppText("login.errorSession", "La session n'a pas pu etre conservee. Verifiez les cookies du navigateur puis reconnectez-vous."),
    pending: getAppText("login.errorPending", "Votre compte est en attente de validation par un administrateur."),
    disabled: getAppText("login.errorDisabled", "Votre compte est desactive. Rapprochez-vous d'un administrateur.")
  };

  const noticeMessages = {
    signup_pending: getAppText("login.noticeSignupPending", "Votre demande d'inscription a ete enregistree. Un administrateur doit maintenant valider votre compte.")
  };

  if (error && errorMessages[error]) {
    errorBox.textContent = errorMessages[error];
    errorBox.classList.remove("d-none");
  }

  if (notice && noticeMessages[notice]) {
    noticeBox.textContent = noticeMessages[notice];
    noticeBox.classList.remove("d-none");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  applyLoginTexts();
  applyLoginMessages();
});
