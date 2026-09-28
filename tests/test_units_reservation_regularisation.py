"""Bug constate en production : un objet restitue via un dossier de regularisation ("sortie", attribution
retrodatee) restait affiche "reserve" pour toujours, meme apres sa restitution, et n'etait donc jamais propose
pour une reattribution (available_units_for_resource / l'ecran "reattribuer a une autre personne").

Cause : le brouillon initial cree un evenement "reserve" date au moment REEL de sa creation. Un dossier de
regularisation retrodate ensuite son "assigned" a une date ANTERIEURE (la personne detenait deja l'objet avant
d'etre enregistree). derive_state() traite les evenements tries par date : l'"assigned" (plus ancien) passe
AVANT le "reserve" (plus recent) et ne peut donc pas le lever ; rien d'autre ne levait la reservation de ce
dossier ensuite, meme a la restitution. Corrige dans models/units.py (_FORM_RELATIONSHIP_SETTLED) : la
reservation d'un dossier est desormais levee des que celui-ci atteint N'IMPORTE QUEL evenement definitif
(attribue, restitue, perdu, transfere, mis au rebut, supprime), pas seulement "attribue"."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.units import derive_state, ensure_units_schema, sync_units_for_form

SCHEMA = [{"key": "numeroSerie", "label": "N° de série", "required": True, "identifier": True}, {"key": "marque", "label": "Marque"}]


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE dotation_forms (id TEXT PRIMARY KEY, status TEXT, dossier_type TEXT, nom TEXT, prenom TEXT, service TEXT,
            assigned_at TEXT, returned_at TEXT, updated_at TEXT);
        CREATE TABLE dotation_items (id INTEGER PRIMARY KEY AUTOINCREMENT, form_id TEXT, item_key TEXT, assigned INTEGER,
            returned_at TEXT, return_condition TEXT, details_json TEXT);
        CREATE TABLE resource_catalog (code TEXT, label TEXT, category TEXT, tracking_mode TEXT, field_schema_json TEXT);
    """)
    conn.execute("INSERT INTO resource_catalog VALUES ('ordinateur','Ordinateur','materiel','unit',?)", (json.dumps(SCHEMA),))
    conn.execute("INSERT INTO resource_catalog VALUES ('telephone','Téléphone','materiel','unit',?)", (json.dumps(SCHEMA),))
    ensure_units_schema(conn)
    return conn


