"""Identifiant interne immuable des champs : attribue, conserve, herite au renommage, et utilise pour retrouver une valeur."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from migrations import field_id_for
from models.catalog import carry_over_field_aliases, normalize_resource_catalog_payload
from models.inventory import align_with_embedded_schema
from models.workflow import normalize_resource_field_schema


def test_identifiant_deterministe_et_stable():
    assert field_id_for("pc", "numero") == field_id_for("pc", "numero") != field_id_for("pc", "autre")


def test_un_nouveau_champ_recoit_un_identifiant_et_il_survit_a_la_sauvegarde_suivante():
    created = normalize_resource_catalog_payload({"code": "x", "label": "X", "field_schema": [{"key": "a", "label": "A"}]})
    field_id = created["field_schema"][0]["id"]
    assert field_id.startswith("fld_")
    existing = {"field_schema_json": __import__("json").dumps(created["field_schema"])}
    again = normalize_resource_catalog_payload({"code": "x", "label": "X", "field_schema": [{"key": "a", "label": "A"}]}, existing)  # l'editeur ne renvoie pas l'id
    assert again["field_schema"][0]["id"] == field_id


def test_renommage_de_cle_garde_le_meme_identifiant():
    old = normalize_resource_field_schema([{"id": "fld_1", "key": "sn", "label": "N° de série"}])
    new = normalize_resource_field_schema([{"key": "numero_serie", "label": "N° de série"}])
    assert carry_over_field_aliases(old, new)[0]["id"] == "fld_1"


def test_valeur_retrouvee_par_identifiant_meme_si_le_libelle_change():
    embedded = [{"id": "fld_1", "key": "sn", "label": "Ancien libellé"}]
    current = [{"id": "fld_1", "key": "numero_serie", "label": "Numéro de série"}]
    assert align_with_embedded_schema({"sn": "42"}, embedded, current) == {"numero_serie": "42"}
