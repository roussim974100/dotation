"""Isolation globale des tests : AUCUN test ne doit toucher aux vraies bases (backend/dotation.db, users.db).

Plusieurs tests importent l'application (`from app import app`), dont le demarrage cree / migre les bases. Sans ce fichier,
ils travaillaient sur la base de developpement de l'utilisateur. Les variables sont posees AVANT tout import de `config`.
"""
import os
import sys
import tempfile
from pathlib import Path

_DATA = tempfile.mkdtemp(prefix="aquai_tests_")
os.environ["APP_DATA_DIR"] = _DATA
os.environ["APP_CUSTOM_BRANDING_DIR"] = os.path.join(_DATA, "branding")
os.environ["APP_UPDATE_CHECK"] = "0"  # aucune requete reseau pendant les tests

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

import _stamped_client  # noqa: E402
from app import app  # noqa: E402

_stamped_client.install(app)
_stamped_client.release_default_admin()  # sessions posees a la main = sessions valides (voir _stamped_client.py)