def set_form(db, form_id, status, assigned, updated, returned=None, dossier_type="arrivee",
             nom="TORAMAN", prenom="Alicia", service="DRH"):
    existing = db.execute("SELECT 1 FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
    if existing:
        db.execute("UPDATE dotation_forms SET status=?, dossier_type=?, assigned_at=?, returned_at=?, updated_at=? WHERE id=?",
                   (status, dossier_type, assigned, returned, updated, form_id))
    else:
        db.execute("INSERT INTO dotation_forms (id,status,dossier_type,nom,prenom,service,assigned_at,returned_at,updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (form_id, status, dossier_type, nom, prenom, service, assigned, returned, updated))


def set_item(db, form_id, serial, condition="pending", returned_at=None, code="ordinateur"):
    db.execute("DELETE FROM dotation_items WHERE form_id = ? AND item_key = ?", (form_id, code))
    details = {"selected": True, "fields": {"numeroSerie": serial, "marque": "HP"}}
    db.execute("INSERT INTO dotation_items (form_id,item_key,assigned,returned_at,return_condition,details_json) VALUES (?,?,1,?,?,?)",
               (form_id, code, returned_at, condition, json.dumps(details)))


def unit_status(db, serial, code="ordinateur"):
    row = db.execute("SELECT status FROM resource_units WHERE resource_code = ? AND identifier_norm = ?", (code, serial.lower())).fetchone()
    return row["status"] if row else None


def event_types(db, serial, code="ordinateur"):
    unit_id = db.execute("SELECT id FROM resource_units WHERE resource_code = ? AND identifier_norm = ?", (code, serial.lower())).fetchone()["id"]
    return [r["event_type"] for r in db.execute(
        "SELECT event_type FROM resource_unit_events WHERE unit_id = ? ORDER BY occurred_at, seq", (unit_id,))]


def regularisation_return_becomes_available(db, serial, code, condition, expected_status):
    form_id = f"form_{serial}"
    # 1) Brouillon cree "aujourd'hui" (2026-09-20) : sync_units_for_form enregistre une simple reservation.
    set_item(db, form_id, serial, condition="pending", code=code)
    set_form(db, form_id, status="draft", assigned="2026-09-20", updated="2026-09-20T09:34:46", dossier_type="sortie")
    sync_units_for_form(db, form_id)
    assert event_types(db, serial, code) == ["reserved"]

    # 2) Regularisation signee : l'attribution reelle est RETRODATEE avant la reservation (la personne detenait
    #    deja l'objet), puis la restitution est enregistree.
    set_form(db, form_id, status="returned", assigned="2026-08-26T09:06", returned="2026-09-30",
              updated="2026-09-28T12:32:03", dossier_type="sortie")
    set_item(db, form_id, serial, condition=condition, returned_at="2026-09-30", code=code)
    sync_units_for_form(db, form_id)

    assert unit_status(db, serial, code) == expected_status, (
        f"l'objet {serial} restitue doit redevenir '{expected_status}', pas rester bloque 'reserve'"
    )


def test_regularisation_conforme_redevient_disponible(db):
    regularisation_return_becomes_available(db, "CZC2097Y6W", "ordinateur", "conforme", "in_stock")


def test_regularisation_degrade_redevient_disponible_degrade(db):
    regularisation_return_becomes_available(db, "SN-DEGRADE", "ordinateur", "degrade", "degraded")


def test_le_correctif_s_applique_a_une_autre_ressource_que_l_ordinateur(db):
    # Meme scenario, sur un telephone : le correctif est dans derive_state(), commun a toutes les ressources
    # suivies par objet, pas un correctif specifique au poste de travail.
    regularisation_return_becomes_available(db, "IMEI-000111222", "telephone", "conforme", "in_stock")


def test_reservation_normale_non_retrodatee_n_est_pas_affectee(db):
    # Garde-fou de non-regression : le cas courant (reservation avant attribution, dates dans l'ordre) doit
    # continuer a fonctionner exactement comme avant.
    form_id = "form_NORMAL"
    set_item(db, "form_NORMAL", "SN-NORMAL", condition="pending")
    set_form(db, form_id, status="draft", assigned="2026-01-10", updated="2026-01-10")
    sync_units_for_form(db, form_id)
    set_form(db, form_id, status="active", assigned="2026-01-12", updated="2026-01-12")
    set_item(db, form_id, "SN-NORMAL", condition="pending")
    sync_units_for_form(db, form_id)
    assert unit_status(db, "SN-NORMAL") == "assigned"
    set_form(db, form_id, status="returned", assigned="2026-01-12", returned="2026-01-20", updated="2026-01-20")
    set_item(db, form_id, "SN-NORMAL", condition="conforme", returned_at="2026-01-20")
    sync_units_for_form(db, form_id)
    assert unit_status(db, "SN-NORMAL") == "in_stock"


@pytest.mark.parametrize("closing_event", ["returned", "returned_degraded", "lost", "transferred", "retired"])
def test_derive_state_leve_la_reservation_du_meme_dossier_sur_tout_evenement_definitif(closing_event):
    # Test unitaire pur de derive_state() : la reservation du dossier F1, datee APRES son evenement d'ouverture
    # (attribution), doit etre levee des que ce meme dossier atteint un evenement definitif quelconque - pas
    # seulement "assigned" - sans quoi elle resterait pour toujours accrochee a l'unite.
    events = [
        {"event_type": "assigned", "form_id": "F1", "occurred_at": "2026-01-01", "holder_label": "F1"},
        {"event_type": "reserved", "form_id": "F1", "occurred_at": "2026-02-01", "holder_label": "F1"},
        {"event_type": closing_event, "form_id": "F1", "occurred_at": "2026-03-01", "holder_label": None},
    ]
    status, holder = derive_state(events)
    assert status != "reserved", f"une reservation du meme dossier ne doit pas survivre a un evenement '{closing_event}'"


def test_derive_state_conserve_la_reservation_d_un_autre_dossier(db):
    # Un dossier B qui reserve l'objet APRES que le dossier A l'ait rendu doit rester visible "reserve" : le
    # correctif ne doit lever que la reservation du MEME dossier que l'evenement definitif.
    events = [
        {"event_type": "assigned", "form_id": "A", "occurred_at": "2026-01-01", "holder_label": "A"},
        {"event_type": "returned", "form_id": "A", "occurred_at": "2026-01-10", "holder_label": None},
        {"event_type": "reserved", "form_id": "B", "occurred_at": "2026-01-11", "holder_label": "B"},
    ]
    status, holder = derive_state(events)
    assert status == "reserved" and holder["form_id"] == "B"
