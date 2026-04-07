"""Tests des paramètres applicatifs : lecture publique, email_domains, admin PUT."""


class TestPublicSettings:
    def test_accessible_sans_auth(self, client):
        r = client.get("/api/settings/public")
        assert r.status_code == 200

    def test_contient_champs_attendus(self, client):
        data = client.get("/api/settings/public").get_json()
        assert "orgName" in data
        assert "emailDomains" in data

    def test_email_domains_vide_par_defaut(self, client):
        data = client.get("/api/settings/public").get_json()
        assert data["emailDomains"] == []

    def test_email_domains_parse_apres_sauvegarde(self, admin_client):
        admin_client.put(
            "/api/admin/settings",
            json={"email_domains": "example.fr, agglo.fr"},
        )
        data = admin_client.get("/api/settings/public").get_json()
        assert data["emailDomains"] == ["example.fr", "agglo.fr"]

    def test_email_domains_un_seul(self, admin_client):
        admin_client.put("/api/admin/settings", json={"email_domains": "mairie.fr"})
        data = admin_client.get("/api/settings/public").get_json()
        assert data["emailDomains"] == ["mairie.fr"]


class TestAdminSettings:
    def test_get_settings_admin(self, admin_client):
        r = admin_client.get("/api/admin/settings")
        assert r.status_code == 200
        data = r.get_json()
        # La route admin retourne orgName au top-level et raw.org_name
        assert "orgName" in data
        assert "raw" in data
        assert "org_name" in data["raw"]

    def test_put_settings_met_a_jour(self, admin_client):
        admin_client.put("/api/admin/settings", json={"org_name": "Ville Test"})
        data = admin_client.get("/api/admin/settings").get_json()
        assert data["raw"]["org_name"] == "Ville Test"

    def test_put_settings_refuse_sans_auth(self, client):
        r = client.put("/api/admin/settings", json={"org_name": "Pirate"})
        assert r.status_code == 401
