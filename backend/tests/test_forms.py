"""Tests CRUD des dossiers."""


_MINIMAL = {"beneficiaire": {"nom": "Dupont", "prenom": "Jean"}}
_FULL = {
    "beneficiaire": {"nom": "Martin", "prenom": "Alice", "service": "DSI"},
    "immateriel": {
        "email": {"selected": True, "adresse": "alice.martin@ville-publier.fr"},
    },
}


def _extract_id(response):
    """Extrait l'id depuis la réponse de persist_form (structure imbriquée)."""
    data = response.get_json()
    return data["summary"]["id"]


class TestListForms:
    def test_liste_vide_par_defaut(self, admin_client):
        r = admin_client.get("/api/forms")
        assert r.status_code == 200
        assert r.get_json() == []

    def test_liste_apres_creation(self, admin_client):
        admin_client.post("/api/forms", json=_MINIMAL)
        r = admin_client.get("/api/forms")
        assert len(r.get_json()) == 1


class TestCreateForm:
    def test_creation_minimale(self, admin_client):
        r = admin_client.post("/api/forms", json=_MINIMAL)
        assert r.status_code == 201
        data = r.get_json()
        assert "summary" in data
        assert data["summary"]["nom"] == "Dupont"
        assert "id" in data["summary"]

    def test_creation_sans_nom_rejete(self, admin_client):
        r = admin_client.post("/api/forms", json={"beneficiaire": {"prenom": "Jean"}})
        assert r.status_code == 400

    def test_creation_sans_prenom_rejete(self, admin_client):
        r = admin_client.post("/api/forms", json={"beneficiaire": {"nom": "Dupont"}})
        assert r.status_code == 400

    def test_creation_requiert_auth(self, client):
        r = client.post("/api/forms", json=_MINIMAL)
        assert r.status_code == 401

    def test_creation_requiert_permission(self, redac_client):
        # redac a forms.create → doit fonctionner
        r = redac_client.post("/api/forms", json=_MINIMAL)
        assert r.status_code == 201


class TestGetForm:
    def test_lecture_existant(self, admin_client):
        form_id = _extract_id(admin_client.post("/api/forms", json=_MINIMAL))
        r = admin_client.get(f"/api/forms/{form_id}")
        assert r.status_code == 200
        assert r.get_json()["summary"]["id"] == form_id

    def test_lecture_inexistant(self, admin_client):
        r = admin_client.get("/api/forms/inexistant-id")
        assert r.status_code == 404


class TestDeleteForm:
    def test_suppression_admin(self, admin_client):
        form_id = _extract_id(admin_client.post("/api/forms", json=_MINIMAL))
        r = admin_client.delete(f"/api/forms/{form_id}")
        assert r.status_code == 200
        assert admin_client.get(f"/api/forms/{form_id}").status_code == 404

    def test_suppression_refusee_redac(self, admin_client, redac_client):
        form_id = _extract_id(admin_client.post("/api/forms", json=_MINIMAL))
        r = redac_client.delete(f"/api/forms/{form_id}")
        assert r.status_code == 403


class TestUncAccesCount:
    """Vérifie que uncAccesCount apparaît dans la liste des dossiers."""

    def test_dossier_sans_unc(self, admin_client):
        admin_client.post("/api/forms", json=_MINIMAL)
        items = admin_client.get("/api/forms").get_json()
        assert items[0]["uncAccesCount"] == 0

    def test_dossier_avec_unc(self, admin_client):
        payload = {
            **_MINIMAL,
            "unc_acces": [
                {"chemin": "\\\\SRV\\partage", "acces": "lecture", "statut": "demande", "commentaire": ""},
                {"chemin": "\\\\SRV\\data", "acces": "lecture_ecriture", "statut": "provisionne", "commentaire": "ok"},
            ],
        }
        admin_client.post("/api/forms", json=payload)
        items = admin_client.get("/api/forms").get_json()
        assert items[0]["uncAccesCount"] == 2
