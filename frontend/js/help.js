const HELP_CONTENT = {
  dashboard: {
    title: "Aide du tableau de bord",
    subtitle: "Retrouvez vos dossiers, suivez leur avancement et lancez les actions utiles sans quitter la liste.",
    hero: "Le tableau de bord centralise les dossiers d'attribution et de restitution, leur etat et les actions disponibles.",
    pill: "Tableau de bord",
    returnHref: "index.html",
    returnLabel: "Retour au tableau de bord",
    quickLinkLabel: "",
    summary: [
      "Creer un nouveau dossier quand vous demarrez une arrivee, une mobilite interne ou une mise a jour.",
      "Retrouver rapidement une fiche grace a la recherche, aux filtres et aux etats metier.",
      "Ouvrir le dossier ou la restitution pour consulter et completer les informations.",
      "Utiliser les menus d'actions pour les PDF, la signature et les operations de gestion.",
      "Selectionner plusieurs lignes pour lancer des exports groupes ou une suppression multiple."
    ],
    sections: [
      {
        title: "Reperer les priorites",
        text: "La colonne Pilotage vous aide a savoir si le dossier est dans les temps, en danger ou en retard par rapport a la date de prise de fonction."
      },
      {
        title: "Comprendre la progression",
        text: "La fraction et la barre de progression comparent les ressources deja attribuees a l'ensemble des ressources demandees sur la fiche."
      },
      {
        title: "Choisir la bonne action",
        text: "Le groupe Ouvrir sert a consulter la fiche, le groupe PDF aux exports et le groupe Signature aux liens ou courriels de signature lorsqu'ils sont encore utiles."
      }
    ]
  },
  form: {
    title: "Aide du dossier d'attribution",
    subtitle: "Completez la fiche de maniere progressive, puis finalisez-la lorsque toutes les informations utiles sont presentes.",
    hero: "La fiche d'attribution regroupe l'identite de la personne, les ressources demandees, leur attribution et la validation finale.",
    pill: "Dossier d'attribution",
    returnHref: "form.html",
    returnLabel: "Retour a la fiche",
    quickLinkLabel: "Ouvrir la fiche",
    summary: [
      "Renseigner d'abord la personne, le type de dossier et le contexte RH.",
      "Cocher uniquement les ressources reellement demandees pour les missions de la personne.",
      "Ajouter les dates d'attribution au fur et a mesure pour materialiser les actions deja realisees.",
      "Utiliser la signature sur place ou a distance selon le mode de validation choisi.",
      "Enregistrer regulierement si le dossier doit etre repris plus tard."
    ],
    sections: [
      {
        title: "Personne et contexte",
        text: "La premiere section definit le cadre du dossier : identite, service, qualite, date de prise de fonction et eventuel changement de service."
      },
      {
        title: "Ressources a attribuer",
        text: "Chaque case cochee represente une ressource attendue. Les details demandes servent ensuite a suivre precisement ce qui a ete remis."
      },
      {
        title: "Validation finale",
        text: "La derniere section regroupe la signature et l'information RGPD. Tant qu'un element obligatoire manque, le dossier reste a completer ou en attribution partielle."
      }
    ]
  },
  restitution: {
    title: "Aide de la restitution",
    subtitle: "Preparez la restitution, qualifiez l'etat du materiel et choisissez le bon mode de signature.",
    hero: "La restitution sert a tracer le retour des ressources materielles et a finaliser leur validation par signature sur place ou a distance.",
    pill: "Restitution",
    returnHref: "restitution.html",
    returnLabel: "Retour a la restitution",
    quickLinkLabel: "Ouvrir la restitution",
    summary: [
      "Renseigner le contexte general de restitution avant de passer au materiel.",
      "Choisir un etat clair pour chaque ressource materielle restituee.",
      "Ajouter un commentaire seulement lorsqu'un ecart ou une anomalie doit etre explique.",
      "Utiliser la signature sur place, impossible ou a distance selon la situation rencontree.",
      "Enregistrer la restitution une fois toutes les lignes materielles renseignees."
    ],
    sections: [
      {
        title: "Contexte de restitution",
        text: "Commencez par la date, le motif et les observations generales pour cadrer le retour du materiel."
      },
      {
        title: "Etat du materiel",
        text: "Chaque ligne de materiel doit recevoir un etat visible. Cette etape sert au suivi des ecarts et a la tracabilite du retour."
      },
      {
        title: "Signature de restitution",
        text: "Quand tout est pret, choisissez le mode de signature adapte. La restitution ne passe en terminee qu'apres la vraie validation finale."
      }
    ]
  },
  admin: {
    title: "Aide du portail d'administration",
    subtitle: "Utilisez les sous-pages d'administration pour gerer separement les comptes, les referentiels et les parametres.",
    hero: "Le portail admin sert d'entree vers les espaces specialises de gestion de l'application.",
    pill: "Administration",
    returnHref: "admin.html",
    returnLabel: "Retour au portail admin",
    quickLinkLabel: "Ouvrir le portail admin",
    summary: [
      "Acceder a la gestion des comptes et aux validations en attente.",
      "Maintenir les services et les ressources proposes dans les formulaires.",
      "Personnaliser l'application avec le logo, les couleurs et les informations institutionnelles.",
      "Consulter le journal et la corbeille depuis des pages dediees."
    ],
    sections: [
      {
        title: "Travailler par sous-page",
        text: "Chaque carte ouvre un ecran dedie afin d'eviter de concentrer trop d'actions sur une seule page."
      },
      {
        title: "Securiser les reglages",
        text: "Les modifications de personnalisation et de referentiels ont un impact global. Elles doivent etre faites avec un compte habilite."
      }
    ]
  },
  "admin-accounts": {
    title: "Aide des comptes et droits",
    subtitle: "Gerez les utilisateurs, les groupes et les validations en attente depuis une seule page.",
    hero: "Cette page permet de creer des comptes, d'ajuster leurs groupes et de suivre les demandes de validation.",
    pill: "Admin comptes",
    returnHref: "admin-comptes.html",
    returnLabel: "Retour aux comptes",
    quickLinkLabel: "Ouvrir les comptes",
    summary: [
      "Creer un utilisateur avec un mot de passe provisoire conforme a la politique affichee.",
      "Affecter les groupes qui pilotent les droits d'acces dans l'application.",
      "Modifier ou desactiver un compte existant sans le recreer.",
      "Traiter les validations en attente directement depuis la liste des utilisateurs."
    ],
    sections: [
      {
        title: "Creer ou modifier un compte",
        text: "Le formulaire du haut sert a creer un nouvel utilisateur ou a mettre a jour un compte existant lorsque vous passez en mode edition."
      },
      {
        title: "Affecter les groupes",
        text: "Les groupes determinent les autorisations. Verifiez-les avant d'enregistrer pour eviter de donner trop ou trop peu de droits."
      },
      {
        title: "Suivre les validations",
        text: "La liste des utilisateurs sert aussi a identifier les comptes en attente et a traiter rapidement les actions de gestion."
      }
    ]
  },
  "admin-services": {
    title: "Aide du catalogue des services",
    subtitle: "Maintenez la liste des services proposee dans les dossiers sans modifier le code.",
    hero: "La page services sert a garder un referentiel propre pour les listes deroulantes et le classement des dossiers.",
    pill: "Admin services",
    returnHref: "admin-services.html",
    returnLabel: "Retour aux services",
    quickLinkLabel: "Ouvrir les services",
    summary: [
      "Ajouter un nouveau service pour le rendre disponible dans les formulaires.",
      "Mettre a jour un libelle existant sans recreer toute la liste.",
      "Desactiver un service pour le masquer sans perdre son historique.",
      "Controler rapidement l'etat global du catalogue."
    ],
    sections: [
      {
        title: "Construire le catalogue",
        text: "Chaque ligne du tableau correspond a un service utilisable dans les dossiers. Le formulaire du haut permet de l'ajouter ou de le modifier."
      },
      {
        title: "Gerer l'activation",
        text: "Un service inactif n'est plus propose dans les nouvelles saisies, mais les anciennes fiches conservent leur historique."
      }
    ]
  },
  "admin-resources": {
    title: "Aide des ressources attribuables",
    subtitle: "Definissez les ressources et les champs demandes dans les dossiers d'attribution.",
    hero: "Cette page sert a piloter le referentiel des ressources materielles et immaterielles utilisees dans l'application.",
    pill: "Admin ressources",
    returnHref: "admin-ressources.html",
    returnLabel: "Retour aux ressources",
    quickLinkLabel: "Ouvrir les ressources",
    summary: [
      "Creer une ressource avec son code, son libelle, sa categorie et son service emetteur.",
      "Definir la structure des champs qui seront demandes dans les dossiers.",
      "Choisir si la ressource est restituable ou non selon son cycle de vie.",
      "Desactiver une ressource sans casser l'historique des fiches existantes."
    ],
    sections: [
      {
        title: "Decrire la ressource",
        text: "Le formulaire principal definit l'identite metier de la ressource et ses caracteristiques globales."
      },
      {
        title: "Structurer les champs",
        text: "Le bloc Structure de la ressource sert a declarer les champs a saisir dans les dossiers, ainsi que leur caractere obligatoire."
      },
      {
        title: "Maitriser l'impact metier",
        text: "Toute modification du referentiel influence les nouvelles fiches. Faites evoluer les ressources avec prudence quand elles sont deja utilisees."
      }
    ]
  },
  "admin-branding": {
    title: "Aide de la personnalisation",
    subtitle: "Ajustez l'identite visuelle et les informations institutionnelles sans modifier les fichiers de l'application.",
    hero: "La personnalisation centralise le logo, le theme, le mode sombre et l'adresse du DPO.",
    pill: "Admin personnalisation",
    returnHref: "admin-personnalisation.html",
    returnLabel: "Retour a la personnalisation",
    quickLinkLabel: "Ouvrir la personnalisation",
    summary: [
      "Definir le nom de la collectivite pour les informations institutionnelles et le footer.",
      "Choisir le logo par defaut, une URL distante ou un fichier televerse.",
      "Ajuster le theme, les couleurs et le comportement du mode sombre.",
      "Mettre a jour l'adresse e-mail du DPO reprise dans les informations RGPD."
    ],
    sections: [
      {
        title: "Preparer les changements",
        text: "La page detecte les modifications avant enregistrement. Verifiez le logo, le theme et les textes avant de lancer la sauvegarde."
      },
      {
        title: "Comprendre la sauvegarde",
        text: "La fenetre de chargement detaille les changements appliques pour vous eviter une impression de blocage pendant l'enregistrement."
      }
    ]
  },
  "admin-logs": {
    title: "Aide du journal applicatif",
    subtitle: "Analysez les traces systeme et utilisateur pour retrouver une action, un dossier ou un incident.",
    hero: "Le journal applicatif sert a la tracabilite, au diagnostic et au suivi des evenements importants de l'application.",
    pill: "Admin journal",
    returnHref: "logs.html",
    returnLabel: "Retour au journal",
    quickLinkLabel: "Ouvrir le journal",
    summary: [
      "Rechercher un acteur, un dossier, une ressource ou une action precise.",
      "Lire rapidement le perimetre, l'action et la cible pour comprendre un evenement.",
      "Utiliser le volume d'affichage pour adapter la quantite de traces chargees."
    ],
    sections: [
      {
        title: "Filtrer efficacement",
        text: "La recherche plein texte permet de retrouver rapidement une action utilisateur, un detail technique ou un identifiant metier."
      },
      {
        title: "Lire les colonnes",
        text: "Date, acteur, perimetre, action, cible et detail donnent ensemble le contexte complet d'une trace."
      }
    ]
  },
  "admin-trash": {
    title: "Aide de la corbeille",
    subtitle: "Retrouvez et restaurez les elements supprimes avant leur suppression definitive.",
    hero: "La corbeille est l'espace de recuperation des dossiers, comptes et ressources supprimes par erreur.",
    pill: "Admin corbeille",
    returnHref: "trash.html",
    returnLabel: "Retour a la corbeille",
    quickLinkLabel: "Ouvrir la corbeille",
    summary: [
      "Rechercher un element supprime par son type, son nom ou son identifiant.",
      "Controler l'auteur et la date de suppression avant de restaurer.",
      "Restaurer une ligne individuellement ou vider entierement la corbeille si necessaire."
    ],
    sections: [
      {
        title: "Restaurer avec prudence",
        text: "Avant chaque restauration, verifiez bien le type d'element et le contexte de suppression pour eviter une remise en circulation non souhaitee."
      },
      {
        title: "Suppression definitive",
        text: "Le vidage de corbeille supprime la copie de restauration en base. Apres cette action, l'element n'est plus recuperable depuis l'application."
      }
    ]
  }
};

