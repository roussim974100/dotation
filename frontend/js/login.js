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
    session: getAppText("login.errorSession", "La session n'a pas pu être conservée. Vérifiez les cookies du navigateur puis reconnectez-vous."),
    pending: getAppText("login.errorPending", "Votre compte est en attente de validation par un administrateur."),
    disabled: getAppText("login.errorDisabled", "Votre compte est désactivé. Rapprochez-vous d'un administrateur."),
    rate_limited: getAppText("login.errorRateLimited", "Trop de tentatives de connexion. Veuillez réessayer dans quelques minutes.")
  };

  const noticeMessages = {
    signup_pending: getAppText("login.noticeSignupPending", "Votre demande d'inscription a été enregistrée. Un administrateur doit maintenant valider votre compte.")
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

function detectBrowserName() {
  const userAgent = navigator.userAgent || "";
  if (/Edg\//.test(userAgent)) {
    return "Microsoft Edge";
  }
  if (/Chrome\//.test(userAgent) && !/Edg\//.test(userAgent)) {
    return "Google Chrome";
  }
  if (/Firefox\//.test(userAgent)) {
    return "Mozilla Firefox";
  }
  if (/Safari\//.test(userAgent) && !/Chrome\//.test(userAgent) && !/Edg\//.test(userAgent)) {
    return "Safari";
  }
  return "Navigateur inconnu";
}

function detectPlatformName() {
  const platform = navigator.userAgentData?.platform || navigator.platform || "";
  const userAgent = navigator.userAgent || "";
  const source = `${platform} ${userAgent}`;
  if (/Windows/i.test(source)) {
    return "Windows";
  }
  if (/Mac/i.test(source)) {
    return "macOS";
  }
  if (/Linux/i.test(source)) {
    return "Linux";
  }
  if (/Android/i.test(source)) {
    return "Android";
  }
  if (/iPhone|iPad|iPod/i.test(source)) {
    return "iOS";
  }
  return platform || "Plateforme inconnue";
}

function buildClientDeviceLabel() {
  return `${detectPlatformName()} - ${detectBrowserName()}`;
}

function isPrivateIpv4(value) {
  return /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(value || "");
}

function extractIceCandidateAddress(candidate) {
  const raw = String(candidate?.candidate || "");
  const match = raw.match(/([a-f0-9:.]+)\s\d+\styp/i);
  return match ? match[1] : "";
}

function resolveLocalNetworkHint() {
  return new Promise((resolve) => {
    const RTCPeerConnectionCtor = window.RTCPeerConnection || window.webkitRTCPeerConnection || window.mozRTCPeerConnection;
    if (!RTCPeerConnectionCtor) {
      resolve({ localIp: "", localHostHint: "" });
      return;
    }

    const connection = new RTCPeerConnectionCtor({ iceServers: [] });
    let settled = false;
    let localIp = "";
    let localHostHint = "";

    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      connection.onicecandidate = null;
      connection.close();
      resolve({ localIp, localHostHint });
    };

    connection.onicecandidate = (event) => {
      if (!event.candidate) {
        finish();
        return;
      }
      const address = extractIceCandidateAddress(event.candidate);
      if (!address) {
        return;
      }
      if (!localIp && isPrivateIpv4(address)) {
        localIp = address;
      }
      if (!localHostHint && /\.local$/i.test(address)) {
        localHostHint = address;
      }
    };

    connection.createDataChannel("login-client-context");
    connection.createOffer()
      .then((offer) => connection.setLocalDescription(offer))
      .catch(() => finish());

    window.setTimeout(finish, 1200);
  });
}

function setHiddenValue(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.value = value || "";
  }
}

async function fetchCsrfToken() {
  try {
    const resp = await fetch("/api/csrf-token", {
      credentials: "include"
    });
    const data = await resp.json();
    setHiddenValue("csrfToken", data.token || "");
  } catch (_) {
    // silencieux — le serveur rejettera le formulaire si absent
  }
}

async function hydrateLoginClientContext() {
  await fetchCsrfToken();
  setHiddenValue("clientDeviceLabel", buildClientDeviceLabel());
  setHiddenValue("clientBrowser", detectBrowserName());
  setHiddenValue("clientPlatform", detectPlatformName());
  setHiddenValue("clientUserAgent", navigator.userAgent || "");
  setHiddenValue("clientLanguage", navigator.language || "");
  setHiddenValue("clientLanguages", Array.isArray(navigator.languages) ? navigator.languages.join(", ") : "");
  setHiddenValue("clientTimezone", Intl.DateTimeFormat().resolvedOptions().timeZone || "");
  setHiddenValue("clientScreen", window.screen ? `${window.screen.width}x${window.screen.height}` : "");
  setHiddenValue("clientViewport", `${window.innerWidth || 0}x${window.innerHeight || 0}`);
  setHiddenValue("clientCookieEnabled", String(Boolean(navigator.cookieEnabled)));
  setHiddenValue("clientPageUrl", window.location.href);

  const localContext = await resolveLocalNetworkHint().catch(() => ({ localIp: "", localHostHint: "" }));
  setHiddenValue("clientLocalIp", localContext.localIp || "");
  setHiddenValue("clientLocalHostHint", localContext.localHostHint || "");
}

document.addEventListener("DOMContentLoaded", () => {
  applyLoginTexts();
  applyLoginMessages();

  const loginForm = document.querySelector(".login-form");

  // Lancer l'hydratation immédiatement
  let contextPromise = hydrateLoginClientContext();

  loginForm?.addEventListener("submit", async (event) => {
    if (!contextPromise) {
      // L'hydratation a déjà été faite, permettre la soumission normale
      return;
    }

    // Attendre que l'hydratation se termine
    event.preventDefault();
    const pending = contextPromise;
    contextPromise = null;
    await pending.catch(() => {
      // Erreur lors de l'hydratation, mais continuer
    });

    // Maintenant que l'hydratation est complète, soumettre le formulaire
    // Utiliser FormData pour s'assurer que toutes les données sont correctement encodées
    const formData = new FormData(loginForm);
    const method = loginForm.getAttribute("method") || "POST";
    const action = loginForm.getAttribute("action") || loginForm.action || "/login";

    try {
      const response = await fetch(action, {
        method: method.toUpperCase(),
        body: formData,
        redirect: "follow",
        credentials: "include"  // IMPORTANT: Incluire les cookies (sessions)
      });

      // Rediriger vers la location finale
      if (response.redirected) {
        window.location.href = response.url;
      }
    } catch (error) {
      // En cas d'erreur, essayer la soumission normale
      loginForm.submit();
    }
  });
});
