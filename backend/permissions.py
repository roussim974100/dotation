# Configuration centralisée des permissions par route et groupe
# Utilisé pour valider la cohérence au démarrage

ROUTES_REQUIRED_PERMISSIONS = {
    "/api/forms/list": ["forms.read_list"],
    "/api/forms/get": ["forms.read_detail"],
    "/api/forms/create": ["forms.create"],
    "/api/forms/update": ["forms.edit"],
    "/api/forms/delete": ["forms.delete"],
    "/api/forms/export": ["forms.export"],
    "/api/forms/restitution": ["forms.restitution"],
    "/api/admin": ["users.manage"],
    "/pages/db": ["db.manage"],
    "/api/unc": ["forms.view_all"],
}

DEFAULT_GROUPS = {
    "admin": ["users.manage", "forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.delete", "forms.view_all", "forms.export", "forms.restitution", "db.manage", "unc.view_all", "pools.manage"],
    "user": ["forms.read_list", "forms.read_detail", "forms.create", "forms.view_all"],
    "administration": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "users.manage"],
    "direction": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage", "unc.view_all"],
    "gestion": ["forms.read_list", "forms.read_detail", "forms.create", "forms.edit", "forms.restitution", "forms.export", "forms.delete", "forms.view_all", "pools.manage"],
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
    print("VALIDATION DES PERMISSIONS AU DÉMARRAGE")
    print("=" * 80)

    warnings = []

    # Pour chaque route, vérifier que les groupes ont les permissions requises
    for route, required_perms in ROUTES_REQUIRED_PERMISSIONS.items():
        for group_name, group_perms in DEFAULT_GROUPS.items():
            for req_perm in required_perms:
                if req_perm not in group_perms and "*" not in group_perms:
                    warnings.append(f"  ⚠️  {group_name:15} manque '{req_perm}' pour accéder à {route}")

    if warnings:
        print("\nAVERTISSEMENTS - Permissions manquantes :\n")
        for warning in warnings:
            print(warning)
        print("\n⚠️  Certains groupes manquent des permissions !")
        print("    Utilisateurs du groupe affecté auront des erreurs 403\n")
    else:
        print("\n✅ Toutes les permissions sont correctes !")
        print("   Tous les groupes ont les permissions requises.\n")

    print("=" * 80 + "\n")


def get_group_permissions(group_name: str) -> list:
    """Retourne les permissions d'un groupe"""
    return DEFAULT_GROUPS.get(group_name, [])


def has_permission_in_group(group_name: str, permission: str) -> bool:
    """Vérifie qu'un groupe a une permission spécifique"""
    group_perms = DEFAULT_GROUPS.get(group_name, [])
    return permission in group_perms or "*" in group_perms
