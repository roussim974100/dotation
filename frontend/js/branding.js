// Branding public partagé par toutes les pages frontend.
// Le logo reste masqué jusqu'à ce que le bon visuel soit prêt,
// ce qui évite le flash du fallback local avant le vrai logo configuré.
const BRANDING_CACHE_KEY = "appBrandingPublicCacheV1";
  const APP_BUILD_VERSION = "3.8.1";
const APP_FIXED_NAME = "A quai";
const APP_PRIMARY_LOGO_URL = "/assets/a-quai-hero.png";
const COOKIECONSENT_VERSION = "3.1.0";
const COOKIECONSENT_CSS_URL = `https://cdn.jsdelivr.net/gh/orestbida/cookieconsent@${COOKIECONSENT_VERSION}/dist/cookieconsent.css`;
const COOKIECONSENT_JS_URL = `https://cdn.jsdelivr.net/gh/orestbida/cookieconsent@${COOKIECONSENT_VERSION}/dist/cookieconsent.umd.js`;
const CLIENT_CONTEXT_COOKIE_NAME = "dotation_client_context_v1";
const BRAND_THEME_PRESETS = {
  institutionnel: {
    light: {
      brand: "#0f5b8d",
      brandDark: "#0a4267",
      brandSoft: "#dbeaf3",
      accent: "#d9a441",
      surface: "#ffffff",
      surfaceAlt: "#f5f8fb",
      text: "#1f2933",
      muted: "#607080",
      border: "#d4dde6"
    },
    dark: {
      brand: "#68a7d1",
      brandDark: "#0f5b8d",
      brandSoft: "#17354a",
      accent: "#e3b85f",
      surface: "#10212d",
      surfaceAlt: "#163040",
      text: "#edf4f8",
      muted: "#acc0ce",
      border: "#2d4b5f"
    }
  },
  lac_montagne: {
    light: {
      brand: "#1e6f74",
      brandDark: "#174f53",
      brandSoft: "#d7eeec",
      accent: "#9b7b45",
      surface: "#ffffff",
      surfaceAlt: "#f2f7f6",
      text: "#20313a",
      muted: "#5d7682",
      border: "#cfdedd"
    },
    dark: {
      brand: "#5fb2b7",
      brandDark: "#1e6f74",
      brandSoft: "#15353a",
      accent: "#c6a26a",
      surface: "#0f1d22",
      surfaceAlt: "#16282f",
      text: "#e7f4f3",
      muted: "#a7c2c4",
      border: "#335259"
    }
  },
  ardoise: {
    light: {
      brand: "#43576b",
      brandDark: "#2f4050",
      brandSoft: "#e2e8ee",
      accent: "#c48d45",
      surface: "#ffffff",
      surfaceAlt: "#f5f7fa",
      text: "#22303c",
      muted: "#677786",
      border: "#d6dfe7"
    },
    dark: {
      brand: "#8da4b8",
      brandDark: "#43576b",
      brandSoft: "#1d2832",
      accent: "#d3a05c",
      surface: "#12181f",
      surfaceAlt: "#1a232d",
      text: "#eef3f7",
      muted: "#aeb9c3",
      border: "#364350"
    }
  },
  sable: {
    light: {
      brand: "#9b6f3e",
      brandDark: "#77522d",
      brandSoft: "#f3e9dc",
      accent: "#3f7b8a",
      surface: "#fffdfa",
      surfaceAlt: "#fbf5ee",
      text: "#332820",
      muted: "#7b6a5b",
      border: "#e5d8ca"
    },
    dark: {
      brand: "#d2a06a",
      brandDark: "#9b6f3e",
      brandSoft: "#38281a",
      accent: "#74aebe",
      surface: "#1c1712",
      surfaceAlt: "#272018",
      text: "#f7efe6",
      muted: "#c2b2a2",
      border: "#4d3e2f"
    }
  },
  foret: {
    light: {
      brand: "#2f6d4f",
      brandDark: "#24513b",
      brandSoft: "#dceee4",
      accent: "#c89b49",
      surface: "#ffffff",
      surfaceAlt: "#f4f8f5",
      text: "#20332a",
      muted: "#61786b",
      border: "#d3e1d8"
    },
    dark: {
      brand: "#68b388",
      brandDark: "#2f6d4f",
      brandSoft: "#183225",
      accent: "#dfb367",
      surface: "#101914",
      surfaceAlt: "#17231c",
      text: "#edf5f0",
      muted: "#adc4b7",
      border: "#345241"
    }
  }
};

