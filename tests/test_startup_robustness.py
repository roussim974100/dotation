"""Démarrage insensible aux données : une donnée abîmée ou atypique n'empêche jamais l'application de démarrer ;
une base plus récente que le code est refusée avec un message clair (au lieu d'être abîmée)."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _run(data_dir, code="import app; print('DEMARRE')"):
    env = dict(os.environ, APP_UPDATE_CHECK="0", APP_DATA_DIR=str(data_dir), APP_HEALTH_INTERVAL_HOURS="0", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT / "backend"), env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_donnees_abimees_n_empechent_pas_le_demarrage(tmp_path):
    first = _run(tmp_path)
    assert "DEMARRE" in first.stdout, first.stderr[-800:]

    db = sqlite3.connect(tmp_path / "dotation.db")
    now = "2026-01-01T00:00:00.000Z"
    cols = [r[1] for r in db.execute("PRAGMA table_info(dotation_forms)").fetchall()]
    row = {"id": "abime", "dossier_id": None, "dossier_type": "arrivee", "title": "ABIME", "status": "draft", "beneficiary_type": "agent", "nom": "A", "prenom": "B",
           "service": "", "fonction": "", "mandat": "", "rgpd_accepted": 0, "signature_data": "", "assigned_at": now, "returned_at": None, "return_reason": None,
           "return_notes": None, "source_form_id": None, "payload_json": "{ceci n'est pas du json", "created_at": now, "updated_at": now}
    values = {k: v for k, v in row.items() if k in cols}
    db.execute(f"INSERT INTO dotation_forms ({','.join(values)}) VALUES ({','.join('?' * len(values))})", list(values.values()))
    db.execute("INSERT INTO dotation_forms (id, title, status, nom, prenom, payload_json, created_at, updated_at) VALUES ('liste', 'L', 'draft', 'A', 'B', '[1,2]', ?, ?)", (now, now))
    db.execute("UPDATE resource_catalog SET field_schema_json = 'null' WHERE code = 'ordinateur'")
    db.execute("UPDATE resource_catalog SET field_schema_json = '{\"pas\": \"une liste\"}' WHERE code = 'ecran'")
    db.execute("DELETE FROM schema_migrations")  # les migrations sont rejouees sur ces schemas atypiques
    db.commit()
    db.close()
    users = sqlite3.connect(tmp_path / "users.db")
    users.execute("UPDATE groups SET permissions_json = 'illisible' WHERE key = 'admin'")
    users.commit()
    users.close()

    second = _run(tmp_path)
    assert "DEMARRE" in second.stdout, second.stderr[-1200:]


def test_base_plus_recente_que_le_code_est_refusee_avec_un_message_clair(tmp_path):
    assert "DEMARRE" in _run(tmp_path).stdout
    db = sqlite3.connect(tmp_path / "dotation.db")
    db.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (999, 'du_futur', '2099-01-01')")
    db.commit()
    db.close()
    result = _run(tmp_path)
    assert "DEMARRE" not in result.stdout
    assert "plus recente" in result.stderr


def test_quantites_illisibles_ne_levent_jamais_d_erreur():
    sys.path.insert(0, str(ROOT / "backend"))
    from models.stock import MAX_QUANTITY, _as_quantity
    assert _as_quantity("inf") == 1 and _as_quantity("nan") == 1 and _as_quantity("1e999") == 1 and _as_quantity("abc") == 1
    assert _as_quantity("5") == 5 and _as_quantity("2,5") == 2 and _as_quantity(0) == 1 and _as_quantity(-3) == 1
    assert _as_quantity("1e30") == MAX_QUANTITY


def test_schemas_hostiles_normalises_sans_erreur_ni_champ_perdu():
    sys.path.insert(0, str(ROOT / "backend"))
    from models.workflow import MAX_FIELDS_PER_RESOURCE, normalize_resource_field_schema
    assert normalize_resource_field_schema(None) == [] and normalize_resource_field_schema({"a": 1}) == [] and normalize_resource_field_schema("x") == []
    out = normalize_resource_field_schema([{"label": "Номер серии"}, {"label": "序列号"}, {"label": "😀"}, "pas un dict", {"label": "Normal"}])
    assert [f["key"] for f in out] == ["champ_1", "champ_2", "champ_3", "normal"]  # libelles non latins conserves (avant : supprimes en silence)
    many = normalize_resource_field_schema([{"label": f"Champ {i}"} for i in range(500)])
    assert len(many) == MAX_FIELDS_PER_RESOURCE
    assert len(normalize_resource_field_schema([{"label": "x" * 1000}])[0]["label"]) == 120
    assert normalize_resource_field_schema([{"label": "S", "type": "select", "options": ["a", "a", "b"]}])[0]["options"] == ["a", "b"]
