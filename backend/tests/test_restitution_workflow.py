"""Tests exhaustifs du cycle de restitution et de compute_effective_workflow_status.

Scénarios couverts :
  1.  keepPending=True  + items tous conforme      → partial_return, pendingFinalization=True
  2.  keepPending=True  + items avec non_restitue  → partial_return, pendingFinalization=True
  3.  keepPending=True  + aucun item               → partial_return, pendingFinalization=True
  4.  keepPending=False + items tous conforme      → returned,       pendingFinalization=False
  5.  keepPending=False + items avec non_restitue  → partial_return, pendingFinalization=False
  6.  keepPending=False + deferred + tous conforme → awaiting_signature, pendingFinalization=False
  7.  keepPending=False + deferred + non_restitue  → partial_return, pendingFinalization=False
  8.  keepPending=False + impossible + tous conf.  → returned,       pendingFinalization=False
  9.  keepPending=True  puis keepPending=False     → returned,       pendingFinalization=False
  10. signatureDataUrl présent + tous conforme     → returned  (signature fournie)
  11. GET /api/forms (liste) reflète le bon statut effectif
  12. Accès sans permission → 403
"""

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BENE = {"nom": "Martin", "prenom": "Alice"}

_ITEM_CONFORME = {
    "state": "conforme",
    "returned": True,
    "returnedAt": "2026-04-21",
    "condition": "conforme",
    "notes": "",
}
_ITEM_DEGRADE = {
    "state": "returned_damaged",
    "returned": True,
    "returnedAt": "2026-04-21",
    "condition": "degrade",
    "notes": "",
}
_ITEM_NON_RESTITUE = {
    "state": "non_restitue",
    "returned": False,
    "returnedAt": "",
    "condition": "",
    "notes": "",
}


def _create_active_form(client):
    """Crée un dossier et le force en statut active (signé + rgpd)."""
    r = client.post(
        "/api/forms",
        json={
            "beneficiaire": _BENE,
            "workflow": {"status": "active"},
            "validation": {"signatureDataUrl": "data:image/png;base64,AA==", "rgpdAccepted": True},
            "meta": {"lockedAt": "2026-01-01T00:00:00Z"},
        },
    )
    assert r.status_code == 201
    return r.get_json()["summary"]["id"]


def _patch_restitution(client, form_id, items, *, keep_pending=False,
                       signature_status="", signature_data=""):
    return client.patch(
        f"/api/forms/{form_id}/restitution",
        json={
            "returnedAt": "2026-04-21",
            "reason": "depart",
            "notes": "",
            "items": items,
            "signatureStatus": signature_status,
            "signatureDataUrl": signature_data,
            "keepPending": keep_pending,
        },
    )


def _summary(client, form_id):
    r = client.get(f"/api/forms/{form_id}")
    assert r.status_code == 200
    return r.get_json()["summary"]


def _restitution_data(client, form_id):
    r = client.get(f"/api/forms/{form_id}")
    return r.get_json()["data"].get("restitution", {})


# ---------------------------------------------------------------------------
# Scénario 1 – keepPending + tous conforme → partial_return préservé
# ---------------------------------------------------------------------------

class TestKeepPendingAllConforme:
    def test_status_is_partial_return(self, admin_client):
        fid = _create_active_form(admin_client)
        r = _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME},
            keep_pending=True,
        )
        assert r.status_code == 200
        assert _summary(admin_client, fid)["status"] == "partial_return"

    def test_pending_finalization_flag_true(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        assert _restitution_data(admin_client, fid)["pendingFinalization"] is True

    def test_summary_pending_finalization_true(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        assert _summary(admin_client, fid)["pendingFinalization"] is True


# ---------------------------------------------------------------------------
# Scénario 2 – keepPending + non_restitue → partial_return
# ---------------------------------------------------------------------------

class TestKeepPendingWithNonRestitue:
    def test_status_is_partial_return(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "pc": _ITEM_NON_RESTITUE},
            keep_pending=True,
        )
        assert _summary(admin_client, fid)["status"] == "partial_return"

    def test_pending_finalization_true(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "pc": _ITEM_NON_RESTITUE},
            keep_pending=True,
        )
        assert _restitution_data(admin_client, fid)["pendingFinalization"] is True


# ---------------------------------------------------------------------------
# Scénario 3 – keepPending + aucun item → partial_return
# ---------------------------------------------------------------------------

class TestKeepPendingNoItems:
    def test_status_is_partial_return(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {}, keep_pending=True)
        assert _summary(admin_client, fid)["status"] == "partial_return"

    def test_pending_finalization_true(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {}, keep_pending=True)
        assert _restitution_data(admin_client, fid)["pendingFinalization"] is True


# ---------------------------------------------------------------------------
# Scénario 4 – keepPending=False + tous conforme → returned
# ---------------------------------------------------------------------------

class TestFinalizeAllConforme:
    def test_status_is_returned(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert _summary(admin_client, fid)["status"] == "returned"

    def test_pending_finalization_false(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert _restitution_data(admin_client, fid).get("pendingFinalization") is False

    def test_degrade_item_also_returned(self, admin_client):
        """Un item dégradé compte comme restitué → returned."""
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "badge": _ITEM_DEGRADE},
            keep_pending=False,
        )
        assert _summary(admin_client, fid)["status"] == "returned"