window.APP_BRANDING = null;
let clientContextBootPromise = null;
let cookieConsentBootPromise = null;
let cookieConsentScheduled = false;

function getBrandLogos() {
  return Array.from(document.querySelectorAll(".app-logo[data-brand-logo]"));
}

function syncBrandLogos(settings) {
  getBrandLogos().forEach((logo) => {
    logo.alt = `Logo ${APP_FIXED_NAME}`;
    if (logo.getAttribute("src") !== APP_PRIMARY_LOGO_URL) {
      logo.setAttribute("src", APP_PRIMARY_LOGO_URL);
    }
  });
}

function bindHomeBrandLinks() {
  document.querySelectorAll(".app-brand[data-home-link]").forEach((brand) => {
    if (brand.dataset.homeLinkBound) {
      return;
    }
    brand.dataset.homeLinkBound = "true";
    brand.setAttribute("role", "link");
    brand.setAttribute("tabindex", "0");
    brand.style.cursor = "pointer";
    const goHome = () => {
      window.location.href = "index.html";
    };
    brand.addEventListener("click", (event) => {
      const interactive = event.target.closest("a, button, input, select, textarea, label");
      if (interactive) {
        return;
      }
      goHome();
    });
    brand.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        goHome();
      }
    });
  });
}

function ensureAppFooter() {
  if (document.querySelector("[data-app-footer]")) {
    return;
  }

  const targetBody = document.body;
  if (!targetBody) {
    return;
  }

  const footer = document.createElement("footer");
  footer.className = "app-footer no-print";
  footer.setAttribute("data-app-footer", "true");

  const container = document.createElement("div");
  container.className = "container app-footer__inner";

  const grid = document.createElement("div");
  grid.className = "app-footer__grid";

  const identityColumn = document.createElement("div");
  identityColumn.className = "app-footer__column";
  const identityWrap = document.createElement("div");
  identityWrap.className = "app-footer__identity";
  const appName = document.createElement("strong");
  appName.className = "app-footer__app";
  appName.setAttribute("data-brand-app-name", "");
  appName.textContent = APP_FIXED_NAME;
  const version = document.createElement("span");
  version.className = "app-footer__version";
  version.textContent = `Version ${APP_BUILD_VERSION}`;
  identityWrap.append(appName, version);
  const identityText = document.createElement("p");
  identityText.className = "app-footer__text";
  identityText.textContent = "Application métier dédiée au suivi des attributions de ressources et des restitutions au sein de la commune.";
  identityColumn.append(identityWrap, identityText);

  const navigationColumn = document.createElement("div");
  navigationColumn.className = "app-footer__column";
  const navigationHeading = document.createElement("span");
  navigationHeading.className = "app-footer__heading";
  navigationHeading.textContent = "Navigation";
  const navigation = document.createElement("nav");
  navigation.className = "app-footer__links";
  navigation.setAttribute("aria-label", "Navigation de pied de page");
  const aboutLink = document.createElement("a");
  aboutLink.href = "/about.html";
  aboutLink.textContent = "\u00C0 propos";
  const contactLink = document.createElement("a");
  contactLink.href = "/contact.html";
  contactLink.textContent = "Contact";
  navigation.append(aboutLink, contactLink);
  navigationColumn.append(navigationHeading, navigation);

  const supportColumn = document.createElement("div");
  supportColumn.className = "app-footer__column";
  const supportHeading = document.createElement("span");
  supportHeading.className = "app-footer__heading";
  supportHeading.textContent = "Support";
  const supportContact = document.createElement("div");
  supportContact.className = "app-footer__contact";
  const supportLabel = document.createElement("span");
  supportLabel.textContent = "Assistance applicative :";
  const supportMail = document.createElement("a");
  supportMail.setAttribute("data-brand-support-email-link", "");
  supportMail.setAttribute("data-brand-support-email-text", "");
  supportMail.href = "#";
  supportMail.textContent = "";
  supportContact.append(supportLabel, supportMail);
  const supportText = document.createElement("p");
  supportText.className = "app-footer__text";
  supportText.setAttribute("data-brand-support-credit", "");
  supportText.innerHTML = 'Développé par <a href="mailto:computing.bs@gmail.com">Samir Bassim</a>.';
  const supportLogo = document.createElement("img");
  supportLogo.className = "app-footer__org-logo";
  supportLogo.setAttribute("data-brand-org-logo", "");
  supportLogo.alt = "";
  supportLogo.hidden = true;
  supportColumn.append(supportHeading, supportContact, supportText);
  supportColumn.appendChild(supportLogo);

  grid.append(identityColumn, navigationColumn, supportColumn);

  const bottom = document.createElement("div");
  bottom.className = "app-footer__bottom";
  const copyright = document.createElement("span");
  copyright.append(document.createTextNode("\u00A9 "));
  const year = document.createElement("span");
  year.setAttribute("data-app-year", "");
  year.textContent = String(new Date().getFullYear());
  const org = document.createElement("span");
  org.setAttribute("data-brand-org", "");
  org.textContent = APP_FIXED_NAME;
  copyright.append(year, document.createTextNode(" "), org, document.createTextNode(". Tous droits réservés."));
  const cookiesButton = document.createElement("button");
  cookiesButton.className = "app-footer__cookies";
  cookiesButton.type = "button";
  cookiesButton.setAttribute("data-cc", "show-preferencesModal");
  cookiesButton.textContent = "Cookies";
  bottom.append(copyright, cookiesButton);

  container.append(grid, bottom);
  footer.appendChild(container);
  targetBody.appendChild(footer);

  footer.querySelector(".app-footer__cookies")?.addEventListener("click", async () => {
    const CookieConsent = await bootCookieConsent();
    CookieConsent?.showPreferences?.();
  });
}

