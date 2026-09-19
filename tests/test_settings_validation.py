"""Reglages de l'organisation : mise a jour partielle sure, types de beneficiaires valides (toutes langues), setup verrouille."""
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.settings import (SettingsValidationError, get_app_settings, normalize_beneficiary_types, save_app_settings,
                             seed_app_settings)


def _connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT, updated_at TEXT)")
    seed_app_settings(connection)
    return connection


def test_valeur_absente_ne_efface_rien():
    connection = _connection()
    save_app_settings(connection, {"org_name": "Ville de Test", "support_email": "aide@test.fr", "beneficiary_types": "salarie:Salarié"})
    save_app_settings(connection, {"org_name": None, "support_email": None, "beneficiary_types": None, "theme_id": "foret"})
    settings = get_app_settings(connection)
    assert settings["org_name"] == "Ville de Test" and settings["support_email"] == "aide@test.fr"
    assert settings["beneficiary_types"] == "salarie:Salarié" and settings["theme_id"] == "foret"


def test_chaine_vide_vide_bien_le_reglage():
    connection = _connection()
    save_app_settings(connection, {"support_name": "Marie"})
    save_app_settings(connection, {"support_name": ""})
    assert get_app_settings(connection)["support_name"] == ""


def test_types_de_beneficiaires_toutes_langues():
    assert normalize_beneficiary_types("agent:Agent, elu:Élu(e)") == "agent:Agent,elu:Élu(e)"
    assert normalize_beneficiary_types("employee:Employee,volunteer:Volunteer") == "employee:Employee,volunteer:Volunteer"
    assert normalize_beneficiary_types("staff:员工,member:Мember") == "staff:员工,member:Мember"


@pytest.mark.parametrize("raw", [
    "", "agent", "Agent:Agent", "a b:Agent", "agent:", "agent:Ag,ent", "agent:A;B", "agent:<b>x</b>", 'agent:"x"',
    "agent:Agent,agent:Autre", "x" * 41 + ":Agent", "agent:" + "l" * 61,
])
def test_types_de_beneficiaires_invalides_refuses(raw):
    with pytest.raises(SettingsValidationError):
        normalize_beneficiary_types(raw)


def test_save_refuse_un_type_invalide_sans_rien_ecrire():
    connection = _connection()
    before = get_app_settings(connection)["beneficiary_types"]
    with pytest.raises(SettingsValidationError):
        save_app_settings(connection, {"org_name": "Nouvelle", "beneficiary_types": "agent:A:B"})
    settings = get_app_settings(connection)
    assert settings["beneficiary_types"] == before and settings["org_name"] == ""


def test_texte_trop_long_refuse():
    connection = _connection()
    with pytest.raises(SettingsValidationError):
        save_app_settings(connection, {"org_name": "x" * 201})
