# Configuration centralisée des permissions par route et groupe
# Utilisé pour valider la cohérence au démarrage

ROUTES_REQUIRED_PERMISSIONS = {
    # Routes formulaires (cœur métier - critiques)
    "/api/forms": ["forms.read_list"],
    "/api/forms/<form_id>": ["forms.read_detail"],

    # Routes admin (gestion globale - critiques)
    "/api/admin/users": ["users.manage"],
    "/api/admin/services": ["users.manage"],
    "/api/admin/resources": ["users.manage"],
    "/api/admin/groups": ["users.manage"],

    # Routes spécialisées
    "/api/unc": ["forms.view_all"],
}

DEFAULT_GROUPS = {
    "admin": ["users.manage", "forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.delete", "forms.view_all", "forms.export", "forms.restitution", "db.manage", "unc.view_all"],
    "user": ["forms.read_list", "forms.read_detail", "forms.create", "forms.view_all"],
    "administration": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "users.manage"],
    "direction": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "unc.view_all", "users.manage"],
    "gestion": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "users.manage"],
    "lecture": ["forms.read_list", "forms.read_detail", "forms.export", "forms.view_all"],
    "redaction": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export"],
}


def validate_permissions_at_startup():
    """
    Valide que tous les groupes ont les permissions requises par les routes.
    Affiche des warnings si des permissions manquent.
    Appelé au démarrage de l'application.
    """
    print("\n" + "=" * 80)
    print("VALIDATION DES PERMISSIONS AU DEMARRAGE")
    print("=" * 80)

    warnings = []

    # Pour chaque route, vérifier que les groupes ont les permissions requises
    for route, required_perms in ROUTES_REQUIRED_PERMISSIONS.items():
        for group_name, group_perms in DEFAULT_GROUPS.items():
            for req_perm in required_perms:
                if req_perm not in group_perms and "*" not in group_perms:
                    warnings.append(f"  [WARN] {group_name:15} manque '{req_perm}' pour acceder a {route}")

    if warnings:
        print("\nAVERTISSEMENTS - Permissions manquantes :\n")
        for warning in warnings:
            print(warning)
        print("\n[WARN] Certains groupes manquent des permissions !")
        print("       Utilisateurs du groupe affecte auront des erreurs 403\n")
    else:
        print("\n[OK] Toutes les permissions sont correctes !")
        print("     Tous les groupes ont les permissions requises.\n")

    print("=" * 80 + "\n")


def get_group_permissions(group_name: str) -> list:
    """Retourne les permissions d'un groupe"""
    return DEFAULT_GROUPS.get(group_name, [])


def has_permission_in_group(group_name: str, permission: str) -> bool:
    """Vérifie qu'un groupe a une permission spécifique"""
    group_perms = DEFAULT_GROUPS.get(group_name, [])
    return permission in group_perms or "*" in group_perms