function writeCookie(name, value, maxAgeSeconds) {
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    "SameSite=Lax"
  ];
  if (typeof maxAgeSeconds === "number") {
    parts.push(`Max-Age=${maxAgeSeconds}`);
  }
  document.cookie = parts.join("; ");
}

function removeCookie(name) {
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

function ensureCookieConsentStylesheet() {
  if (document.querySelector(`link[data-cookieconsent-css="${COOKIECONSENT_VERSION}"]`)) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = COOKIECONSENT_CSS_URL;
  link.setAttribute("data-cookieconsent-css", COOKIECONSENT_VERSION);
  document.head.appendChild(link);
}

function revealBrandLogos() {
  // Le logo courant est déjà chargé directement par le HTML.
}

function hideBrandLogos() {
  // Le masquage n'est plus nécessaire maintenant que le src HTML
  // pointe déjà vers le logo courant de l'application.
}

function readBrandingCache() {
  try {
    const raw = localStorage.getItem(BRANDING_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function writeBrandingCache(settings) {
  try {
    localStorage.setItem(BRANDING_CACHE_KEY, JSON.stringify(settings));
  } catch (error) {
    // Cache facultatif.
  }
}

function encodeCookiePayload(payload) {
  try {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  } catch (error) {
    return "";
  }
}

function persistClientContextCookie(payload) {
  const encoded = encodeCookiePayload(payload);
  if (!encoded) {
    return;
  }
  writeCookie(CLIENT_CONTEXT_COOKIE_NAME, encoded, 60 * 60 * 24 * 7);
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
  if (/Safari\//.test(userAgent) && !/Chrome\//.test(userAgent)) {
    return "Safari";
  }
  return "Navigateur";
}

function detectPlatformName() {
  return navigator.userAgentData?.platform || navigator.platform || "Poste";
}

function buildClientDeviceLabel() {
  return `${detectPlatformName()} - ${detectBrowserName()}`;
}

function isPrivateIpv4(value) {
  return /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(value || "");
}

function extractIceCandidateAddress(candidate) {
  const raw = String(candidate?.candidate || "");
  const parts = raw.split(" ");
  return parts[4] || "";
}

function resolveLocalNetworkHint(timeoutMs = 1200) {
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

    connection.createDataChannel("client-context");
    connection.createOffer()
      .then((offer) => connection.setLocalDescription(offer))
      .catch(() => finish());

    window.setTimeout(finish, timeoutMs);
  });
}

async function fetchServerSeenClientContext() {
  try {
    const response = await fetch("/api/client-context", {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!response.ok) {
      return {};
    }
    return await response.json();
  } catch (error) {
    return {};
  }
}

async function bootClientContext() {
  if (!window.CookieConsent?.acceptedCategory?.("client_context")) {
    return {};
  }
  if (clientContextBootPromise) {
    return clientContextBootPromise;
  }

  clientContextBootPromise = Promise.all([
    resolveLocalNetworkHint(),
    fetchServerSeenClientContext()
  ]).then(([localContext, serverContext]) => {
    const payload = {
      deviceLabel: buildClientDeviceLabel(),
      browser: detectBrowserName(),
      platform: detectPlatformName(),
      localIp: localContext.localIp || "",
      localHostHint: localContext.localHostHint || "",
      serverSeenIp: serverContext.serverSeenIp || serverContext.realIp || "",
      capturedAt: new Date().toISOString()
    };
    persistClientContextCookie(payload);
    return payload;
  }).catch(() => ({}));

  return clientContextBootPromise;
}

function clearClientContextCookie() {
  clientContextBootPromise = null;
  removeCookie(CLIENT_CONTEXT_COOKIE_NAME);
}

function syncClientContextConsent() {
  if (window.CookieConsent?.acceptedCategory?.("client_context")) {
    void bootClientContext();
    return;
  }
  clearClientContextCookie();
}

function loadCookieConsentScript() {
  if (window.CookieConsent?.run) {
    return Promise.resolve(window.CookieConsent);
  }

  const existing = document.querySelector(`script[data-cookieconsent-js="${COOKIECONSENT_VERSION}"]`);
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(window.CookieConsent), { once: true });
      existing.addEventListener("error", () => reject(new Error("cookieconsent_load_failed")), { once: true });
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = COOKIECONSENT_JS_URL;
    script.defer = true;
    script.setAttribute("data-cookieconsent-js", COOKIECONSENT_VERSION);
    script.addEventListener("load", () => resolve(window.CookieConsent), { once: true });
    script.addEventListener("error", () => reject(new Error("cookieconsent_load_failed")), { once: true });
    document.head.appendChild(script);
  });
}

