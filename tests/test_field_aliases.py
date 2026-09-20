"""Anciens noms de champs : alias declares a la modification du catalogue + correspondance exacte a la lecture."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.catalog import carry_over_field_aliases
from models.inventory import align_fields, schema_key_set
from models.workflow import normalize_resource_field_schema


def _schema(*pairs):
    return normalize_resource_field_schema([{"key": k, "label": l} for k, l in pairs])


def test_cle_renommee_devient_alias_par_libelle():
    old = _schema(("serial", "Numéro de série"), ("marque", "Marque"))
    new = _schema(("numero_serie", "Numéro de série"), ("marque", "Marque"))
    out = carry_over_field_aliases(old, new)
    assert out[0]["aliases"] == ["serial"] and out[1]["aliases"] == []


def test_pas_d_appariement_par_position_si_le_libelle_change():
    # supprimer un champ et en ajouter un autre ne doit JAMAIS rattacher les anciennes valeurs au nouveau champ
    out = carry_over_field_aliases(_schema(("sn", "SN")), _schema(("numero_de_serie", "Numéro de série")))
    assert out[0]["aliases"] == []


def test_les_alias_existants_survivent_a_la_sauvegarde_suivante():
    old = normalize_resource_field_schema([{"key": "numero_serie", "label": "Numéro de série", "aliases": ["serial"]}])
    new = normalize_resource_field_schema([{"key": "numero_serie", "label": "Numéro de série"}])  # l'éditeur n'envoie pas les alias
    assert carry_over_field_aliases(old, new)[0]["aliases"] == ["serial"]


def test_alias_retrouve_la_valeur_sans_heuristique():
    keys = schema_key_set([{"key": "identifiant_unique", "aliases": ["zzz"]}])
    assert align_fields({"zzz": "V1"}, keys) == {"identifiant_unique": "V1"}


def test_champ_masque_ou_inchange_n_ajoute_pas_d_alias():
    same = _schema(("a", "A"))
    assert carry_over_field_aliases(same, _schema(("a", "A")))[0]["aliases"] == []
