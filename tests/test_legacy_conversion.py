"""22/11/2026 : logique de conversion de l'ancien format (materiel/immateriel) vers le format dynamique actuel
(resources.additional), ECRITE ET TESTEE sur donnees synthetiques uniquement (audit de perennite, recommandation
P1 "ancien modele materiel/immateriel"). Ne touche jamais backend/dotation.db ni aucune vraie donnee : a lancer,
une fois revue, depuis un script dedie sur UNE COPIE."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.legacy_conversion import convert_legacy_item, convert_legacy_payload

ORDINATEUR_CATALOG = {
    "id": "resource_ordinateur", "code": "ordinateur", "label": "Ordinateur portable", "requiresReturn": True,
    "field_schema": [
        {"key": "nom_du_poste", "label": "Nom du poste"},
        {"key": "marque", "label": "Marque"},
        {"key": "modele", "label": "Modèle"},
        {"key": "numero_de_serie", "label": "Numéro de série", "identifier": True},
    ],
}


def test_conversion_aligne_les_anciens_noms_de_champs_camel_case_sur_le_schema_actuel():
    """Le catalogue actuel utilise des cles snake_case (numero_de_serie) alors que l'ancien format etait en
    camelCase (numeroSerie) : align_fields doit faire le lien, aucune valeur perdue."""
    legacy = {"selected": True, "nomPoste": "PC-123", "marque": "Dell", "modele": "Latitude", "numeroSerie": "SN-42",
              "assignedAt": "2024-01-01"}
    entry = convert_legacy_item("ordinateur", legacy, ORDINATEUR_CATALOG)
    assert entry["code"] == "ordinateur"
    assert entry["category"] == "materiel"
    assert entry["selected"] is True
    assert entry["fields"] == {"nom_du_poste": "PC-123", "marque": "Dell", "modele": "Latitude", "numero_de_serie": "SN-42"}
    assert entry["assignedAt"] == "2024-01-01"


def test_conversion_sans_entree_catalogue_garde_les_valeurs_sous_les_anciens_noms():
    """Code retire du catalogue depuis : les valeurs ne sont jamais perdues, juste sans schema pour les aligner."""
    legacy = {"selected": True, "description": "Casque de chantier"}
    entry = convert_legacy_item("autre", legacy)
    assert entry["fields"] == {"description": "Casque de chantier"}
    assert entry["label"] == "Autre ressource"
    assert entry["fieldSchema"] == []


def test_conversion_d_un_champ_liste_cles():
    legacy = {"selected": True, "values": ["Bureau 12", "Local technique", ""]}
    entry = convert_legacy_item("cles", legacy)
    assert entry["fields"]["values"] == ["Bureau 12", "Local technique"]


def test_payload_complet_deplace_les_items_selectionnes_et_retire_l_ancien_format():
    payload = {
        "materiel": {
            "ordinateur": {"selected": True, "marque": "Dell", "numeroSerie": "SN-1"},
            "telephone": {"selected": False, "marque": "Jamais coche"},
        },
        "immateriel": {"email": {"selected": True, "adresse": "a@b.fr"}},
        "resources": {"additional": []},
    }
    converted, keys = convert_legacy_payload(payload, {"ordinateur": ORDINATEUR_CATALOG})
    assert set(keys) == {"ordinateur", "email"}
    codes = {r["code"] for r in converted["resources"]["additional"]}
    assert codes == {"ordinateur", "email"}
    # L'item non selectionne (telephone) est laisse tel quel, pas converti ni retire.
    assert "telephone" in converted["materiel"]
    assert "ordinateur" not in converted["materiel"]
    assert "immateriel" not in converted  # section videe entierement -> retiree


def test_payload_ne_duplique_jamais_un_item_deja_present_dans_additional():
    payload = {
        "materiel": {"ordinateur": {"selected": True, "marque": "Dell"}},
        "resources": {"additional": [{"id": "x", "code": "ordinateur", "label": "Deja migre", "selected": True}]},
    }
    converted, keys = convert_legacy_payload(payload)
    assert keys == []  # rien reconverti
    assert len(converted["resources"]["additional"]) == 1  # pas de doublon
    assert "materiel" not in converted  # le residu de l'ancien format est tout de meme retire


def test_payload_original_n_est_jamais_modifie_en_place():
    payload = {"materiel": {"ordinateur": {"selected": True, "marque": "Dell"}}, "resources": {"additional": []}}
    convert_legacy_payload(payload)
    assert "ordinateur" in payload["materiel"]  # l'original, non touche