async function bootCookieConsent() {
  if (cookieConsentBootPromise) {
    return cookieConsentBootPromise;
  }

  ensureCookieConsentStylesheet();
  cookieConsentBootPromise = loadCookieConsentScript().then((CookieConsent) => {
    if (!CookieConsent?.run) {
      throw new Error("cookieconsent_unavailable");
    }

    CookieConsent.run({
      root: document.body,
      mode: "opt-in",
      cookie: {
        name: "dotation_cookie_preferences",
        expiresAfterDays: 180
      },
      guiOptions: {
        consentModal: {
          layout: "box",
          position: "bottom right",
          equalWeightButtons: true,
          flipButtons: false
        },
        preferencesModal: {
          layout: "box",
          equalWeightButtons: true,
          flipButtons: false
        }
      },
      categories: {
        necessary: {
          enabled: true,
          readOnly: true
        },
        client_context: {}
      },
      onFirstConsent: syncClientContextConsent,
      onConsent: syncClientContextConsent,
      onChange: syncClientContextConsent,
      language: {
        default: "fr",
        translations: {
          fr: {
            consentModal: {
              title: "Cookies techniques",
              description: "Nous utilisons des cookies indispensables au fonctionnement de l'application. Vous pouvez afficher les d\u00e9tails pour consulter les finalit\u00e9s et les dur\u00e9es de conservation.",
              acceptAllBtn: "Accepter",
              acceptNecessaryBtn: "Refuser",
              showPreferencesBtn: "D\u00e9tails"
            },
            preferencesModal: {
              title: "Pr\u00e9f\u00e9rences cookies",
              acceptAllBtn: "Accepter",
              acceptNecessaryBtn: "Refuser",
              savePreferencesBtn: "Enregistrer mes choix",
              closeIconLabel: "Fermer",
              serviceCounterLabel: "Service|Services",
              sections: [
                {
                  title: "Votre choix",
                  description: "Vous pouvez g\u00e9rer ici les cookies utilis\u00e9s par l'application. Les cookies strictement n\u00e9cessaires restent actifs pour la connexion et la s\u00e9curit\u00e9."
                },
                {
                  title: "Cookies indispensables",
                  description: "Ils maintiennent la session utilisateur, la s\u00e9curit\u00e9 et le bon fonctionnement de l'application. Ils ne peuvent pas \u00eatre d\u00e9sactiv\u00e9s.",
                  linkedCategory: "necessary"
                },
                {
                  title: "Journal r\u00e9seau et poste",
                  description: "Avec votre accord, un cookie technique conserve le type de poste, le navigateur, l'IP LAN si le navigateur l'expose, et l'IP WAN d\u00e9tect\u00e9e c\u00f4t\u00e9 serveur pour enrichir le journal d'activit\u00e9.",
                  linkedCategory: "client_context"
                },
                {
                  title: "D\u00e9tails techniques",
                  description: "<ul class=\"cc-cookie-details\"><li><strong>publier_session</strong> : cookie indispensable pour l'authentification et la s\u00e9curit\u00e9. Dur\u00e9e : session navigateur.</li><li><strong>dotation_cookie_preferences</strong> : m\u00e9morise votre choix de consentement. Dur\u00e9e : 180 jours.</li><li><strong>dotation_client_context_v1</strong> : m\u00e9morise, avec votre accord, le type de poste, le navigateur, l'IP LAN si disponible et l'IP WAN vue par le serveur. Dur\u00e9e : 7 jours.</li></ul>"
                }
              ]
            }
          }
        }
      }
    });

    syncClientContextConsent();
    return CookieConsent;
  }).catch((error) => {
    console.error("cookieconsent_boot_failed", error);
    return null;
  });

  return cookieConsentBootPromise;
}

