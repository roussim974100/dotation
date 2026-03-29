const HELP_CONTENT = {
  dashboard: {
    title: "Aide du tableau de bord",
    subtitle: "Retrouvez vos dossiers, suivez leur avancement et lancez les actions utiles sans quitter la liste.",
    hero: "Le tableau de bord centralise les dossiers d'attribution et de restitution, leur état et les actions disponibles.",
    pill: "Tableau de bord",
    returnHref: "index.html",
    returnLabel: "Retour au tableau de bord",
    quickLinkLabel: "",
    summary: [
      "Créer un nouveau dossier quand vous démarrez une arrivée, une mobilité interne ou une mise à jour.",
      "Retrouver rapidement une fiche grâce à la recherche, aux filtres et aux états métier.",
      "Ouvrir le dossier ou la restitution pour consulter et compléter les informations.",
      "Utiliser les menus d'actions pour les PDF, la signature et les opérations de gestion.",
      "Sélectionner plusieurs lignes pour lancer des exports groupés ou une suppression multiple."
    ],
    sections: [
      {
        title: "Repérer les priorités",
        text: "La colonne Pilotage vous aide à savoir si le dossier est dans les temps, en danger ou en retard par rapport à la date de prise de fonction."
      },
      {
        title: "Comprendre la progression",
        text: "La fraction et la barre de progression comparent les ressources déjà attribuées à l'ensemble des ressources demandées sur la fiche."
      },
      {
        title: "Choisir la bonne action",
        text: "Le groupe Ouvrir sert à consulter la fiche, le groupe PDF aux exports et le groupe Signature aux liens ou courriels de signature lorsqu'ils sont encore utiles."
      }
    ]
  },
  form: {
    title: "Aide du dossier d'attribution",
    subtitle: "Complétez la fiche de manière progressive, puis finalisez-la lorsque toutes les informations utiles sont présentes.",
    hero: "La fiche d'attribution regroupe l'identité de la personne, les ressources demandées, leur attribution et la validation finale.",
    pill: "Dossier d'attribution",
    returnHref: "form.html",
    returnLabel: "Retour à la fiche",
    quickLinkLabel: "Ouvrir la fiche",
    summary: [
      "Renseigner d'abord la personne, le type de dossier et le contexte RH.",
      "Cocher uniquement les ressources réellement demandées pour les missions de la personne.",
      "Ajouter les dates d'attribution au fur et à mesure pour matérialiser les actions déjà réalisées.",
      "Utiliser la signature sur place ou à distance selon le mode de validation choisi.",
      "Enregistrer régulièrement si le dossier doit être repris plus tard."
    ],
    sections: [
      {
        title: "Personne et contexte",
        text: "La première section définit le cadre du dossier : identité, service, qualité, date de prise de fonction et éventuel changement de service."
      },
      {
        title: "Ressources à attribuer",
        text: "Chaque case cochée représente une ressource attendue. Les détails demandés servent ensuite à suivre précisément ce qui a été remis."
      },
      {
        title: "Validation finale",
        text: "La dernière section regroupe la signature et l'information RGPD. Tant qu'un élément obligatoire manque, le dossier reste à compléter ou en attribution partielle."
      }
    ]
  },
  restitution: {
    title: "Aide de la restitution",
    subtitle: "Préparez la restitution, qualifiez l'état du matériel et choisissez le bon mode de signature.",
    hero: "La restitution sert à tracer le retour des ressources matérielles et à finaliser leur validation par signature sur place ou à distance.",
    pill: "Restitution",
    returnHref: "restitution.html",
    returnLabel: "Retour à la restitution",
    quickLinkLabel: "Ouvrir la restitution",
    summary: [
      "Renseigner le contexte général de restitution avant de passer au matériel.",
      "Choisir un état clair pour chaque ressource matérielle restituée.",
      "Ajouter un commentaire seulement lorsqu'un écart ou une anomalie doit être expliqué.",
      "Utiliser la signature sur place, impossible ou à distance selon la situation rencontrée.",
      "Enregistrer la restitution une fois toutes les lignes matérielles renseignées."
    ],
    sections: [
      {
        title: "Contexte de restitution",
        text: "Commencez par la date, le motif et les observations générales pour cadrer le retour du matériel."
      },
      {
        title: "État du matériel",
        text: "Chaque ligne de matériel doit recevoir un état visible. Cette étape sert au suivi des écarts et à la traçabilité du retour."
      },
      {
        title: "Signature de restitution",
        text: "Quand tout est prêt, choisissez le mode de signature adapté. La restitution ne passe en terminée qu'après la vraie validation finale."
      }
    ]
  },
  admin: {
    title: "Aide du portail d'administration",
    subtitle: "Utilisez les sous-pages d'administration pour gérer séparément les comptes, les référentiels et les paramètres.",
    hero: "Le portail admin sert d'entrée vers les espaces spécialisés de gestion de l'application.",
    pill: "Administration",
    returnHref: "admin.html",
    returnLabel: "Retour au portail admin",
    quickLinkLabel: "Ouvrir le portail admin",
    summary: [
      "Accéder à la gestion des comptes et aux validations en attente.",
      "Maintenir les services et les ressources proposés dans les formulaires.",
      "Personnaliser l'application avec le logo, les couleurs et les informations institutionnelles.",
      "Consulter le journal et la corbeille depuis des pages dédiées."
    ],
    sections: [
      {
        title: "Travailler par sous-page",
        text: "Chaque carte ouvre un écran dédié afin d'éviter de concentrer trop d'actions sur une seule page."
      },
      {
        title: "Sécuriser les réglages",
        text: "Les modifications de personnalisation et de référentiels ont un impact global. Elles doivent être faites avec un compte habilité."
      }
    ]
  },
  "admin-accounts": {
    title: "Aide des comptes et droits",
    subtitle: "Gérez les utilisateurs, les groupes et les validations en attente depuis une seule page.",
    hero: "Cette page permet de créer des comptes, d'ajuster leurs groupes et de suivre les demandes de validation.",
    pill: "Admin comptes",
    returnHref: "admin-comptes.html",
    returnLabel: "Retour aux comptes",
    quickLinkLabel: "Ouvrir les comptes",
    summary: [
      "Créer un utilisateur avec un mot de passe provisoire conforme à la politique affichée.",
      "Affecter les groupes qui pilotent les droits d'accès dans l'application.",
      "Modifier ou désactiver un compte existant sans le recréer.",
      "Traiter les validations en attente directement depuis la liste des utilisateurs."
    ],
    sections: [
      {
        title: "Créer ou modifier un compte",
        text: "Le formulaire du haut sert à créer un nouvel utilisateur ou à mettre à jour un compte existant lorsque vous passez en mode édition."
      },
      {
        title: "Affecter les groupes",
        text: "Les groupes déterminent les autorisations. Vérifiez-les avant d'enregistrer pour éviter de donner trop ou trop peu de droits."
      },
      {
        title: "Suivre les validations",
        text: "La liste des utilisateurs sert aussi à identifier les comptes en attente et à traiter rapidement les actions de gestion."
      }
    ]
  },
  "admin-services": {
    title: "Aide du catalogue des services",
    subtitle: "Maintenez la liste des services proposée dans les dossiers sans modifier le code.",
    hero: "La page services sert à garder un référentiel propre pour les listes déroulantes et le classement des dossiers.",
    pill: "Admin services",
    returnHref: "admin-services.html",
    returnLabel: "Retour aux services",
    quickLinkLabel: "Ouvrir les services",
    summary: [
      "Ajouter un nouveau service pour le rendre disponible dans les formulaires.",
      "Mettre à jour un libellé existant sans recréer toute la liste.",
      "Désactiver un service pour le masquer sans perdre son historique.",
      "Contrôler rapidement l'état global du catalogue."
    ],
    sections: [
      {
        title: "Construire le catalogue",
        text: "Chaque ligne du tableau correspond à un service utilisable dans les dossiers. Le formulaire du haut permet de l'ajouter ou de le modifier."
      },
      {
        title: "Gérer l'activation",
        text: "Un service inactif n'est plus proposé dans les nouvelles saisies, mais les anciennes fiches conservent leur historique."
      }
    ]
  },
  "admin-resources": {
    title: "Aide des ressources attribuables",
    subtitle: "Définissez les ressources et les champs demandés dans les dossiers d'attribution.",
    hero: "Cette page sert à piloter le référentiel des ressources matérielles et immatérielles utilisées dans l'application.",
    pill: "Admin ressources",
    returnHref: "admin-ressources.html",
    returnLabel: "Retour aux ressources",
    quickLinkLabel: "Ouvrir les ressources",
    summary: [
      "Créer une ressource avec son libellé, sa catégorie et son service émetteur choisi dans la liste des services existants.",
      "Le code technique est généré automatiquement à partir du libellé et ne demande pas de saisie manuelle.",
      "Ajouter uniquement les champs utiles dans la ressource, au moment voulu, avec le bouton Ajouter un champ.",
      "Choisir les informations de suivi à afficher dans le dossier : date d'attribution, état à la remise et observation de remise.",
      "Choisir si la ressource est restituable ou non selon son cycle de vie.",
      "Désactiver une ressource sans casser l'historique des fiches existantes."
    ],
    sections: [
      {
        title: "Décrire la ressource",
        text: "Le formulaire principal définit le libellé visible, la catégorie, le service émetteur, une description et un placement simple dans la liste. Le code interne est fabriqué automatiquement pour garantir une dénomination propre et homogène."
      },
      {
        title: "Structurer les champs",
        text: "Le bloc Structure de la ressource sert à déclarer les champs à saisir dans les dossiers. Aucune ligne n'apparaît tant que vous n'avez pas cliqué sur Ajouter un champ."
      },
      {
        title: "Définir le suivi à l'attribution",
        text: "Le bloc Suivi à l'attribution permet d'afficher ou non la date d'attribution, l'état à la remise et l'observation de remise. Pour une ressource immatérielle, l'état à la remise est automatiquement désactivé."
      },
      {
        title: "Maîtriser l'impact métier",
        text: "Toute modification du référentiel influence les nouvelles fiches. Faites évoluer les ressources avec prudence quand elles sont déjà utilisées."
      }
    ]
  },
  "admin-resources-order": {
    title: "Aide de l'ordre des ressources",
    subtitle: "Réorganisez les ressources avec un glisser-déposer simple et visuel.",
    hero: "Cette page sert à régler l'ordre réel d'apparition des ressources dans les dossiers, sans manipuler de nombres techniques.",
    pill: "Admin ordre",
    returnHref: "admin-ressources-ordre.html",
    returnLabel: "Retour à l'ordre des ressources",
    quickLinkLabel: "Ouvrir l'ordre des ressources",
    summary: [
      "Glisser une ressource vers le haut ou vers le bas pour modifier son ordre d'apparition.",
      "Utiliser cette page quand vous voulez un réglage fin, plus précis que le choix simple du formulaire.",
      "Enregistrer l'ordre une fois la réorganisation terminée pour l'appliquer à tous les dossiers.",
      "Conserver aussi les ressources inactives dans la liste pour garder une organisation complète du référentiel."
    ],
    sections: [
      {
        title: "Comprendre la liste",
        text: "La ressource affichée en premier sera proposée plus haut dans les dossiers. La liste suit donc directement l'ordre de lecture de haut en bas."
      },
      {
        title: "Réorganiser facilement",
        text: "Utilisez la poignée de déplacement et faites glisser la ressource à l'endroit voulu. Un message vous rappelle ensuite d'enregistrer l'ordre."
      },
      {
        title: "Quand utiliser cette page",
        text: "Le formulaire de ressource suffit pour un placement simple. Cette page dédiée est préférable dès que vous voulez un ordre précis ou réorganiser plusieurs ressources d'un coup."
      }
    ]
  },
  "admin-resources-create": {
    title: "Aide à l'ajout d'une ressource",
    subtitle: "Créez une ressource de manière simple, claire et directement exploitable dans les dossiers.",
    hero: "Cette aide vous accompagne pas à pas pour ajouter une ressource, choisir son service, ses champs et son suivi à l'attribution.",
    pill: "Ajout ressource",
    returnHref: "admin-ressources.html",
    returnLabel: "Retour à l'ajout de ressource",
    quickLinkLabel: "Ouvrir l'ajout de ressource",
    summary: [
      "Commencer par le libellé visible de la ressource, puis choisir sa catégorie et son service émetteur.",
      "Ajouter uniquement les champs vraiment utiles avec le bouton Ajouter un champ.",
      "Choisir si la ressource est restituable selon son cycle de vie réel.",
      "Activer seulement les informations de suivi nécessaires : date, état et observation de remise.",
      "Utiliser la page Ordre des ressources si vous voulez ensuite régler finement sa position dans les dossiers."
    ],
    sections: [
      {
        title: "Bien nommer la ressource",
        text: "Le libellé est le nom vu par les utilisateurs dans les dossiers. Il doit être court, compréhensible et proche du vocabulaire métier utilisé au quotidien."
      },
      {
        title: "Choisir la bonne catégorie",
        text: "Une ressource matérielle peut être restituée physiquement. Une ressource immatérielle correspond plutôt à un accès, un droit ou un service."
      },
      {
        title: "Ajouter les bons champs",
        text: "Ajoutez un champ seulement si l'information doit vraiment être saisie dans le dossier. Gardez la structure légère pour éviter une fiche trop lourde."
      },
      {
        title: "Régler le suivi à l'attribution",
        text: "La date d'attribution sert à matérialiser l'action réalisée. L'état à la remise et l'observation sont surtout utiles pour le matériel."
      },
      {
        title: "Penser à la restitution",
        text: "Activez le caractère restituable uniquement si la ressource doit revenir à la collectivité ou à l'organisation à la fin du parcours."
      }
    ]
  },
  "admin-branding": {
    title: "Aide de la personnalisation",
    subtitle: "Ajustez l'identité visuelle et les informations institutionnelles sans modifier les fichiers de l'application.",
    hero: "La personnalisation centralise le logo, le thème, le mode sombre et l'adresse du DPO.",
    pill: "Admin personnalisation",
    returnHref: "admin-personnalisation.html",
    returnLabel: "Retour à la personnalisation",
    quickLinkLabel: "Ouvrir la personnalisation",
    summary: [
      "Définir le nom de la collectivité pour les informations institutionnelles et le footer.",
      "Choisir le logo par défaut, une URL distante ou un fichier téléversé.",
      "Ajuster le thème, les couleurs et le comportement du mode sombre.",
      "Mettre à jour l'adresse e-mail du DPO reprise dans les informations RGPD."
    ],
    sections: [
      {
        title: "Préparer les changements",
        text: "La page détecte les modifications avant enregistrement. Vérifiez le logo, le thème et les textes avant de lancer la sauvegarde."
      },
      {
        title: "Comprendre la sauvegarde",
        text: "La fenêtre de chargement détaille les changements appliqués pour vous éviter une impression de blocage pendant l'enregistrement."
      }
    ]
  },
  "admin-logs": {
    title: "Aide du journal applicatif",
    subtitle: "Analysez les traces système et utilisateur pour retrouver une action, un dossier ou un incident.",
    hero: "Le journal applicatif sert à la traçabilité, au diagnostic et au suivi des événements importants de l'application.",
    pill: "Admin journal",
    returnHref: "logs.html",
    returnLabel: "Retour au journal",
    quickLinkLabel: "Ouvrir le journal",
    summary: [
      "Rechercher un acteur, un dossier, une ressource ou une action précise.",
      "Lire rapidement le périmètre, l'action et la cible pour comprendre un événement.",
      "Utiliser le volume d'affichage pour adapter la quantité de traces chargées."
    ],
    sections: [
      {
        title: "Filtrer efficacement",
        text: "La recherche plein texte permet de retrouver rapidement une action utilisateur, un détail technique ou un identifiant métier."
      },
      {
        title: "Lire les colonnes",
        text: "Date, acteur, périmètre, action, cible et détail donnent ensemble le contexte complet d'une trace."
      }
    ]
  },
  "admin-trash": {
    title: "Aide de la corbeille",
    subtitle: "Retrouvez et restaurez les éléments supprimés avant leur suppression définitive.",
    hero: "La corbeille est l'espace de récupération des dossiers, comptes et ressources supprimés par erreur.",
    pill: "Admin corbeille",
    returnHref: "trash.html",
    returnLabel: "Retour à la corbeille",
    quickLinkLabel: "Ouvrir la corbeille",
    summary: [
      "Rechercher un élément supprimé par son type, son nom ou son identifiant.",
      "Contrôler l'auteur et la date de suppression avant de restaurer.",
      "Restaurer une ligne individuellement ou vider entièrement la corbeille si nécessaire."
    ],
    sections: [
      {
        title: "Restaurer avec prudence",
        text: "Avant chaque restauration, vérifiez bien le type d'élément et le contexte de suppression pour éviter une remise en circulation non souhaitée."
      },
      {
        title: "Suppression définitive",
        text: "Le vidage de corbeille supprime la copie de restauration en base. Après cette action, l'élément n'est plus récupérable depuis l'application."
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
    ? "Revenez exactement à la page depuis laquelle vous avez ouvert cette aide."
    : "Revenez à la page concernée pour poursuivre votre saisie ou votre consultation.";

  if (content.quickLinkLabel && safeReturnHref !== content.returnHref) {
    quickAccessLink.classList.remove("d-none");
    quickAccessLink.href = content.returnHref;
    quickAccessLink.textContent = content.quickLinkLabel;
  } else {
    quickAccessLink.classList.add("d-none");
  }
}

document.addEventListener("DOMContentLoaded", initHelpPage);
