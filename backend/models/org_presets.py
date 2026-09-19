"""Catalogue de l'assistant d'organisation : contextes, packs de ressources proposes et modeles de ressource.

Tout est une SUGGESTION : l'administrateur peut tout modifier, decocher ou remplacer (structure quelconque, y compris hors
France : les libelles sont libres et « other » permet de tout regler soi-meme). Les identifiants restent en ASCII.
Ce catalogue est servi tel quel au navigateur (GET /api/admin/org-presets) : il n'existe qu'a un seul endroit.
"""

# Contexte -> suggestions. `resources` liste des CODES de ressources natives (voir DEFAULT_RESOURCE_REFERENCES) recommandees.
ALL_BUILTIN = ["ordinateur", "ecran", "telephone", "tablette", "vpn", "email", "badge", "cles", "veste", "chaussuresSecurite",
               "zoneAlarme", "vehicule", "plaquePorte", "cartesVisite", "autre"]

ORG_CONTEXTS = {
    "public_collectivite": {
        "label": "Collectivité territoriale",
        "description": "Mairie, intercommunalité, département, région…",
        "beneficiary_types": "agent:Agent,elu:Élu(e)",
        "resources": ALL_BUILTIN,
        "settings": {"parc_retention_years": "5", "timing_warning_days": "3"},
    },
    "public_administration": {
        "label": "Administration publique",
        "description": "Ministère, préfecture, établissement public…",
        "beneficiary_types": "fonctionnaire:Fonctionnaire,contractuel:Contractuel(le),prestataire:Prestataire",
        "resources": ["ordinateur", "ecran", "telephone", "tablette", "vpn", "email", "badge", "cles", "plaquePorte", "cartesVisite", "autre"],
        "settings": {"parc_retention_years": "5", "timing_warning_days": "3"},
    },
    "private_company": {
        "label": "Entreprise privée",
        "description": "Société, filiale, indépendant avec collaborateurs…",
        "beneficiary_types": "salarie:Salarié(e),prestataire:Prestataire",
        "resources": ["ordinateur", "ecran", "telephone", "tablette", "vpn", "email", "badge", "cles", "vehicule", "cartesVisite", "autre"],
        "settings": {"parc_retention_years": "5", "timing_warning_days": "3"},
    },
    "association": {
        "label": "Association",
        "description": "Association, fondation, ONG (salariés et bénévoles)…",
        "beneficiary_types": "salarie:Salarié(e),benevole:Bénévole",
        "resources": ["ordinateur", "telephone", "email", "badge", "cles", "veste", "autre"],
        "settings": {"parc_retention_years": "3", "timing_warning_days": "3"},
    },
    "other": {
        "label": "Autre / sur mesure",
        "description": "Toute autre structure, en France ou à l'étranger : je règle tout moi-même.",
        "beneficiary_types": "member:Membre",
        "resources": ["ordinateur", "telephone", "email", "badge", "cles", "autre"],
        "settings": {"parc_retention_years": "5", "timing_warning_days": "3"},
    },
}

# Modeles pour CREER une ressource absente du catalogue. `builtin_codes` : ressources natives equivalentes (si l'une
# existe deja, on ne cree rien : pas de doublon semantique). Champ : label, type, required, identifier, suggest.
RESOURCE_TEMPLATES = {
    "vetement": {"mode": "none", "label": "Vêtement / équipement", "description": "Veste, chaussures, gilet…", "category": "materiel",
                 "requires_return": True, "builtin_codes": ["veste"], "fields": [{"label": "Taille"}]},
    "stock_vetement": {"mode": "quantity", "label": "Vêtement en stock (par taille)", "category": "materiel", "requires_return": True,
                       "description": "Suit le stock de chaque taille : remises, retours, réceptions.", "builtin_codes": [],
                       "fields": [{"label": "Quantité", "type": "number", "required": True}, {"label": "Taille"}]},
    "stock_consommable": {"mode": "quantity", "label": "Consommable en stock", "category": "materiel", "requires_return": False,
                          "description": "Fournitures : un simple nombre d'exemplaires.", "builtin_codes": [],
                          "fields": [{"label": "Quantité", "type": "number", "required": True}]},
    "acces": {"mode": "access", "label": "Accès numérique", "description": "Compte, droit ou licence.", "category": "immateriel",
              "requires_return": False, "builtin_codes": ["vpn", "email"], "fields": [{"label": "Identifiant du compte", "required": True}]},
    "vehicule": {"mode": "unit", "label": "Véhicule", "description": "Véhicule de service ou de fonction.", "category": "materiel",
                 "requires_return": True, "builtin_codes": ["vehicule"],
                 "fields": [{"label": "Marque", "required": True, "suggest": True}, {"label": "Modèle", "required": True, "suggest": True},
                            {"label": "Immatriculation", "required": True, "identifier": True}]},
    "equipement": {"mode": "unit", "label": "Équipement suivi par objet", "description": "Tout objet identifié par un numéro.", "category": "materiel",
                   "requires_return": True, "builtin_codes": [],
                   "fields": [{"label": "Désignation", "required": True}, {"label": "N° d'identification", "required": True, "identifier": True}]},
}

# Reglages que l'assistant a le droit de modifier (liste blanche ; tout le reste est ignore).
WIZARD_SETTING_KEYS = ("org_name", "org_context", "beneficiary_types", "dpo_email", "email_domains", "support_name", "support_email",
                       "support_role", "restitution_phase1_unlock_days", "timing_warning_days", "parc_retention_years")


def catalog_payload():
    """Catalogue destine au navigateur (les listes de codes sont deja des donnees pures)."""
    return {
        "context_order": list(ORG_CONTEXTS),  # jsonify trie les cles : l'ordre d'affichage est donne a part
        "contexts": {key: {**value} for key, value in ORG_CONTEXTS.items()},
        "template_order": list(RESOURCE_TEMPLATES),
        "templates": {key: {"label": v["label"], "description": v["description"], "mode": v["mode"], "category": v["category"]}
                      for key, v in RESOURCE_TEMPLATES.items()},
        "tracking_modes": ["unit", "none", "quantity", "access"],
    }