function scheduleCookieConsentBoot() {
  if (cookieConsentScheduled) {
    return;
  }
  cookieConsentScheduled = true;

  const runLater = () => {
    window.setTimeout(() => {
      void bootCookieConsent();
    }, 250);
  };

  if (document.readyState === "complete") {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(() => runLater(), { timeout: 2000 });
      return;
    }
    runLater();
    return;
  }

  window.addEventListener("load", () => {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(() => runLater(), { timeout: 2000 });
      return;
    }
    runLater();
  }, { once: true });
}

function waitForImageLoad(image) {
  return new Promise((resolve) => {
    if (image.complete && image.naturalWidth > 0) {
      resolve();
      return;
    }

    const done = () => resolve();
    image.addEventListener("load", done, { once: true });
    image.addEventListener("error", done, { once: true });
  });
}

function applyBrandingTheme(settings) {
  const themeId = settings?.themeId || "institutionnel";
  const policy = settings?.darkModePolicy || "disabled";
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const userPref = localStorage.getItem("userDarkModePreference");
  let mode;
  if (userPref === "dark" || userPref === "light") {
    mode = userPref;
  } else {
    mode = policy === "forced" ? "dark" : (policy === "allowed" && prefersDark ? "dark" : "light");
  }
  const preset = BRAND_THEME_PRESETS[themeId] || BRAND_THEME_PRESETS.institutionnel;
  const palette = preset[mode] || preset.light;
  const root = document.documentElement;

  root.dataset.brandTheme = themeId;
  root.dataset.colorMode = mode;
  root.style.setProperty("--brand", palette.brand);
  root.style.setProperty("--brand-dark", palette.brandDark);
  root.style.setProperty("--brand-soft", palette.brandSoft);
  root.style.setProperty("--accent", palette.accent);
  root.style.setProperty("--surface", palette.surface);
  root.style.setProperty("--surface-alt", palette.surfaceAlt);
  root.style.setProperty("--text", palette.text);
  root.style.setProperty("--muted", palette.muted);
  root.style.setProperty("--border", palette.border);
}

