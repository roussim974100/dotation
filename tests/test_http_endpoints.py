"""Tests HTTP d'integration sur une base TEMPORAIRE (sous-processus + APP_DATA_DIR) : couvre les endpoints qui n'avaient
aucun test (logo, journaux, statistiques, exports, PDF par lots, stocks, parc...) et verifie qu'aucun endpoint prive
ne repond a un visiteur anonyme."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def http(tmp_path_factory):
    data = tmp_path_factory.mktemp("aquai_http")
    env = dict(os.environ, APP_DATA_DIR=str(data), APP_CUSTOM_BRANDING_DIR=str(data / "branding"), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "tests" / "_http_scenarios.py")], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, (result.stderr or result.stdout)[-1500:]
    line = next(line for line in result.stdout.splitlines() if line.startswith("JSON>>"))
    return json.loads(line[len("JSON>>"):])


def test_no_private_endpoint_answers_an_anonymous_visitor(http):
    assert http["anonymous_leaks"] == []


def test_admin_get_endpoints_never_crash(http):
    assert http["admin_get_errors"] == []
    assert http["admin_get_checked"] >= 30  # le parcours couvre bien tous les GET sans parametre


def test_logo_upload_validation(http):
    assert http["logo_valid"] in (200, 201)
    assert http["logo_bad_extension"] == 400
    assert http["logo_bad_magic"] == 400
    assert http["logo_too_large"] in (400, 413)
    assert http["logo_missing"] == 400


@pytest.mark.parametrize("name", [
    "trash", "logs", "unc_stats", "services_csv_template", "services_export_csv", "forms_export", "forms_export_unc",
    "catalog_quality", "stock", "units", "units_stats", "dashboard_stats", "backup_info", "groups", "session",
])
def test_admin_read_endpoints_answer_200(http, name):
    assert http[name] == 200


def test_catalog_quality_and_csv_shapes(http):
    assert http["catalog_quality_has_total"] is True
    assert http["services_csv_is_text"] is True


def test_pdf_endpoints_refuse_bad_input_without_crashing(http):
    assert 400 <= http["pdf_batch_empty"] < 500
    assert 400 <= http["restitution_pdf_batch_empty"] < 500
    assert http["restitution_pdf_unknown"] == 404
    assert http["pdf_unknown"] == 404


def test_stock_and_parc_actions_on_unknown_objects(http):
    assert http["stock_unknown_resource"] == [400, "not_quantity_resource"]
    assert http["unit_action_unknown"] in (400, 404)


def test_logo_url_with_file_scheme_is_never_stored(http):
    assert not http["logo_url_file_scheme_stored"]


def test_login_rate_limit_ignores_a_forged_forwarded_for_header(http):
    """10 tentatives passent, la 11e est refusee, alors que chacune annonce une IP differente dans X-Forwarded-For."""
    assert http["login_rate_limited_at_attempt"] == 11


def test_a_fresh_install_gives_the_admin_group_the_parc_manage_right(http):
    """Regression : sur une installation neuve, l'administrateur doit pouvoir gerer le parc et les stocks des le depart."""
    assert http["admin_has_parc_manage"] is True
