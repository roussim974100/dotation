"""Correspondance des anciens noms de champs pour l'affichage du formulaire (align_fields loose)."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.inventory import align_fields


def test_anciens_noms_camel_case_retrouves():
    schema = ["nom_du_poste", "marque", "modele", "numero_de_serie"]
    assert align_fields({"marque": "HP", "nomPoste": "PC1", "numeroSerie": "SN1"}, schema, loose=True) == {"marque": "HP", "nom_du_poste": "PC1", "numero_de_serie": "SN1"}


def test_nom_plus_court_retrouve_en_affichage_seulement():
    assert align_fields({"adresse": "a@b.fr"}, ["adresse_email", "groupes"], loose=True) == {"adresse_email": "a@b.fr"}
    # le mode strict (utilise par le Parc) ne devine pas : comportement inchange
    assert align_fields({"adresse": "a@b.fr"}, ["adresse_email", "groupes"]) == {}


def test_noms_trop_courts_ou_ambigus_ne_sont_pas_devines():
    assert align_fields({"n": "x", "ab": "y"}, ["numero", "abc"], loose=True) == {}
    assert align_fields({"adr": "z"}, ["adresse_email", "adresse_postale"], loose=True) == {}  # deux candidats possibles


def test_une_valeur_deja_presente_sous_le_nom_actuel_est_gardee():
    assert align_fields({"numeroSerie": "ANCIEN", "numero_de_serie": "ACTUEL"}, ["numero_de_serie"], loose=True) == {"numero_de_serie": "ACTUEL"}


def test_numero_et_n_sont_equivalents():
    assert align_fields({"numeroSerie": "SN9"}, ["nom_du_telephone", "n_de_serie_sn"], loose=True) == {"n_de_serie_sn": "SN9"}


def test_schema_embarque_dans_le_dossier_rattache_par_libelle_sans_devinette():
    from models.inventory import align_with_embedded_schema
    embedded = [{"key": "sn", "label": "Numéro de série"}, {"key": "x", "label": "Autre"}]
    current = [{"key": "identifiant_machine", "label": "Numero de serie"}, {"key": "marque", "label": "Marque"}]
    assert align_with_embedded_schema({"sn": "123", "x": "y"}, embedded, current) == {"identifiant_machine": "123"}
    # deux anciens champs de meme libelle : ambigu, on ne rattache pas
    assert align_with_embedded_schema({"a": "1", "b": "2"}, [{"key": "a", "label": "N"}, {"key": "b", "label": "N"}], [{"key": "n", "label": "N"}]) == {}
