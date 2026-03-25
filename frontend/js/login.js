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

function applyLoginError() {
  const errorBox = document.getElementById("loginError");
  if (!errorBox) {
    return;
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get("error") !== "invalid") {
    return;
  }

  errorBox.textContent = getAppText("login.errorInvalid", "Identifiants invalides.");
  errorBox.classList.remove("d-none");
}

document.addEventListener("DOMContentLoaded", () => {
  applyLoginTexts();
  applyLoginError();
});
