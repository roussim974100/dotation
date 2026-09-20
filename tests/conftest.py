"""Isolation globale des tests : AUCUN test ne doit toucher aux vraies bases (backend/dotation.db, users.db).

Plusieurs tests importent l'application (`from app import app`), dont le demarrage cree / migre les bases. Sans ce fichier,
ils travaillaient sur la base de developpement de l'utilisateur. Les variables sont posees AVANT tout import de `config`.
"""
import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="aquai_tests_")
os.environ["APP_DATA_DIR"] = _DATA
os.environ["APP_CUSTOM_BRANDING_DIR"] = os.path.join(_DATA, "branding")
os.environ["APP_UPDATE_CHECK"] = "0"  # aucune requete reseau pendant les tests
