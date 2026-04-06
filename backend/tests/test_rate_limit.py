"""Tests du rate limiting sur le login : blocage apres 10 tentatives."""

import pytest


class TestRateLimit:
    def _bad_login(self, client):
        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        return client.post(
            "/login",
            data={"username": "testadmin", "password": "wrong!", "csrf_token": token},
            follow_redirects=False,
        )

    def test_rate_limit_after_10_attempts(self, client):
        """Apres 10 echecs, la 11e tentative renvoie rate_limited."""
        for _ in range(10):
            r = self._bad_login(client)
            assert "error=invalid" in r.location

        r = self._bad_login(client)
        assert "error=rate_limited" in r.location

    def test_rate_limit_blocks_valid_credentials_too(self, client):
        """Meme des credentials corrects sont refuses apres rate limit."""
        for _ in range(10):
            self._bad_login(client)

        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "Admin1234!", "csrf_token": token},
            follow_redirects=False,
        )
        assert "error=rate_limited" in r.location

    def test_under_limit_still_works(self, client):
        """9 echecs ne declenchent pas le blocage."""
        for _ in range(9):
            self._bad_login(client)

        r = client.get("/api/csrf-token")
        token = r.get_json()["token"]
        r = client.post(
            "/login",
            data={"username": "testadmin", "password": "Admin1234!", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.location in ("/", "http://localhost/")
