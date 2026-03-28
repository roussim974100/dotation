// Branding public partage par toutes les pages frontend.
// Le logo reste masque jusqu'a ce que le bon visuel soit pret,
// ce qui evite le flash du fallback local avant le vrai logo configure.
const BRANDING_CACHE_KEY = "appBrandingPublicCacheV1";
const APP_BUILD_VERSION = "2.9.0";
const CLIENT_CONTEXT_COOKIE_NAME = "dotation_client_context_v1";
const COOKIE_CONSENT_COOKIE_NAME = "dotation_cookie_consent_v1";
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

function getBrandLogos() {
  return Array.from(document.querySelectorAll(".app-logo[data-brand-logo]"));
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
  footer.innerHTML = `
    <div class="container app-footer__inner">
      <div class="app-footer__top">
        <div class="app-footer__identity">
          <strong class="app-footer__app" data-brand-app-name>Parcours agents et elu(e)s</strong>
          <span class="app-footer__version">Version ${APP_BUILD_VERSION}</span>
        </div>
        <div class="app-footer__contact">
          <span>Contact technique :</span>
          <a href="mailto:computing.bs@gmail.com">computing.bs@gmail.com</a>
        </div>
      </div>
      <div class="app-footer__bottom">
        <span>&copy; <span data-app-year>${new Date().getFullYear()}</span> <span data-brand-org>Ville de Publier</span>. Application developpee en vibecoding par Samir BASSIM, DSI de la commune de Publier.</span>
      </div>
    </div>
  `;
  targetBody.appendChild(footer);
}

function readCookie(name) {
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
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

function getCookieConsentState() {
  return readCookie(COOKIE_CONSENT_COOKIE_NAME);
}

function hasAcceptedClientContextCookies() {
  return getCookieConsentState() === "accepted";
}

function ensureCookieConsentBanner() {
  if (document.querySelector("[data-cookie-consent]")) {
    return;
  }

  const state = getCookieConsentState();
  if (state === "accepted" || state === "rejected") {
    return;
  }

  const banner = document.createElement("aside");
  banner.className = "cookie-consent no-print";
  banner.setAttribute("data-cookie-consent", "true");
  banner.innerHTML = `
    <div class="cookie-consent__content">
      <div class="cookie-consent__copy">
        <strong class="cookie-consent__title">Cookies techniques</strong>
        <p class="cookie-consent__text">Nous utilisons les cookies indispensables à la session et, avec votre accord, un cookie technique pour enrichir le journal avec le poste client, l'IP LAN si disponible et l'IP WAN vue par le serveur.</p>
        <button class="btn btn-link btn-sm cookie-consent__details-toggle" type="button" data-cookie-details-toggle>Détails</button>
        <div class="cookie-consent__details d-none" data-cookie-details>
          <p class="cookie-consent__details-text"><strong>Indispensable :</strong> cookie de session pour l'authentification et la sécurité.</p>
          <p class="cookie-consent__details-text"><strong>Optionnel :</strong> cookie de contexte client pour mémoriser le type de poste, le navigateur, l'IP LAN si le navigateur l'expose, et l'IP WAN détectée côté serveur afin d'améliorer le journal d'activité.</p>
        </div>
      </div>
      <div class="cookie-consent__actions">
        <button class="btn btn-outline-secondary btn-sm" type="button" data-cookie-reject>Refuser</button>
        <button class="btn btn-primary btn-sm" type="button" data-cookie-accept>Accepter</button>
      </div>
    </div>
  `;

  document.body.appendChild(banner);

  banner.querySelector("[data-cookie-details-toggle]")?.addEventListener("click", () => {
    banner.querySelector("[data-cookie-details]")?.classList.toggle("d-none");
  });

  banner.querySelector("[data-cookie-reject]")?.addEventListener("click", () => {
    writeCookie(COOKIE_CONSENT_COOKIE_NAME, "rejected", 60 * 60 * 24 * 180);
    removeCookie(CLIENT_CONTEXT_COOKIE_NAME);
    banner.remove();
  });

  banner.querySelector("[data-cookie-accept]")?.addEventListener("click", async () => {
    writeCookie(COOKIE_CONSENT_COOKIE_NAME, "accepted", 60 * 60 * 24 * 180);
    await bootClientContext();
    banner.remove();
  });
}

function revealBrandLogos() {
  // Le logo courant est deja charge directement par le HTML.
}

function hideBrandLogos() {
  // Le masquage n'est plus necessaire maintenant que le src HTML
  // pointe deja vers le logo courant de l'application.
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
  if (!hasAcceptedClientContextCookies()) {
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
  const mode = policy === "forced" ? "dark" : (policy === "allowed" && prefersDark ? "dark" : "light");
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

async function applyBrandingContent(settings) {
  const orgName = settings?.orgName || "Collectivite";
  const appName = settings?.appName || "Parcours agents et elu(e)s";
  const dpoEmail = settings?.dpoEmail || "dpo@ville-publier.fr";
  const logoUrl = settings?.logoUrl;
  const logos = getBrandLogos();

  if (logoUrl && logos.length) {
    const loads = logos.map((logo) => {
      logo.src = logoUrl;
      logo.alt = `Logo ${orgName}`;
      return waitForImageLoad(logo);
    });
    await Promise.all(loads);
  } else {
    logos.forEach((logo) => {
      logo.alt = `Logo ${orgName}`;
    });
  }

  document.querySelectorAll("[data-brand-org]").forEach((node) => {
    node.textContent = orgName;
  });
  document.querySelectorAll("[data-brand-app-name]").forEach((node) => {
    node.textContent = appName;
  });
  document.querySelectorAll('[data-text="app.kicker"]').forEach((node) => {
    node.textContent = orgName;
  });
  document.querySelectorAll('[data-text="app.name"]').forEach((node) => {
    node.textContent = appName;
  });
  document.querySelectorAll("[data-rgpd-org-text]").forEach((node) => {
    node.textContent = `Les donnees a caractere personnel renseignees dans ce dossier font l'objet d'un traitement par ${orgName} afin d'assurer la gestion des attributions de ressources professionnelles, le suivi des remises et, le cas echeant, des restitutions.`;
  });
  document.querySelectorAll("[data-brand-dpo-email-link]").forEach((node) => {
    node.setAttribute("href", `mailto:${dpoEmail}`);
  });
  document.querySelectorAll("[data-brand-dpo-email-text]").forEach((node) => {
    node.textContent = dpoEmail;
  });

  if (window.APP_TEXT?.app) {
    window.APP_TEXT.app.kicker = orgName;
    window.APP_TEXT.app.name = appName;
  }

  revealBrandLogos();
}

async function loadBranding(options = {}) {
  const preserveVisible = Boolean(options.preserveVisible);
  if (!preserveVisible) {
    hideBrandLogos();
  }
  try {
    const response = await fetch("/api/settings/public", { credentials: "same-origin" });
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
  ensureCookieConsentBanner();
  bindHomeBrandLinks();
  if (hasAcceptedClientContextCookies()) {
    void bootClientContext();
  }
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
