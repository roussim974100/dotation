"""Conversion de l'ancien format fixe (payload["materiel"]/["immateriel"]) vers le format dynamique actuel
(payload["resources"]["additional"]). Fonctions PURES (aucun acces base) : la correspondance ancien nom de champ ->
nom de champ du catalogue ACTUEL passe par `align_fields` (models/inventory.py), le meme mecanisme deja utilise pour
AFFICHER un ancien dossier sans perdre ses valeurs - donc deja eprouve, pas une nouvelle regle de correspondance a
maintenir en double.

Volontairement PAS branche sur une route ni un script d'execution : l'audit de perennite du 22/11/2026 (recommandation
P1 "ancien modele materiel/immateriel", ~150 references de code pour 7 dossiers sur une copie de production) demande
d'ecrire et tester cette logique, PAS de l'executer sur de vraies donnees sans revue humaine prealable. Pour migrer
un vrai dossier : appeler `convert_legacy_payload` depuis un script dedie, sur UNE COPIE, jamais sur
backend/dotation.db.

Types geres : ordinateur, ecran, telephone, tablette, vehicule, badge, cles, veste, chaussuresSecurite, autre (materiel),
email, vpn, zoneAlarme (immateriel) - memes types et memes anciens noms de champs que `collect_resource_entries`
(models/workflow.py), source de verite pour ce qui doit etre reconnu comme "ancien format"."""
from models.inventory import align_fields, schema_key_set

# item_key -> (category, label de repli, champs scalaires "ancien nom -> valeur", champ liste eventuel)
LEGACY_SPECS = {
    "ordinateur": ("materiel", "Ordinateur", ("nomPoste", "marque", "modele", "numeroSerie"), None),
    "ecran": ("materiel", "Écran", ("marque", "modele", "numeroSerie"), None),
    "telephone": ("materiel", "Téléphone", ("nomTelephone", "marque", "modele", "numeroSerie"), None),
    "tablette": ("materiel", "Tablette", ("nomTablette", "marque", "modele", "numeroSerie"), None),
    "vehicule": ("materiel", "Véhicule", ("marque", "modele", "immatriculation"), None),
    "badge": ("materiel", "Badge d'accès", ("numero",), None),
    "autre": ("materiel", "Autre ressource", ("description",), None),
    "veste": ("materiel", "Veste", (), None),
    "chaussuresSecurite": ("materiel", "Chaussures de sécurité", (), None),
    "cles": ("materiel", "Clé(s)", (), "values"),
    "email": ("immateriel", "Messagerie", ("adresse",), None),
    "vpn": ("immateriel", "VPN", (), None),
    "zoneAlarme": ("immateriel", "Zone alarme", (), "zones"),
}


def convert_legacy_item(item_key, legacy_item, catalog_entry=None):
    """Construit une entree resources.additional a partir d'UN item de l'ancien format (deja verifie "selected").
    `catalog_entry` : {"id", "code", "label", "field_schema", "requiresReturn"} du catalogue actuel pour ce code,
    ou None si ce code n'est plus (ou jamais ete) au catalogue - l'entree est alors construite sans schema (les
    valeurs restent dans `details`, comme le fait deja `summarize_dynamic_resource` pour une ressource inconnue)."""
    category, fallback_label, scalar_fields, list_field = LEGACY_SPECS[item_key]
    raw_fields = {key: legacy_item.get(key) for key in scalar_fields if str(legacy_item.get(key) or "").strip()}
    if list_field:
        values = [str(v).strip() for v in (legacy_item.get(list_field) or []) if str(v or "").strip()]
        raw_fields = {**raw_fields, list_field: values}

    schema = (catalog_entry or {}).get("field_schema") or []
    # align_fields (loose=True) reconnait deja camelCase vs snake_case et les anciens alias declares sur le champ :
    # c'est le meme mecanisme qui affiche deja un ancien dossier sans perdre ses valeurs (persist_form). Si un champ
    # ne s'aligne vraiment sur rien (schema trop different), ce n'est pas rattrape ici : a verifier au cas par cas
    # avant d'executer cette conversion sur une vraie copie (voir le compte de champs avant/apres dans le rapport).
    fields = align_fields(raw_fields, schema_key_set(schema), loose=True) if schema else dict(raw_fields)

    entry = {
        "id": (catalog_entry or {}).get("id") or item_key,
        "code": (catalog_entry or {}).get("code") or item_key,
        "label": (catalog_entry or {}).get("label") or fallback_label,
        "category": category,
        "selected": True,
        "requiresReturn": bool((catalog_entry or {}).get("requiresReturn", True)),
        "fieldSchema": schema,
        "fields": fields,
    }
    for key in ("assignedAt", "conditionAttribution", "conditionNotes"):
        if legacy_item.get(key):
            entry[key] = legacy_item[key]
    return entry


def convert_legacy_payload(payload, catalog_by_code=None):
    """Retourne une COPIE du payload ou chaque item "selected" de l'ancien format (materiel/immateriel) a ete
    deplace vers resources.additional, et retire de materiel/immateriel. Les items deja convertis par ailleurs
    (meme code deja present dans resources.additional) sont laisses tels quels, jamais dupliques. N'ecrit rien :
    a appeler avant un persist_form, sur UNE COPIE de la base, jamais sur backend/dotation.db."""
    import copy
    catalog_by_code = catalog_by_code or {}
    payload = copy.deepcopy(payload)
    additional = payload.setdefault("resources", {}).setdefault("additional", [])
    already_present = {str(r.get("code") or r.get("id")) for r in additional}
    converted_keys = []

    for section_name in ("materiel", "immateriel"):
        section = payload.get(section_name) or {}
        for item_key, legacy_item in list(section.items()):
            if item_key not in LEGACY_SPECS or not isinstance(legacy_item, dict) or not legacy_item.get("selected"):
                continue
            if item_key in already_present:
                del section[item_key]  # deja migre par ailleurs : on retire juste le residu de l'ancien format
                continue
            additional.append(convert_legacy_item(item_key, legacy_item, catalog_by_code.get(item_key)))
            del section[item_key]
            converted_keys.append(item_key)
        if section_name in payload and not payload[section_name]:
            del payload[section_name]

    return payload, converted_keys
