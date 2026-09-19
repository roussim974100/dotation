"""
Tests couvrant les correctifs de la session v3.18.6-dev :
- schema de champs de ressource : cle immuable, masquage (hidden), validation
- summarize_dynamic_resource / summarize_resource_item_details : rendu schema-aware
- count_resource_field_usage : comptage d'usage avant suppression d'un champ
- CSRF : contrat backend (en-tete requis sur les requetes mutantes)
"""
import sys
import json
import sqlite3
import tempfile
import os
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.workflow import (
    normalize_resource_field_schema,
    summarize_dynamic_resource,
    summarize_resource_item_details,
    is_dynamic_resource_complete,
    collect_resource_validation_errors,
    count_resource_field_usage,
)


# ---------------------------------------------------------------------------
# normalize_resource_field_schema : le flag "hidden" doit survivre a la normalisation
# ---------------------------------------------------------------------------

def test_normalize_resource_field_schema_preserves_hidden_flag():
    schema = normalize_resource_field_schema([
        {"key": "numeroSerie", "label": "N de serie", "hidden": True},
        {"key": "marque", "label": "Marque"},
    ])
    assert schema[0]["hidden"] is True
    assert schema[1]["hidden"] is False
    print("[PASS] normalize_resource_field_schema conserve le flag hidden")


# ---------------------------------------------------------------------------
# summarize_dynamic_resource : rendu "Label : valeur" schema-aware
# ---------------------------------------------------------------------------

def test_summarize_dynamic_resource_labels_values_in_schema_order():
    resource = {
        "fields": {"numeroSerie": "SN123", "marque": "Dell"},
        "fieldSchema": [
            {"key": "numeroSerie", "label": "N de serie"},
            {"key": "marque", "label": "Marque"},
        ],
    }
    assert summarize_dynamic_resource(resource) == "N de serie : SN123 - Marque : Dell"
    print("[PASS] summarize_dynamic_resource labellise dans l'ordre du schema")


def test_summarize_dynamic_resource_keeps_orphan_value_unlabeled():
    # Champ renomme/supprime depuis : la valeur reste affichee, brute, plutot que de disparaitre.
    resource = {
        "fields": {"numeroSerie": "SN123", "ancienChamp": "valeur-orpheline"},
        "fieldSchema": [{"key": "numeroSerie", "label": "N de serie"}],
    }
    result = summarize_dynamic_resource(resource)
    assert "N de serie : SN123" in result
    assert "valeur-orpheline" in result
    print("[PASS] summarize_dynamic_resource garde les valeurs orphelines (non labellisees)")


def test_summarize_dynamic_resource_case_insensitive_legacy_keys():
    # Piege rencontre en session : normalize_resource_field_schema met la cle en
    # minuscules (slugify_field_key), alors que des ressources historiques (ex.
    # telephone -> numeroSerie) ont leurs valeurs stockees en camelCase.
    resource = {
        "fields": {"numeroSerie": "SN999"},
        "fieldSchema": [{"key": "numeroSerie", "label": "N de serie"}],
    }
    result = summarize_dynamic_resource(resource)
    assert result == "N de serie : SN999", f"cle camelCase non reconnue : {result!r}"
    print("[PASS] summarize_dynamic_resource repli insensible a la casse (cles legacy camelCase)")


def test_summarize_dynamic_resource_no_schema_falls_back_to_raw_join():
    resource = {"fields": {"x": "valeur1", "y": "valeur2"}}
    assert summarize_dynamic_resource(resource) == "valeur1 - valeur2"
    print("[PASS] summarize_dynamic_resource repli join brut sans schema")


# ---------------------------------------------------------------------------
# summarize_resource_item_details : dispatch ressource dynamique vs item statique
# ---------------------------------------------------------------------------

def test_summarize_resource_item_details_static_item():
    details = {"selected": True, "marque": "Apple", "modele": "iPhone", "conditionAttribution": "neuf"}
    result = summarize_resource_item_details(details)
    assert "Apple" in result and "iPhone" in result
    assert "neuf" not in result  # conditionAttribution exclu du resume
    print("[PASS] summarize_resource_item_details item statique (exclut les cles de suivi)")


def test_summarize_resource_item_details_dynamic_item():
    details = {"fields": {"numeroSerie": "SN1"}, "fieldSchema": [{"key": "numeroSerie", "label": "N de serie"}]}
    assert summarize_resource_item_details(details) == "N de serie : SN1"
    print("[PASS] summarize_resource_item_details delegue a summarize_dynamic_resource")


# ---------------------------------------------------------------------------
# Champ masque (hidden) : exclu de la validation "obligatoire"
# ---------------------------------------------------------------------------

def test_hidden_field_excluded_from_is_dynamic_resource_complete():
    resource = {
        "selected": True,
        "fieldSchema": [{"key": "numeroSerie", "label": "N de serie", "required": True, "hidden": True}],
        "fields": {},
        "hasAssignmentDate": False,
    }
    # Le champ requis est masque et vide : ne doit plus bloquer la completion.
    assert is_dynamic_resource_complete(resource) is True
    print("[PASS] is_dynamic_resource_complete ignore les champs masques")