function applyBrandingContent(settings) {
  const orgName = settings?.orgName || APP_FIXED_NAME;
  const appName = APP_FIXED_NAME;
  const dpoEmail = settings?.dpoEmail || "";
  const supportEmail = settings?.supportEmail || "";
  const supportName = settings?.supportName || "";
  const supportRole = settings?.supportRole || "";
  const logoUrl = settings?.logoUrl;
  const logos = getBrandLogos();

  document.querySelectorAll("[data-brand-org]").forEach((node) => {
    node.textContent = APP_FIXED_NAME;
  });
  document.querySelectorAll("[data-brand-app-name]").forEach((node) => {
    node.textContent = appName;
  });
  document.querySelectorAll('[data-text="app.kicker"]').forEach((node) => {
    node.textContent = APP_FIXED_NAME;
  });
  document.querySelectorAll('[data-text="app.name"]').forEach((node) => {
    node.textContent = appName;
  });
  document.querySelectorAll("[data-rgpd-org-text]").forEach((node) => {
    node.textContent = `Les données à caractère personnel renseignées dans ce dossier font l'objet d'un traitement par ${orgName} afin d'assurer la gestion des attributions de ressources professionnelles, le suivi des remises et, le cas échéant, des restitutions.`;
  });
  document.querySelectorAll("[data-brand-dpo-email-link]").forEach((node) => {
    node.setAttribute("href", `mailto:${dpoEmail}`);
  });
  document.querySelectorAll("[data-brand-dpo-email-text]").forEach((node) => {
    node.textContent = dpoEmail || "Non configuré";
  });

  // Support contact
  document.querySelectorAll("[data-brand-support-email-link]").forEach((node) => {
    if (supportEmail) {
      node.setAttribute("href", `mailto:${supportEmail}`);
      node.hidden = false;
    } else {
      node.hidden = true;
    }
  });
  document.querySelectorAll("[data-brand-support-email-text]").forEach((node) => {
    node.textContent = supportEmail || "";
  });
  document.querySelectorAll("[data-brand-support-name]").forEach((node) => {
    node.textContent = supportName || "";
  });
  document.querySelectorAll("[data-brand-support-role]").forEach((node) => {
    node.textContent = supportRole || "";
  });
  // data-brand-support-credit : ne pas écraser si déjà renseigné (crédit développeur statique)
  document.querySelectorAll("[data-brand-support-credit]").forEach((node) => {
    if (node.textContent.trim() || node.innerHTML.trim()) {
      return;
    }
    if (supportName) {
      const parts = [supportName];
      if (supportRole) parts.push(supportRole);
      if (orgName) parts.push(orgName);
      node.textContent = `Développement et maintenance : ${parts.join(" — ")}.`;
    }
  });

  document.querySelectorAll("[data-app-version]").forEach((node) => {
    node.textContent = APP_BUILD_VERSION;
  });

  // Radios qualité dynamiques
  const beneficiaryTypes = settings?.beneficiaryTypes || [
    { value: "agent", label: "Agent" },
    { value: "elu", label: "Élu(e)" }
  ];
  const orgContext = settings?.orgContext || "public_collectivite";

  document.querySelectorAll("[data-dynamic-qualite]").forEach((container) => {
    const currentChecked = container.querySelector('input[name="qualite"]:checked')?.value || null;
    container.innerHTML = "";
    beneficiaryTypes.forEach((type) => {
      const label = document.createElement("label");
      label.className = "choice-chip";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "qualite";
      input.value = type.value;
      if (currentChecked === type.value) input.checked = true;
      const span = document.createElement("span");
      span.textContent = type.label;
      label.append(input, span);
      container.appendChild(label);
    });
    window.dispatchEvent(new CustomEvent("qualite:ready"));
  });

  // Visibilité du bloc mandat élu selon le contexte organisationnel
  const eluBlock = document.getElementById("eluBlock");
  if (eluBlock) {
    if (orgContext !== "public_collectivite") {
      eluBlock.dataset.eluBlockDisabled = "true";
      eluBlock.classList.add("d-none");
    } else {
      delete eluBlock.dataset.eluBlockDisabled;
    }
  }

  // Options qualité dans les filtres du tableau de bord
  document.querySelectorAll("[data-dynamic-qualite-filter]").forEach((select) => {
    const currentVal = select.value;
    const placeholder = select.querySelector('option[value=""]')?.cloneNode(true);
    select.innerHTML = "";
    if (placeholder) select.appendChild(placeholder);
    beneficiaryTypes.forEach((type) => {
      const option = document.createElement("option");
      option.value = type.value;
      option.textContent = type.label;
      select.appendChild(option);
    });
    if (currentVal) select.value = currentVal;
  });

  if (window.APP_TEXT?.app) {
    window.APP_TEXT.app.kicker = APP_FIXED_NAME;
    window.APP_TEXT.app.name = appName;
  }

  syncBrandLogos(settings);
  document.querySelectorAll("[data-brand-org-logo]").forEach((logo) => {
    if (!(logo instanceof HTMLImageElement)) {
      return;
    }
    if (logoUrl) {
      logo.hidden = false;
      logo.alt = `Logo ${orgName}`;
      if (logo.getAttribute("src") !== logoUrl) {
        logo.setAttribute("src", logoUrl);
      }
      return;
    }
    logo.hidden = true;
    logo.removeAttribute("src");
    logo.alt = "";
  });

  // Bannière setup si configuration initiale non effectuée
  ensureSetupBanner(settings?.setupCompleted !== false);

  revealBrandLogos();
}

