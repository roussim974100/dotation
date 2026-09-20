"""Environnement de l'instance (dev / preprod / prod) : fichier > APP_ENVIRONMENT > suffixe de version > prod."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import environment  # noqa: E402


def _isolate(monkeypatch, tmp_path, file_content=None, env=None):
    path = tmp_path / "environment"
    if file_content is not None:
        path.write_text(file_content, encoding="utf-8")
    monkeypatch.setattr(environment, "ENV_FILE", str(path))
    monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
    if env:
        monkeypatch.setenv("APP_ENVIRONMENT", env)


def test_defaut_prod(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert environment.resolve_environment("3.49.0") == "prod"
    assert environment.display_version("3.49.0") == "3.49.0-prod"


def test_fichier_prioritaire(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, file_content="preprod\n", env="dev")
    assert environment.resolve_environment("3.49.0-dev") == "preprod"
    assert environment.display_version("3.49.0") == "3.49.0-preprod"


def test_variable_puis_suffixe(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, env="dev")
    assert environment.resolve_environment("3.49.0") == "dev"
    _isolate(monkeypatch, tmp_path)
    assert environment.resolve_environment("3.18.5-preprod") == "preprod"


def test_valeur_invalide_ignoree(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, file_content="n'importe quoi", env="staging")
    assert environment.resolve_environment("3.49.0") == "prod"


def test_version_de_branding_sans_suffixe():
    assert "-" not in environment.raw_version()