def test_visible_required_field_still_blocks_completion():
    resource = {
        "selected": True,
        "fieldSchema": [{"key": "numeroSerie", "label": "N de serie", "required": True, "hidden": False}],
        "fields": {},
        "hasAssignmentDate": False,
    }
    assert is_dynamic_resource_complete(resource) is False
    print("[PASS] is_dynamic_resource_complete bloque toujours un champ visible obligatoire vide")


def test_hidden_field_excluded_from_collect_resource_validation_errors():
    payload = {
        "resources": {
            "additional": [{
                "selected": True,
                "label": "Test",
                "fieldSchema": [{"key": "numeroSerie", "label": "N de serie", "required": True, "hidden": True}],
                "fields": {},
                "hasAssignmentDate": False,
            }]
        }
    }
    errors = collect_resource_validation_errors(payload)
    assert not any("N de serie" in e for e in errors)
    print("[PASS] collect_resource_validation_errors ignore les champs masques")


# ---------------------------------------------------------------------------
# count_resource_field_usage : comptage avant suppression reelle d'un champ
# ---------------------------------------------------------------------------

def _build_temp_db(tmpdir):
    db_path = os.path.join(tmpdir, "test_usage.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, payload_json TEXT);
        CREATE TABLE dotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            form_id TEXT, item_key TEXT, details_json TEXT
        );
    """)
    return conn


def test_count_resource_field_usage_counts_distinct_dossiers():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = _build_temp_db(tmpdir)

        # f1 : valeur non vide sur le champ -> compte
        payload1 = {"resources": {"additional": [{"code": "badge_visiteur", "fields": {"numeroSerie": "ABC123"}}]}}
        # f2 : champ present mais vide -> ne compte pas
        payload2 = {"resources": {"additional": [{"code": "badge_visiteur", "fields": {"numeroSerie": ""}}]}}
        # f3 : autre ressource -> ne compte pas
        payload3 = {"resources": {"additional": [{"code": "autre_ressource", "fields": {"numeroSerie": "XYZ"}}]}}
        conn.execute("INSERT INTO dotation_forms VALUES (?, ?)", ("f1", json.dumps(payload1)))
        conn.execute("INSERT INTO dotation_forms VALUES (?, ?)", ("f2", json.dumps(payload2)))
        conn.execute("INSERT INTO dotation_forms VALUES (?, ?)", ("f3", json.dumps(payload3)))

        # f4 : uniquement present via dotation_items, cle historique en camelCase
        conn.execute(
            "INSERT INTO dotation_items (form_id, item_key, details_json) VALUES (?, ?, ?)",
            ("f4", "badge_visiteur", json.dumps({"fields": {"NumeroSerie": "ZZZ"}})),
        )
        conn.commit()

        assert count_resource_field_usage(conn, "badge_visiteur", "numeroSerie") == 2  # f1 + f4
        assert count_resource_field_usage(conn, "badge_visiteur", "inconnu") == 0
        assert count_resource_field_usage(conn, "", "numeroSerie") == 0
        conn.close()
    print("[PASS] count_resource_field_usage compte les bons dossiers distincts (payload_json + dotation_items)")


# ---------------------------------------------------------------------------
# CSRF : contrat backend sur les requetes mutantes /api/ authentifiees
# (le bug de session etait cote frontend - en-tete jamais envoye - ce test
# protege le contrat que le frontend doit honorer : sans en-tete -> 403)
# ---------------------------------------------------------------------------

def test_csrf_missing_header_is_rejected():
    from app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test_csrf_user"
        sess["csrf_token"] = "expected-token-123"

    resp = client.put("/api/admin/resources/does-not-exist", json={"label": "x"})
    assert resp.status_code == 403
    assert resp.get_json().get("error") == "csrf_invalid"
    print("[PASS] requete mutante /api/ sans X-CSRF-Token -> 403 csrf_invalid")


def test_csrf_valid_header_passes_check():
    from app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test_csrf_user"
        sess["csrf_token"] = "expected-token-123"

    resp = client.put(
        "/api/admin/resources/does-not-exist",
        json={"label": "x"},
        headers={"X-CSRF-Token": "expected-token-123"},
    )
    # Le token est valide : la requete passe le controle CSRF (peut ensuite
    # echouer plus loin - permission/ressource inexistante - mais plus en 403 csrf_invalid).
    assert not (resp.status_code == 403 and resp.get_json().get("error") == "csrf_invalid")
    print("[PASS] requete mutante /api/ avec X-CSRF-Token valide passe le controle CSRF")


if __name__ == "__main__":
    test_normalize_resource_field_schema_preserves_hidden_flag()
    test_summarize_dynamic_resource_labels_values_in_schema_order()
    test_summarize_dynamic_resource_keeps_orphan_value_unlabeled()
    test_summarize_dynamic_resource_case_insensitive_legacy_keys()
    test_summarize_dynamic_resource_no_schema_falls_back_to_raw_join()
    test_summarize_resource_item_details_static_item()
    test_summarize_resource_item_details_dynamic_item()
    test_hidden_field_excluded_from_is_dynamic_resource_complete()
    test_visible_required_field_still_blocks_completion()
    test_hidden_field_excluded_from_collect_resource_validation_errors()
    test_count_resource_field_usage_counts_distinct_dossiers()
    test_csrf_missing_header_is_rejected()
    test_csrf_valid_header_passes_check()
    print("\nTous les tests sont passes.")