function appendHelpSummary(listNode, items) {
  listNode.replaceChildren();
  items.forEach((item) => {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    listNode.appendChild(listItem);
  });
}

function appendHelpSections(container, sections) {
  container.replaceChildren();
  sections.forEach((section, index) => {
    const article = document.createElement("article");
    article.className = `resource-kind-block${index < sections.length - 1 ? " mb-4" : ""}`;

    const header = document.createElement("div");
    header.className = "resource-kind-block__header";

    const title = document.createElement("h4");
    title.className = "resource-kind-block__title";
    title.textContent = section.title;
    header.appendChild(title);

    const text = document.createElement("p");
    text.className = "panel-text mb-0";
    text.textContent = section.text;

    article.appendChild(header);
    article.appendChild(text);
    container.appendChild(article);
  });
}

function initHelpPage() {
  const params = new URLSearchParams(window.location.search);
  const pageKey = params.get("page") || "dashboard";
  const requestedReturn = params.get("return") || "";
  const content = HELP_CONTENT[pageKey] || HELP_CONTENT.dashboard;

  const titleNode = document.getElementById("helpPageTitle");
  const subtitleNode = document.getElementById("helpPageSubtitle");
  const heroTitleNode = document.getElementById("helpHeroTitle");
  const heroTextNode = document.getElementById("helpHeroText");
  const pillNode = document.getElementById("helpContextPill");
  const summaryListNode = document.getElementById("helpSummaryList");
  const sectionsNode = document.getElementById("helpSections");
  const backLink = document.getElementById("helpBackLink");
  const primaryBackLink = document.getElementById("helpBackPrimaryLink");
  const quickAccessLink = document.getElementById("helpQuickAccessLink");
  const returnTextNode = document.getElementById("helpReturnText");

  document.title = content.title;
  titleNode.textContent = content.title;
  subtitleNode.textContent = content.subtitle;
  heroTitleNode.textContent = content.title;
  heroTextNode.textContent = content.hero;
  pillNode.textContent = content.pill;

  appendHelpSummary(summaryListNode, content.summary);
  appendHelpSections(sectionsNode, content.sections);

  const safeReturnHref = requestedReturn && !requestedReturn.startsWith("http")
    ? requestedReturn
    : content.returnHref;

  backLink.href = safeReturnHref;
  backLink.textContent = content.returnLabel;
  primaryBackLink.href = safeReturnHref;
  primaryBackLink.textContent = content.returnLabel;
  returnTextNode.textContent = requestedReturn
    ? "Revenez exactement a la page depuis laquelle vous avez ouvert cette aide."
    : "Revenez a la page concernee pour poursuivre votre saisie ou votre consultation.";

  if (content.quickLinkLabel && safeReturnHref !== content.returnHref) {
    quickAccessLink.classList.remove("d-none");
    quickAccessLink.href = content.returnHref;
    quickAccessLink.textContent = content.quickLinkLabel;
  } else {
    quickAccessLink.classList.add("d-none");
  }
}

document.addEventListener("DOMContentLoaded", initHelpPage);

