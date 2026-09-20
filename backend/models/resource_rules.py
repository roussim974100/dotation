"""Regles de coherence d'une ressource du catalogue, pour que l'historique du parc soit exploitable.

Un « mode de suivi » dit ce qu'on peut faire de la ressource :
  - unit   : suivi objet par objet (ordinateur, badge, telepeage...) -> exige un champ identifiant obligatoire ;
  - none   : ressource sans suivi individuel (veste, chaussures...) ;
  - access : acces numerique (VPN, messagerie, licence) ;
  - quantity : stock suivi par quantite, sans identifiant individuel (vetements par taille, consommables).
Un mode vide ("") veut dire « automatique » (ressources anterieures a l'assistant) : il est deduit de la
categorie et de la presence d'un champ identifiant, et les regles ne produisent alors que des avertissements.
Fonctions pures, sans Flask ni base.
"""
from models.inventory import resolve_identifier_key

TRACKING_MODES = ("unit", "none", "access", "quantity")


def effective_tracking_mode(tracking_mode, category, schema):
    if tracking_mode in TRACKING_MODES:
        return tracking_mode
    if category == "immateriel":
        return "access"
    return "unit" if resolve_identifier_key(schema) else "none"


def _issue(level, code, message):
    return {"level": level, "code": code, "message": message}


def validate_resource(data):
    """Retourne la liste des problemes d'une ressource normalisee. Niveau « error » = bloquant (uniquement quand
    le mode de suivi a ete choisi explicitement) ; « warning » = a corriger ; « info » = a connaitre."""
    schema = data.get("field_schema") or []
    explicit = data.get("tracking_mode") in TRACKING_MODES
    mode = effective_tracking_mode(data.get("tracking_mode"), data.get("category"), schema)
    blocking = "error" if explicit else "warning"
    issues = []

    keys = [f.get("key") for f in schema if isinstance(f, dict)]
    if len(keys) != len(set(keys)):
        issues.append(_issue("error", "duplicate_field", "Deux champs portent le même nom technique."))

    flagged = [f for f in schema if isinstance(f, dict) and f.get("identifier")]
    if len(flagged) > 1:
        issues.append(_issue("error", "several_identifiers", "Un seul champ peut identifier l'objet."))

    if mode == "unit":
        identifier_key = resolve_identifier_key(schema)
        field = next((f for f in schema if f.get("key") == identifier_key), None) if identifier_key else None
        if not field:
            issues.append(_issue(blocking, "no_identifier", "Suivi par objet sans champ identifiant (n° de série, immatriculation, n° de badge…) : aucun historique possible."))
        else:
            if field.get("hidden"):
                issues.append(_issue(blocking, "identifier_hidden", "Le champ identifiant est masqué : il n'est plus saisi dans les dossiers."))
            if not field.get("required"):
                issues.append(_issue(blocking, "identifier_optional", "Le champ identifiant doit être obligatoire, sinon des objets resteront sans historique."))
        if data.get("category") != "materiel":
            issues.append(_issue(blocking, "unit_needs_material", "Le suivi par objet est réservé aux ressources de catégorie matériel."))
        if not data.get("requires_return", True):
            issues.append(_issue("warning", "unit_not_returnable", "Ressource non restituable : l'historique ne verra jamais de restitution."))
        if not data.get("has_assignment_condition"):
            issues.append(_issue("warning", "no_condition", "Activez « état à la remise » : il alimente l'historique (neuf, bon état…)."))
    elif mode == "quantity":
        if data.get("category") != "materiel":
            issues.append(_issue(blocking, "quantity_needs_material", "Le suivi par quantité est réservé aux ressources de catégorie matériel."))
        has_quantity = any(isinstance(f, dict) and (f.get("quantity") or f.get("key") in ("quantite", "quantity", "nombre")) for f in schema)
        if not has_quantity:
            issues.append(_issue("info", "no_quantity_field", "Aucun champ n'a le rôle « Quantité » : chaque remise compte pour 1 unité (choisissez le rôle dans l'éditeur de champs)."))
    elif mode == "none" and data.get("category") == "materiel" and data.get("requires_return", True):
        issues.append(_issue("info", "no_history", "Sans suivi individuel : on sait qu'une ressource a été remise, pas laquelle."))

    if not (data.get("issuer_service") or "").strip():
        issues.append(_issue("warning", "no_issuer", "Aucun service émetteur : personne ne saura qui doit l'attribuer."))
    return issues


def blocking_issues(issues):
    return [issue for issue in issues if issue["level"] == "error"]


def catalog_quality_report(resources):
    """resources : ressources actives (dicts normalises avec field_schema). Retourne celles qui ont des problemes."""
    report = []
    for resource in resources:
        issues = [i for i in validate_resource(resource) if i["level"] != "info"]
        if issues:
            report.append({
                "id": resource.get("id"), "code": resource.get("code"), "label": resource.get("label"),
                "mode": effective_tracking_mode(resource.get("tracking_mode"), resource.get("category"), resource.get("field_schema") or []),
                "issues": issues,
            })
    return report
