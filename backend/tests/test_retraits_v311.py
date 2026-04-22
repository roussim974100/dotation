"""
Tests pour v3.11.0 : Dossier "mise à jour" avec retraits signés.

Teste le workflow complet :
1. Créer un dossier source finalisé avec ressources
2. Créer un dossier mise_à_jour qui le référence
3. Vérifier que les retraits sont marqués dans le dossier source
4. Générer le PDF de retraits
"""

import pytest
from datetime import datetime


class TestRetraitsFeature:
    """Tests du workflow retraits v3.11.0"""

    def test_create_source_form_finalized(self, admin_client):
        """Créer un dossier source finalisé avec un équipement"""
        payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "arrivee"},
            "beneficiaire": {
                "nom": "Dupont",
                "prenom": "Jean",
                "qualite": "agent",
                "service": "DSI",
            },
            "materiel": {
                "ordinateur": {
                    "selected": True,
                    "marque": "Dell",
                    "modele": "Latitude",
                }
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }

        resp = admin_client.post("/api/forms", json=payload)
        assert resp.status_code == 201
        data = resp.json
        source_form_id = data["summary"]["id"]
        assert source_form_id

    def test_get_retrait_items(self, admin_client):
        """Récupérer les items à retirer d'un dossier"""
        # Créer source
        payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "arrivee"},
            "beneficiaire": {"nom": "Test", "prenom": "User", "qualite": "agent"},
            "materiel": {
                "ordinateur": {"selected": True, "marque": "HP", "modele": "Pavilion"}
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "validation": {"rgpdAccepted": True, "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="},
        }
        resp = admin_client.post("/api/forms", json=payload)
        assert resp.status_code == 201
        source_form_id = resp.json["summary"]["id"]

        # Récupérer items à retirer
        resp = admin_client.get(f"/api/forms/{source_form_id}/retrait-items")
        assert resp.status_code == 200
        items = resp.json
        assert len(items) > 0
        assert any(item["item_key"] == "ordinateur" for item in items)

    def test_create_mise_a_jour_with_retraits(self, admin_client):
        """Créer un dossier mise_à_jour avec retraits"""
        # Créer source
        source_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "arrivee"},
            "beneficiaire": {"nom": "Dupont", "prenom": "Jean", "qualite": "agent"},
            "materiel": {
                "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude"}
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=source_payload)
        source_form_id = resp.json["summary"]["id"]

        # Créer mise_à_jour
        miseajour_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {
                "type": "mise_a_jour",
                "sourceFormId": source_form_id,
            },
            "beneficiaire": {"nom": "Dupont", "prenom": "Jean", "qualite": "agent"},
            "materiel": {
                "ordinateur": {"selected": True, "marque": "HP", "modele": "ProBook"}
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "retraits": {
                "items": {
                    "ordinateur": {
                        "selected": True,
                        "etat": "Bon",
                        "notes": "PC restitué en bon état",
                    }
                },
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=miseajour_payload)
        assert resp.status_code == 201
        miseajour_form_id = resp.json["summary"]["id"]
        assert resp.json["summary"]["dossierType"] == "mise_a_jour"

        # Vérifier que le source a été mis à jour avec les retraits
        resp = admin_client.get(f"/api/forms/{source_form_id}")
        assert resp.status_code == 200
        source_updated = resp.json["data"]
        restitution = source_updated.get("restitution", {})
        items = restitution.get("items", {})

        # Vérifier que l'ordinateur a été marqué comme retiré
        assert "ordinateur" in items
        assert items["ordinateur"].get("state") == "conforme"
        assert "restitué" in items["ordinateur"].get("notes", "").lower()

    def test_retrait_pdf_endpoint(self, admin_client):
        """Tester l'endpoint de génération du PDF retraits"""
        # Créer mise_à_jour
        source_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "arrivee"},
            "beneficiaire": {"nom": "Test", "prenom": "User", "qualite": "agent"},
            "materiel": {"ordinateur": {"selected": True}},
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=source_payload)
        assert resp.status_code == 201
        source_form_id = resp.json["summary"]["id"]

        miseajour_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "mise_a_jour", "sourceFormId": source_form_id},
            "beneficiaire": {"nom": "Test", "prenom": "User", "qualite": "agent"},
            "materiel": {"ordinateur": {"selected": True}},
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "retraits": {
                "items": {"ordinateur": {"selected": True, "etat": "Bon", "notes": "OK"}},
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=miseajour_payload)
        assert resp.status_code == 201
        miseajour_form_id = resp.json["summary"]["id"]

        # Générer PDF
        resp = admin_client.get(f"/api/forms/{miseajour_form_id}/pdf/retraits")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert len(resp.data) > 0

    def test_retrait_permission_required(self, client):
        """Vérifier que les permissions sont requises"""
        # Sans authentification
        resp = client.get("/api/forms/test-id/retrait-items")
        assert resp.status_code == 401

    def test_retraits_application_debug(self, admin_client):
        """Debug test pour vérifier l'application des retraits"""
        # Créer source
        source_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {"type": "arrivee"},
            "beneficiaire": {"nom": "Dupont", "prenom": "Jean", "qualite": "agent"},
            "materiel": {
                "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude"}
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=source_payload)
        assert resp.status_code == 201
        source_form_id = resp.json["summary"]["id"]

        # Check source form restitution before retraits
        resp_before = admin_client.get(f"/api/forms/{source_form_id}")
        restitution_before = resp_before.json["data"].get("restitution", {})
        print(f"Source restitution BEFORE: {restitution_before}")

        # Créer mise_à_jour avec retraits
        miseajour_payload = {
            "meta": {"savedAt": datetime.now().isoformat()},
            "workflow": {"status": "active"},
            "dossier": {
                "type": "mise_a_jour",
                "sourceFormId": source_form_id,
            },
            "beneficiaire": {"nom": "Dupont", "prenom": "Jean", "qualite": "agent"},
            "materiel": {
                "ordinateur": {"selected": True, "marque": "HP", "modele": "ProBook"}
            },
            "immateriel": {},
            "resources": {"additional": []},
            "unc_acces": [],
            "retraits": {
                "items": {
                    "ordinateur": {
                        "selected": True,
                        "etat": "Bon",
                        "notes": "PC restitué en bon état",
                    }
                },
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
            "validation": {
                "rgpdAccepted": True,
                "signatureDataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
            },
        }
        resp = admin_client.post("/api/forms", json=miseajour_payload)
        assert resp.status_code == 201
        print(f"Mise à jour creation status: {resp.json['summary']['status']}")

        # Check source form restitution AFTER retraits
        resp_after = admin_client.get(f"/api/forms/{source_form_id}")
        restitution_after = resp_after.json["data"].get("restitution", {})
        print(f"Source restitution AFTER: {restitution_after}")

        # Verify retraits were applied
        items = restitution_after.get("items", {})
        assert len(items) > 0, f"Expected items in restitution, got empty: {items}"
        assert "ordinateur" in items, f"Expected ordinateur in items: {items}"
