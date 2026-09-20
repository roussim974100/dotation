// Navigation d'administration : UNE définition pour toutes les pages (menu latéral groupé, fil d'Ariane, page courante).
// Elle remplace le menu latéral copié à la main dans chaque page et l'ajoute aux pages qui n'en avaient pas (journal, corbeille).
// Les liens d'ancre propres à une page (« Nouveau compte », « Groupes »…) sont conservés sous « Sur cette page ».

(function () {
  "use strict";

  const GROUPS = [
    { title: null, items: [{ href: "admin.html", label: "Accueil admin", hint: "Vue d'ensemble" }] },
    { title: "Utilisateurs", items: [{ href: "admin-comptes.html", label: "Comptes", hint: "Utilisateurs et groupes" }] },
    { title: "Organisation", items: [
      { href: "admin-services.html", label: "Services", hint: "Catalogue du formulaire" },
      { href: "admin-ressources.html", label: "Ressources", hint: "Référentiel" },
      { href: "admin-ressources-ordre.html", label: "Ordre des ressources", hint: "Glisser-déposer" },
      { href: "admin-personnalisation.html?wizard=1", label: "Assistant d'organisation", hint: "Configuration guidée", page: "wizard" }
    ] },
    { title: "Apparence", items: [{ href: "admin-personnalisation.html", label: "Personnalisation", hint: "Logo et thèmes" }] },
    { title: "Exploitation", items: [
      { href: "admin-db.html", label: "Base de données", hint: "Sauvegarde et restauration", perm: "db" },
      { href: "parc.html", label: "Parc matériel", hint: "Historique des objets", perm: "parc" },
      { href: "logs.html", label: "Journal", hint: "Traçabilité" },
      { href: "trash.html", label: "Corbeille", hint: "Éléments supprimés" }
    ] }
  ];

  const ALL = GROUPS.flatMap((group) => group.items);
  const file = (href) => href.split("?")[0].split("#")[0];
  const current = window.location.pathname.split("/").pop() || "index.html";

  function esc(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function pageLabel() {
    const entry = ALL.find((item) => file(item.href) === current && item.page !== "wizard");
    return entry ? entry.label : "";
  }

  function pageLinks(nav) {
    return [...nav.querySelectorAll('a[href^="#"]')].map((a) => ({
      href: a.getAttribute("href"), label: (a.querySelector("span") || a).textContent.trim(), hint: (a.querySelector("small") || {}).textContent || ""
    }));
  }

  function linkHtml(item) {
    const active = file(item.href) === current && item.page !== "wizard" && !window.location.search.includes("wizard=1");
    const hidden = item.perm ? " hidden" : "";
    return `<a class="admin-nav__link${active ? " is-active" : ""}" href="${esc(item.href)}"${active ? ' aria-current="page"' : ""}${item.perm ? ` data-perm="${item.perm}"` : ""}${hidden}>` +
      `<span>${esc(item.label)}</span><small>${esc(item.hint)}</small></a>`;
  }

  function navHtml(local) {
    const groups = GROUPS.map((group) => `${group.title ? `<p class="admin-nav__group">${esc(group.title)}</p>` : ""}${group.items.map(linkHtml).join("")}`).join("");
    const here = local.length ? `<p class="admin-nav__group">Sur cette page</p>${local.map((item) => `<a class="admin-nav__link admin-nav__link--local" href="${esc(item.href)}"><span>${esc(item.label)}</span><small>${esc(item.hint)}</small></a>`).join("")}` : "";
    return groups + here;
  }

  function ensureLayout(main) {
    if (main.querySelector(".admin-layout")) return main.querySelector(".admin-nav");
    const layout = document.createElement("div");
    layout.className = "admin-layout";
    const aside = document.createElement("aside");
    aside.className = "content-card admin-sidebar";
    aside.innerHTML = '<p class="panel-eyebrow">Navigation</p><nav class="admin-nav" aria-label="Navigation administration"></nav>';
    const content = document.createElement("div");
    content.className = "admin-content";
    while (main.firstChild) content.appendChild(main.firstChild);
    layout.append(aside, content);
    main.appendChild(layout);
    return aside.querySelector(".admin-nav");
  }

  function breadcrumb(host) {
    const label = pageLabel();
    const trail = `<li class="breadcrumb-item"><a href="index.html">Accueil</a></li>` +
      (current === "admin.html" ? '<li class="breadcrumb-item active" aria-current="page">Administration</li>'
        : `<li class="breadcrumb-item"><a href="admin.html">Administration</a></li><li class="breadcrumb-item active" aria-current="page">${esc(label)}</li>`);
    const nav = document.createElement("nav");
    nav.className = "admin-breadcrumb";
    nav.setAttribute("aria-label", "Fil d'Ariane");
    nav.innerHTML = `<ol class="breadcrumb mb-3">${trail}</ol>`;
    host.insertBefore(nav, host.firstChild);
  }

  async function revealByPermission(nav) {
    try {
      const response = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return;
      const user = await response.json();
      const permissions = user.permissions || [];
      const all = permissions.includes("*");
      const allowed = { db: all || permissions.includes("db.manage") || Boolean(user.db_manage), parc: all || permissions.includes("forms.read_list") };
      nav.querySelectorAll("[data-perm]").forEach((link) => { link.hidden = !allowed[link.dataset.perm]; });
    } catch (_) {
      /* les entrées réservées restent masquées */
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const main = document.getElementById("main");
    if (!main || !ALL.some((item) => file(item.href) === current)) return;
    if (current === "parc.html") return;  // page métier : elle garde sa mise en page pleine largeur (lien dans le menu du compte)
    if (current === "admin.html") {  // le portail est lui-même le menu (cartes) : fil d'Ariane seulement
      if (!document.querySelector(".admin-breadcrumb")) breadcrumb(main);
      return;
    }
    const existing = main.querySelector(".admin-nav");
    const local = existing ? pageLinks(existing) : [];
    const nav = ensureLayout(main);
    nav.dataset.managed = "true";
    nav.innerHTML = navHtml(local);
    const content = main.querySelector(".admin-content") || main;
    if (!document.querySelector(".admin-breadcrumb")) breadcrumb(content);
    revealByPermission(nav);
  });
})();
