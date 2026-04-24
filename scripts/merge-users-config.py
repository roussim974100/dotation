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
        path = Path(path)
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Impossible de lire {path}: {e}")
        return None

def save_json(path, data):
    """Sauvegarde un fichier JSON."""
    try:
        path = Path(path)
        # Créer le répertoire s'il n'existe pas
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Impossible d'écrire {path}: {e}")
        return False

def backup_file(path):
    """Crée une sauvegarde du fichier avec timestamp."""
    try:
        path = Path(path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.parent / f"{path.name}.backup.{timestamp}"
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
    local_users_path = project_root / "backend" / "users.json"
    repo_users_path = project_root / "backend" / "users.json"

    print("\n========================================")
    print("Fusion des configurations utilisateurs")
    print("========================================\n")

    # 1. Charger les configurations
    print("[1] Chargement des configurations...")

    # La config locale est celle déjà en place sur le serveur AVANT git reset
    # Chercher la sauvegarde la PLUS RÉCENTE (dernier timestamp)

    local_config = None
    backup_files = sorted(local_users_path.parent.glob("users.json.backup.*"), reverse=True)

    if backup_files:
        # Utiliser la sauvegarde la plus récente
        most_recent_backup = backup_files[0]
        local_config = load_json(most_recent_backup)
        if local_config:
            print(f"    [OK] Config locale trouvée: {most_recent_backup.name}")
        else:
            print(f"    [WARN] Impossible de lire: {most_recent_backup.name}")

    # Si pas de sauvegarde valide, essayer de lire directement
    if not local_config and local_users_path.exists():
        local_config = load_json(local_users_path)
        if local_config:
            print(f"    [OK] Config locale trouvée: {local_users_path}")

    repo_config = load_json(repo_users_path)
    if not repo_config:
        return False

    print("    [OK] Configurations chargées")

    # 2. Si aucune config locale, utiliser repo
    if not local_config:
        print("[2] Première installation - utiliser configuration du dépôt")
        # Déjà en place depuis git reset
        print("    [OK] Configuration du dépôt conservée")
        return True

    # 3. Fusionner: groupes depuis repo, utilisateurs depuis local
    print("[2] Fusion intelligente...")

    merged_config = {
        "groups": repo_config.get("groups", {}),
        "users": local_config.get("users", [])
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
    backup_file(local_users_path)
    if save_json(local_users_path, merged_config):
        print("    [OK] Fusion sauvegardée")
    else:
        return False

    # 6. Résumé
    print("\n========================================")
    print("[SUCCESS] Fusion complétée avec succès!")
    print("========================================")
    print(f"  • Groupes: {len(merged_config['groups'])} (depuis dépôt)")
    print(f"  • Utilisateurs: {len(merged_config['users'])} (locaux préservés)")
    print(f"  • Config: {local_users_path}")
    print()

    return True

if __name__ == "__main__":
    success = merge_users_config()
    sys.exit(0 if success else 1)