function ensureSetupBanner(setupCompleted) {
  const DISMISSED_KEY = "setupBannerDismissed";
  const isSetupPage = window.location.pathname.endsWith("setup.html");
  const isLoginPage = window.location.pathname.endsWith("login.html") ||
                      window.location.pathname === "/login" ||
                      window.location.pathname.endsWith("signup.html");

  // Supprimer la bannière si setup est fait
  if (setupCompleted || isSetupPage || isLoginPage) {
    document.getElementById("setupBanner")?.remove();
    return;
  }

  // Ne pas afficher si déjà rejetée dans cette session
  try {
    if (sessionStorage.getItem(DISMISSED_KEY) === "1") return;
  } catch (_) {}

  if (document.getElementById("setupBanner")) return;

  const banner = document.createElement("div");
  banner.id = "setupBanner";
  banner.className = "setup-banner no-print";
  banner.setAttribute("role", "alert");

  const inner = document.createElement("div");
  inner.className = "container setup-banner__inner";

  const text = document.createElement("span");
  text.className = "setup-banner__text";
  text.innerHTML = '<strong>Configuration initiale non effectuée.</strong> Paramétrez l\'organisation, les contacts et les types de bénéficiaires avant utilisation.';

  const link = document.createElement("a");
  link.href = "/setup.html";
  link.className = "setup-banner__link btn btn-sm btn-light";
  link.textContent = "Configurer maintenant";

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "setup-banner__dismiss";
  dismiss.setAttribute("aria-label", "Fermer");
  dismiss.textContent = "×";
  dismiss.addEventListener("click", () => {
    try { sessionStorage.setItem(DISMISSED_KEY, "1"); } catch (_) {}
    banner.remove();
  });

  inner.append(text, link, dismiss);
  banner.appendChild(inner);

  // Insérer après le header ou au début du body
  const header = document.querySelector(".app-header, .setup-header");
  if (header && header.nextSibling) {
    header.parentNode.insertBefore(banner, header.nextSibling);
  } else {
    document.body.insertBefore(banner, document.body.firstChild);
  }
}

async function loadBranding(options = {}) {
  const preserveVisible = Boolean(options.preserveVisible);
  if (!preserveVisible) {
    hideBrandLogos();
  }
  try {
    const response = await fetch("/api/settings/public", {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!response.ok) {
      if (!preserveVisible) {
        revealBrandLogos();
      }
      return null;
    }
    const settings = await response.json();
    window.APP_BRANDING = settings;
    writeBrandingCache(settings);
    applyBrandingTheme(settings);
    await applyBrandingContent(settings);
    return settings;
  } catch (error) {
    console.error("branding_load_failed", error);
    if (!preserveVisible) {
      revealBrandLogos();
    }
    return null;
  }
}

async function bootBranding() {
  ensureAppFooter();
  bindHomeBrandLinks();
  scheduleCookieConsentBoot();
  const cached = readBrandingCache();
  if (cached) {
    window.APP_BRANDING = cached;
    applyBrandingTheme(cached);
    await applyBrandingContent(cached);
  }
  await loadBranding({ preserveVisible: Boolean(cached) });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    void bootBranding();
  });
} else {
  void bootBranding();
}




