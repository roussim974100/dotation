"""Tests du endpoint GET /api/catalog/suggestions/<resource_id>.

Scénarios :
  1. Ressource inexistante → 200 avec values/linked vides
  2. Ressource sans champ suggest → values/linked vides
  3. Ressource avec champs suggest, aucune fiche → listes vides
  4. Champs suggest remplis dans des fiches → valeurs présentes, triées par fréquence
  5. Liaison marque → modèle (linked) correctement construite
  6. Liaison bidirectionnelle (modèle → marque aussi)
  7. Fiches annulées exclues du calcul
  8. Ressource non sélectionnée dans la fiche ignorée
  9. Sans authentification → 401
  10. Valeurs vides ignorées (ne polluent pas les suggestions)
"""

import json
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BENE = {"nom": "Test", "prenom": "Util"}


def _create_resource(client, code="cam_test", label="Caméra test",
                     field_schema=None):
    """Crée une ressource catalogue avec champs suggest et retourne son id."""
    if field_schema is None:
        field_schema = [
            {"key": "marque", "label": "Marque", "type": "text", "suggest": True, "required": False},
            {"key": "modele", "label": "Modèle", "type": "text", "suggest": True, "required": False},
        ]
    r = client.post("/api/admin/resources", json={
        "code": code,
        "label": label,
        "category": "materiel",
        "field_schema": field_schema,
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()["resource"]["id"]


def _create_form_with_resource(client, resource_id, fields, selected=True,
                               status="active"):
    """Crée une fiche ayant la ressource en additional avec les champs donnés."""
    payload = {
        "beneficiaire": _BENE,
        "workflow": {"status": status},
        "validation": {"signatureDataUrl": "data:image/png;base64,AA==", "rgpdAccepted": True},
        "meta": {"lockedAt": "2026-01-01T00:00:00Z"},
        "resources": {
            "additional": [
                {
                    "id": resource_id,
                    "selected": selected,
                    "category": "materiel",
                    "fields": fields,
                }
            ]
        },
    }
    r = client.post("/api/forms", json=payload)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["summary"]["id"]


def _suggestions(client, resource_id):
    r = client.get(f"/api/catalog/suggestions/{resource_id}")
    assert r.status_code == 200
    return r.get_json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSuggestionsEndpoint:

    def test_resource_not_found_returns_empty(self, admin_client):
        data = _suggestions(admin_client, "res_doesnotexist")
        assert data == {"values": {}, "linked": {}}

    def test_no_suggest_fields_returns_empty(self, admin_client):
        rid = _create_resource(admin_client, code="nosuggest", label="Sans suggest",
                               field_schema=[
                                   {"key": "ref", "label": "Référence", "type": "text",
                                    "suggest": False, "required": False}
                               ])
        data = _suggestions(admin_client, rid)
        assert data == {"values": {}, "linked": {}}

    def test_no_forms_returns_empty_lists(self, admin_client):
        rid = _create_resource(admin_client)
        data = _suggestions(admin_client, rid)
        assert data["values"] == {"marque": [], "modele": []}
        assert data["linked"] == {}

    def test_single_form_values_present(self, admin_client):
        rid = _create_resource(admin_client)
        _create_form_with_resource(admin_client, rid, {"marque": "Apple", "modele": "iPhone 14"})
        data = _suggestions(admin_client, rid)
        assert "Apple" in data["values"]["marque"]
        assert "iPhone 14" in data["values"]["modele"]

    def test_frequency_order(self, admin_client):
        """La valeur la plus fréquente doit apparaître en premier."""
        rid = _create_resource(admin_client)
        for _ in range(3):
            _create_form_with_resource(admin_client, rid, {"marque": "Samsung", "modele": "Galaxy S23"})
        _create_form_with_resource(admin_client, rid, {"marque": "Apple", "modele": "iPhone 14"})
        data = _suggestions(admin_client, rid)
        assert data["values"]["marque"][0] == "Samsung"

    def test_linked_marque_to_modele(self, admin_client):
        """Sélectionner Apple doit filtrer les modèles vers les modèles Apple."""
        rid = _create_resource(admin_client)
        _create_form_with_resource(admin_client, rid, {"marque": "Apple", "modele": "iPhone 14"})
        _create_form_with_resource(admin_client, rid, {"marque": "Apple", "modele": "iPhone 15"})
        _create_form_with_resource(admin_client, rid, {"marque": "Samsung", "modele": "Galaxy S23"})
        data = _suggestions(admin_client, rid)
        apple_models = data["linked"]["marque"]["Apple"]["modele"]
        assert "iPhone 14" in apple_models
        assert "iPhone 15" in apple_models
        assert "Galaxy S23" not in apple_models

    def test_linked_is_bidirectional(self, admin_client):
        """Le lien modèle → marque doit aussi exister."""
        rid = _create_resource(admin_client)
        _create_form_with_resource(admin_client, rid, {"marque": "Apple", "modele": "iPhone 14"})
        data = _suggestions(admin_client, rid)
        assert "modele" in data["linked"]
        assert "marque" in data["linked"]["modele"]["iPhone 14"]
        assert "Apple" in data["linked"]["modele"]["iPhone 14"]["marque"]

    def test_cancelled_forms_excluded(self, admin_client):
        """Les fiches annulées ne doivent pas alimenter les suggestions."""
        rid = _create_resource(admin_client)
        form_id = _create_form_with_resource(
            admin_client, rid, {"marque": "Motorola", "modele": "G54"},
            status="active"
        )
        # Annuler la fiche directement via PUT en forçant le statut
        r = admin_client.get(f"/api/forms/{form_id}")
        payload = r.get_json()["data"]
        payload["workflow"]["status"] = "cancelled"
        admin_client.put(f"/api/forms/{form_id}", json=payload)
        data = _suggestions(admin_client, rid)
        assert "Motorola" not in data["values"].get("marque", [])

    def test_unselected_resource_ignored(self, admin_client):
        """Une ressource non cochée (selected=False) ne doit pas alimenter les suggestions."""
        rid = _create_resource(admin_client)
        _create_form_with_resource(admin_client, rid,
                                   {"marque": "Phantom", "modele": "X1"},
                                   selected=False)
        data = _suggestions(admin_client, rid)
        assert "Phantom" not in data["values"].get("marque", [])

    def test_requires_auth(self, client):
        r = client.get("/api/catalog/suggestions/any-id")
        assert r.status_code == 401

    def test_empty_field_values_ignored(self, admin_client):
        """Les valeurs vides ne doivent pas polluer les suggestions."""
        rid = _create_resource(admin_client)
        _create_form_with_resource(admin_client, rid,
                                   {"marque": "Apple", "modele": ""})
        data = _suggestions(admin_client, rid)
        assert "Apple" in data["values"]["marque"]
        assert "" not in data["values"].get("modele", [])

    def test_three_suggest_fields_linked(self, admin_client):
        """Avec 3 champs suggest, la structure linked couvre toutes les paires."""
        rid = _create_resource(admin_client, code="tri_suggest", label="Triple",
                               field_schema=[
                                   {"key": "marque", "label": "Marque", "type": "text",
                                    "suggest": True, "required": False},
                                   {"key": "modele", "label": "Modèle", "type": "text",
                                    "suggest": True, "required": False},
                                   {"key": "couleur", "label": "Couleur", "type": "text",
                                    "suggest": True, "required": False},
                               ])
        _create_form_with_resource(admin_client, rid,
                                   {"marque": "Apple", "modele": "iPhone 14", "couleur": "Noir"})
        data = _suggestions(admin_client, rid)
        # marque → modèle ET marque → couleur
        assert "modele" in data["linked"]["marque"]["Apple"]
        assert "couleur" in data["linked"]["marque"]["Apple"]
        # modèle → couleur
        assert "couleur" in data["linked"]["modele"]["iPhone 14"]
