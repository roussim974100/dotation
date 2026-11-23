"""Vérifie le VRAI système de permissions (backend/app.py:DEFAULT_GROUPS, celui réellement utilisé au démarrage),
pas une copie orpheline. L'ancien backend/permissions.py définissait son propre DEFAULT_GROUPS, déconnecté de celui-ci
(déjà périmé : il lui manquait forms.restitution_force) ; ses 6 tests passaient indéfiniment sans aucun rapport avec
le système réellement exposé aux utilisateurs. Supprimé le 22/11/2026 (audit de pérennité, recommandation R1) : ce
fichier teste maintenant directement app.py:DEFAULT_GROUPS, et la cohérence TOGGLEABLE_PERMISSIONS (routes/admin.py)
/ PERMISSION_INFO (frontend/js/admin.js) — même principe que test_version_consistency.py."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
backend_path = str(ROOT / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import DEFAULT_GROUPS
from routes.admin import TOGGLEABLE_PERMISSIONS


def _group_perms(key):
    return next(perms for group_key, _label, _desc, perms, _scope in DEFAULT_GROUPS if group_key == key)


def test_redaction_group_cannot_see_other_services_dossiers():
    """Confidentialité entre services : redaction ne doit voir que les dossiers de son propre service."""
    perms = _group_perms("redaction")
    assert "forms.view_all" not in perms
    assert "forms.read_list" in perms
    assert "forms.create" in perms


def test_lecture_group_is_read_only():
    perms = set(_group_perms("lecture"))
    assert {"forms.read_list", "forms.read_detail", "forms.export"} <= perms
    assert not {"forms.create", "forms.edit", "forms.delete"} & perms


def test_admin_group_has_every_toggleable_permission():
    perms = set(_group_perms("admin"))
    assert TOGGLEABLE_PERMISSIONS <= perms, f"admin devrait porter tous les droits cochables, manque : {TOGGLEABLE_PERMISSIONS - perms}"


def test_every_group_permission_is_a_known_toggleable_permission():
    """Un groupe qui porte un droit absent de TOGGLEABLE_PERMISSIONS ne pourrait jamais être retiré/réattribué
    depuis Admin > Comptes : signe d'un droit ajouté à DEFAULT_GROUPS sans être rendu éditable."""
    for key, _label, _desc, perms, _scope in DEFAULT_GROUPS:
        unknown = set(perms) - TOGGLEABLE_PERMISSIONS - {"*"}
        assert not unknown, f"Le groupe {key} porte un droit absent de TOGGLEABLE_PERMISSIONS : {unknown}"


def test_permission_info_matches_toggleable_permissions():
    """TOGGLEABLE_PERMISSIONS (backend/routes/admin.py, les droits cochables dans Admin > Comptes) et
    PERMISSION_INFO (frontend/js/admin.js, les libellés affichés) sont deux copies à la main de la même liste :
    un droit ajouté à l'une et oublié dans l'autre reste invisible (sans libellé) ou incochable, en silence
    (constat de l'audit de pérennité du 22/11/2026)."""
    admin_js = (ROOT / "frontend" / "js" / "admin.js").read_text(encoding="utf-8")
    match = re.search(r"const PERMISSION_INFO = \[(.*?)\];", admin_js, re.DOTALL)
    assert match, "PERMISSION_INFO introuvable dans frontend/js/admin.js"
    displayed_keys = set(re.findall(r'key:\s*"([^"]+)"', match.group(1)))

    assert displayed_keys == TOGGLEABLE_PERMISSIONS, (
        "PERMISSION_INFO (frontend/js/admin.js) et TOGGLEABLE_PERMISSIONS (backend/routes/admin.py) ont divergé.\n"
        f"Dans PERMISSION_INFO mais pas TOGGLEABLE_PERMISSIONS : {displayed_keys - TOGGLEABLE_PERMISSIONS}\n"
        f"Dans TOGGLEABLE_PERMISSIONS mais pas PERMISSION_INFO : {TOGGLEABLE_PERMISSIONS - displayed_keys}"
    )
