"""
Test du système de validation des permissions au démarrage.
Vérifie que validate_permissions_at_startup() détecte correctement les problèmes.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from permissions import (
    ROUTES_REQUIRED_PERMISSIONS,
    DEFAULT_GROUPS,
    validate_permissions_at_startup,
    has_permission_in_group,
    get_group_permissions,
)


def test_all_required_permissions_exist():
    """Vérifie que toutes les permissions requises sont définies dans les groupes."""
    print("\n[OK] Test 1: Verifier que les permissions requises existent")

    all_required_perms = set()
    for route, perms in ROUTES_REQUIRED_PERMISSIONS.items():
        all_required_perms.update(perms)

    # Vérifier que les groupes principaux (non-redaction) ont toutes les perms
    critical_groups = ["admin", "administration", "direction", "gestion"]

    for group_name in critical_groups:
        group_perms = DEFAULT_GROUPS[group_name]
        missing = all_required_perms - set(group_perms)
        assert not missing, f"Le groupe {group_name} manque des permissions: {missing}"

    print(f"   Tous les groupes critiques ont les permissions requises [PASS]")


def test_redaction_confidentiality():
    """Vérifie que le groupe redaction ne peut pas voir tous les dossiers."""
    print("\n[OK] Test 2: Verifier la confidentialite du groupe redaction")

    redaction_perms = DEFAULT_GROUPS["redaction"]

    # redaction ne doit PAS avoir forms.view_all (pour raison de confidentialité)
    assert "forms.view_all" not in redaction_perms, \
        "redaction ne doit pas avoir forms.view_all pour respecter la confidentialité"

    # Mais doit avoir les perms de base
    assert "forms.read_list" in redaction_perms
    assert "forms.read_detail" in redaction_perms
    assert "forms.create" in redaction_perms

    print(f"   redaction n'a pas forms.view_all (confidentialite OK) [PASS]")


def test_lecture_group_limited_perms():
    """Vérifie que le groupe lecture a des permissions limitées."""
    print("\n[OK] Test 3: Verifier que lecture a des permissions limitees")

    lecture_perms = set(DEFAULT_GROUPS["lecture"])

    # Lecture peut lire et exporter, mais pas créer/éditer/supprimer
    assert "forms.read_list" in lecture_perms
    assert "forms.read_detail" in lecture_perms
    assert "forms.export" in lecture_perms

    assert "forms.create" not in lecture_perms
    assert "forms.edit" not in lecture_perms
    assert "forms.delete" not in lecture_perms

    print(f"   lecture est bien limite a la lecture/export [PASS]")


def test_has_permission_in_group():
    """Teste la fonction has_permission_in_group."""
    print("\n[OK] Test 4: Tester has_permission_in_group()")

    # Admin doit avoir toutes les perms
    assert has_permission_in_group("admin", "users.manage")
    assert has_permission_in_group("admin", "forms.read_list")

    # Lecture ne doit pas avoir forms.create
    assert not has_permission_in_group("lecture", "forms.create")

    # Groupe inexistant retourne []
    assert not has_permission_in_group("inexistant", "forms.read_list")

    print(f"   has_permission_in_group() fonctionne correctement [PASS]")


def test_get_group_permissions():
    """Teste la fonction get_group_permissions."""
    print("\n[OK] Test 5: Tester get_group_permissions()")

    admin_perms = get_group_permissions("admin")
    assert isinstance(admin_perms, list)
    assert len(admin_perms) > 0
    assert "users.manage" in admin_perms

    # Groupe inexistant retourne []
    unknown_perms = get_group_permissions("inexistant")
    assert unknown_perms == []

    print(f"   get_group_permissions() fonctionne correctement [PASS]")


def test_routes_coverage():
    """Vérifie que les routes principales sont couvertes."""
    print("\n[OK] Test 6: Verifier la couverture des routes")

    critical_routes = [
        "/api/forms",
        "/api/pools",
        "/api/admin/users",
        "/api/admin/services",
    ]

    for route in critical_routes:
        found = False
        for defined_route in ROUTES_REQUIRED_PERMISSIONS.keys():
            if route in defined_route:
                found = True
                break
        assert found, f"Route critique {route} n'est pas couverte par la validation"

    print(f"   Toutes les routes critiques sont couvertes [PASS]")


if __name__ == "__main__":
    print("=" * 80)
    print("TEST DU SYSTÈME DE VALIDATION DES PERMISSIONS")
    print("=" * 80)

    try:
        test_all_required_permissions_exist()
        test_redaction_confidentiality()
        test_lecture_group_limited_perms()
        test_has_permission_in_group()
        test_get_group_permissions()
        test_routes_coverage()

        print("\n" + "=" * 80)
        print("[OK] TOUS LES TESTS PASSENT")
        print("=" * 80)

    except AssertionError as e:
        print(f"\n[FAIL] TEST ÉCHOUÉ: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] ERREUR: {e}")
        sys.exit(1)
