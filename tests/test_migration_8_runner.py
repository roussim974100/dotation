"""3.66.1 : la migration 8 doit s'executer AVEC le lanceur reel (run_pending_migrations) et rattraper, sur une base
existante, les unites restees bloquees "reservees" par le bug corrige dans models/units.py (derive_state) - voir
tests/test_units_reservation_regularisation.py pour le detail du bug. Verifie ici de bout en bout, via l'API reelle
(/api/catalog/available/<id>), qu'un objet restitue par une regularisation redevient proposable a la reattribution
apres la migration, sans avoir a resauvegarder le dossier concerne."""
import json
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
from database import get_db
from migrations import run_pending_migrations
from models.units import ensure_units_schema

H = {"X-CSRF-Token": "jeton"}
SERIAL = "CZC2097Y6W"
SCHEMA = [{"key": "numeroSerie", "label": "N° de série", "required": True, "identifier": True}, {"key": "marque", "label": "Marque"}]


def _client():
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = "admin"
        flask_session["csrf_token"] = "jeton"
    return client


def _resource_catalog_id(connection):
    row = connection.execute("SELECT id FROM resource_catalog WHERE code = 'ordinateur'").fetchone()
    if row:
        return row["id"]
    connection.execute(
        "INSERT INTO resource_catalog (code, label, category, tracking_mode, field_schema_json, is_active) "
        "VALUES ('ordinateur', 'Ordinateur', 'materiel', 'unit', ?, 1)",
        (json.dumps(SCHEMA),),
    )
    connection.commit()
    return connection.execute("SELECT id FROM resource_catalog WHERE code = 'ordinateur'").fetchone()["id"]


def test_migration_8_rattrape_une_reservation_bloquee_par_une_regularisation():
    client = _client()
    form_id = "form_regularisation_test"

    with get_db() as connection:
        ensure_units_schema(connection)
        resource_id = _resource_catalog_id(connection)

        # Etat tel que laisse par le code D'AVANT LE CORRECTIF sur une vraie regularisation (voir constat en
        # production) : les 3 evenements reels (attribution retrodatee, reservation du brouillon initial, puis
        # restitution), et le statut "reserved" que l'ancien derive_state() calculait et laissait fige pour
        # toujours. La migration doit rejouer EXACTEMENT ces evenements deja enregistres, pas en creer de nouveaux.
        connection.execute(
            "INSERT INTO dotation_forms (id, dossier_id, title, status, dossier_type, nom, prenom, service, "
            "payload_json, assigned_at, returned_at, updated_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (form_id, "dossier_" + form_id, "TORAMAN Alicia", "returned", "sortie", "TORAMAN", "Alicia", "DRH", "{}",
             "2026-08-26T09:06", "2026-09-30", "2026-09-28T12:32:03", "2026-09-20T09:34:46"),
        )
        connection.commit()

        unit_id = "unit_test_" + SERIAL
        connection.execute(
            "INSERT INTO resource_units (id, resource_code, identifier, identifier_norm, status, holder_form_id, "
            "holder_label, fields_json, origin, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (unit_id, "ordinateur", SERIAL, SERIAL.lower(), "reserved", form_id, "TORAMAN Alicia · DRH",
             json.dumps({"numeroSerie": SERIAL, "marque": "HP"}), "regularisation",
             "2026-09-20T09:34:46", "2026-09-28T12:32:03"),
        )
        for event_type, occurred_at, condition, dedupe in (
            ("assigned", "2026-08-26T09:06", None, "assign"),
            ("reserved", "2026-09-20T09:34:46.703205+00:00", None, "reserve:0"),
            ("returned", "2026-09-30T00:00:00", "conforme", "returned"),
        ):
            connection.execute(
                "INSERT INTO resource_unit_events (unit_id, event_type, occurred_at, form_id, holder_label, "
                "condition, source, dedupe_key, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (unit_id, event_type, occurred_at, form_id, "TORAMAN Alicia · DRH", condition, "dossier",
                 f"{unit_id}:{dedupe}:{form_id}", "2026-09-20T09:34:46"),
            )
        connection.commit()

        stuck_status = connection.execute("SELECT status FROM resource_units WHERE id = ?", (unit_id,)).fetchone()["status"]
        assert stuck_status == "reserved", "le scenario doit d'abord reproduire le bug (objet bloque 'reserve')"

    # L'API de reattribution ne doit encore rien proposer : c'est le symptome signale par l'utilisateur.
    before = client.get(f"/api/catalog/available/{resource_id}")
    assert before.get_json()["items"] == []

    # 3) Migration 8 : rejoue le calcul de statut de chaque unite a partir de ses evenements deja enregistres.
    with get_db() as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 8")
        connection.commit()
    with get_db() as connection:
        applied = run_pending_migrations(connection)  # ne doit ni lever, ni etre annulee
        connection.commit()
    assert 8 in applied

    with get_db() as connection:
        fixed_status = connection.execute(
            "SELECT status FROM resource_units WHERE resource_code = 'ordinateur' AND identifier_norm = ?", (SERIAL.lower(),)
        ).fetchone()["status"]
    assert fixed_status == "in_stock"

    # L'API propose maintenant l'objet pour une reattribution (le cas concret signale : reattribuer a Lilou).
    after = client.get(f"/api/catalog/available/{resource_id}")
    identifiers = [item["identifier"] for item in after.get_json()["items"]]
    assert SERIAL in identifiers
