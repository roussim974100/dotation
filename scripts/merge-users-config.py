#!/usr/bin/env python3
"""
Script de fusion intelligente des configurations utilisateurs.
Préserve les utilisateurs locaux (avec leurs mots de passe) et met à jour les permissions/groupes depuis git.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

def load_json(path):
    """Charge un fichier JSON."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Impossible de lire {path}: {e}")
        return None

def save_json(path, data):
    """Sauvegarde un fichier JSON."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Impossible d'écrire {path}: {e}")
        return False

def backup_file(path):
    """Crée une sauvegarde du fichier avec timestamp."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.backup.{timestamp}"
        with open(path, 'r', encoding='utf-8') as src:
            with open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
        print(f"[OK] Sauvegarde créée: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[ERROR] Impossible de créer une sauvegarde: {e}")
        return None

def merge_users_config():
    """Fusionne les configurations utilisateurs."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Chemins
    prod_users_path = project_root / "backend" / ".prod" / "users.json"
    repo_users_path = project_root / "backend" / "users.json"

    print("\n========================================")
    print("Fusion des configurations utilisateurs")
    print("========================================\n")

    # 1. Charger les configurations
    print("[1] Chargement des configurations...")

    if not prod_users_path.exists():
        print(f"    [WARN] Aucune config locale en {prod_users_path}")
        prod_config = None
    else:
        prod_config = load_json(prod_users_path)
        if not prod_config:
            return False

    repo_config = load_json(repo_users_path)
    if not repo_config:
        return False

    print("    [OK] Configurations chargées")

    # 2. Si aucune config locale, utiliser repo
    if not prod_config:
        print("[2] Première installation - utiliser configuration du dépôt")
        if save_json(prod_users_path, repo_config):
            print("    [OK] Configuration initialisée")
            return True
        else:
            return False

    # 3. Fusionner: groupes depuis repo, utilisateurs depuis prod
    print("[2] Fusion intelligente...")

    merged_config = {
        "groups": repo_config.get("groups", {}),
        "users": prod_config.get("users", [])
    }

    # 4. Vérifier que tous les utilisateurs locaux ont des groupes valides
    repo_group_names = set(repo_config.get("groups", {}).keys())
    for user in merged_config["users"]:
        user_groups = user.get("groups", [])
        invalid_groups = [g for g in user_groups if g not in repo_group_names]
        if invalid_groups:
            print(f"    [WARN] Utilisateur '{user.get('username')}' a des groupes invalides: {invalid_groups}")
            user["groups"] = [g for g in user_groups if g in repo_group_names]

    # 5. Sauvegarder
    print("[3] Sauvegarde de la fusion...")
    backup_file(prod_users_path)
    if save_json(prod_users_path, merged_config):
        print("    [OK] Fusion sauvegardée")
    else:
        return False

    # 6. Résumé
    print("\n========================================")
    print("[SUCCESS] Fusion complétée avec succès!")
    print("========================================")
    print(f"  • Groupes: {len(merged_config['groups'])} (depuis dépôt)")
    print(f"  • Utilisateurs: {len(merged_config['users'])} (locaux préservés)")
    print(f"  • Config: {prod_users_path}")
    print()

    return True

if __name__ == "__main__":
    success = merge_users_config()
    sys.exit(0 if success else 1)