# ---------------------------------------------------------------------------
# Scénario 5 – keepPending=False + non_restitue → partial_return
# ---------------------------------------------------------------------------

class TestFinalizeWithNonRestitue:
    def test_status_is_partial_return(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "pc": _ITEM_NON_RESTITUE},
            keep_pending=False,
        )
        assert _summary(admin_client, fid)["status"] == "partial_return"

    def test_pending_finalization_false(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "pc": _ITEM_NON_RESTITUE},
            keep_pending=False,
        )
        assert _restitution_data(admin_client, fid).get("pendingFinalization") is False


# ---------------------------------------------------------------------------
# Scénario 6 – deferred + tous conforme → awaiting_signature
# ---------------------------------------------------------------------------

class TestDeferredAllConforme:
    def test_status_is_awaiting_signature(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME},
            keep_pending=False,
            signature_status="deferred",
        )
        assert _summary(admin_client, fid)["status"] == "awaiting_signature"

    def test_pending_finalization_false(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid, {"tel": _ITEM_CONFORME},
            keep_pending=False, signature_status="deferred",
        )
        assert _restitution_data(admin_client, fid).get("pendingFinalization") is False


# ---------------------------------------------------------------------------
# Scénario 7 – deferred + non_restitue → partial_return (deferred inopérant)
# ---------------------------------------------------------------------------

class TestDeferredWithNonRestitue:
    def test_status_is_partial_return(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME, "pc": _ITEM_NON_RESTITUE},
            keep_pending=False,
            signature_status="deferred",
        )
        assert _summary(admin_client, fid)["status"] == "partial_return"


# ---------------------------------------------------------------------------
# Scénario 8 – impossible + tous conforme → returned
# ---------------------------------------------------------------------------

class TestImpossibleAllConforme:
    def test_status_is_returned(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME},
            keep_pending=False,
            signature_status="impossible",
        )
        assert _summary(admin_client, fid)["status"] == "returned"


# ---------------------------------------------------------------------------
# Scénario 9 – keepPending=True puis keepPending=False → returned, flag effacé
# ---------------------------------------------------------------------------

class TestKeepPendingThenFinalize:
    def test_status_switches_to_returned(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        assert _summary(admin_client, fid)["status"] == "partial_return"

        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert _summary(admin_client, fid)["status"] == "returned"

    def test_pending_finalization_cleared(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert _restitution_data(admin_client, fid).get("pendingFinalization") is False

    def test_summary_pending_finalization_false(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert _summary(admin_client, fid)["pendingFinalization"] is False


# ---------------------------------------------------------------------------
# Scénario 10 – signatureDataUrl fourni + tous conforme → returned
# ---------------------------------------------------------------------------

class TestSignatureDataUrlPresent:
    def test_status_is_returned_when_signed(self, admin_client):
        """Une signature de restitution fournie directement → returned."""
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME},
            keep_pending=False,
            signature_status="deferred",
            signature_data="data:image/png;base64,AA==",
        )
        assert _summary(admin_client, fid)["status"] == "returned"

    def test_pending_finalization_false_when_signed(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid,
            {"tel": _ITEM_CONFORME},
            keep_pending=False,
            signature_status="deferred",
            signature_data="data:image/png;base64,AA==",
        )
        assert _restitution_data(admin_client, fid).get("pendingFinalization") is False


# ---------------------------------------------------------------------------
# Scénario 11 – GET /api/forms (liste) reflète le bon statut effectif
# ---------------------------------------------------------------------------

class TestDashboardListStatuses:
    def test_list_shows_partial_return_for_keep_pending(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=True)
        r = admin_client.get("/api/forms")
        assert r.status_code == 200
        forms = r.get_json()  # liste directe
        match = next((f for f in forms if f["id"] == fid), None)
        assert match is not None
        assert match["status"] == "partial_return"

    def test_list_shows_returned_after_finalize(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(admin_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        r = admin_client.get("/api/forms")
        forms = r.get_json()
        match = next(f for f in forms if f["id"] == fid)
        assert match["status"] == "returned"

    def test_list_shows_awaiting_signature_when_deferred(self, admin_client):
        fid = _create_active_form(admin_client)
        _patch_restitution(
            admin_client, fid, {"tel": _ITEM_CONFORME},
            keep_pending=False, signature_status="deferred",
        )
        r = admin_client.get("/api/forms")
        forms = r.get_json()
        match = next(f for f in forms if f["id"] == fid)
        assert match["status"] == "awaiting_signature"


# ---------------------------------------------------------------------------
# Scénario 12 – Permission
# ---------------------------------------------------------------------------

class TestRestitutionPermission:
    def test_requires_auth(self, client, app):
        with app.test_request_context():
            pass
        c = app.test_client()
        r = c.patch(
            "/api/forms/some-id/restitution",
            json={"returnedAt": "2026-04-21", "items": {}},
            headers={"X-CSRF-Token": c.get("/api/csrf-token").get_json()["token"]},
        )
        assert r.status_code == 401

    def test_requires_restitution_permission(self, redac_client, admin_client):
        fid = _create_active_form(admin_client)
        r = _patch_restitution(redac_client, fid, {"tel": _ITEM_CONFORME}, keep_pending=False)
        assert r.status_code == 403
