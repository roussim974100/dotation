#!/usr/bin/env python3
"""
Script de fusion intelligente pour users.json
- Préserve les utilisateurs locaux
- Met à jour les groupes/permissions depuis le repo
- Crée un backup avant modification
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

USERS_FILE = Path("backend/users.json")
BACKUP_DIR = Path("backend/.backups")

def backup_users():
    """Créer un backup du users.json actuel"""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"users_{timestamp}.json"
    shutil.copy(USERS_FILE, backup_file)
    print(f"[OK] Backup cree : {backup_file}")
    return backup_file

def load_json(path):
    """Charger JSON de manière sûre"""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"✗ Erreur lecture {path}: {e}")
        return None

def merge_users_config():
    """
    Fusionner users.json du repo avec la version locale en prod
    - Préserve les utilisateurs existants en prod
    - Met à jour les groupes/permissions depuis le repo
    """

    # Charger les fichiers
    repo_config = load_json(USERS_FILE)
    if not repo_config:
        print("[ERROR] Impossible de charger users.json du repo")
        return False

    # S'il n'existe pas de fichier local, c'est le premier déploiement
    if not USERS_FILE.exists():
        print("[INFO] Premiers utilisateurs - fichier cree depuis le repo")
        return True

    # Créer un backup
    backup_file = backup_users()

    # Charger la config actuelle
    current_config = load_json(USERS_FILE)
    if not current_config:
        print("[ERROR] Erreur : impossible de lire le users.json local")
        return False

    # Fusionner : garder les utilisateurs locaux, mettre à jour les groupes
    merged_config = {
        "_comment": repo_config.get("_comment", "Configuration locale"),
        "groups": repo_config["groups"],  # Groupes à jour du repo
        "users": current_config["users"]   # Utilisateurs conservés en local
    }

    # Écrire le fichier fusionné
    with open(USERS_FILE, 'w') as f:
        json.dump(merged_config, f, indent=2, ensure_ascii=False)

    print(f"[OK] Fusion complete : {len(merged_config['users'])} utilisateurs conserves")
    print(f"[OK] Groupes mis a jour depuis le repo")
    print(f"[OK] Backup disponible : {backup_file}")
    return True

if __name__ == "__main__":
    success = merge_users_config()
    exit(0 if success else 1)
