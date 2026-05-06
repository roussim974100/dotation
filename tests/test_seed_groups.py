"""Tests pour valider le comportement du seed des groupes et de l'admin."""
import sqlite3
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime

# Importer les fonctions à tester
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app import seed_default_groups, seed_default_admin


def utc_now():
    """Retourner l'heure actuelle au format ISO."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def test_scenario_1_empty_database():
    """Scénario 1 : Base vide
    - seed_default_groups() doit créer tous les groupes par défaut
    - seed_default_admin() doit créer admin/admin
    - admin doit être dans le groupe admin
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_users.db')

        # Créer une connexion vide
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Créer les tables
        conn.executescript("""
            CREATE TABLE users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                service TEXT,
                db_manage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE groups (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                data_scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE user_groups (
                username TEXT NOT NULL,
                group_key TEXT NOT NULL,
                PRIMARY KEY (username, group_key),
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY(group_key) REFERENCES groups(key) ON DELETE RESTRICT
            );
        """)

        # Appeler seed_default_groups et seed_default_admin
        seed_default_groups(conn)
        seed_default_admin(conn)

        # Vérifier les groupes
        groups = conn.execute("SELECT key FROM groups ORDER BY key").fetchall()
        group_keys = [g['key'] for g in groups]

        assert 'admin' in group_keys, f"Groupe 'admin' manquant. Groupes: {group_keys}"
        assert 'user' in group_keys, f"Groupe 'user' manquant. Groupes: {group_keys}"

        # Vérifier que admin/admin existe
        admin_user = conn.execute("SELECT username FROM users WHERE username = 'admin'").fetchone()
        assert admin_user, "Utilisateur 'admin' doit exister en base vide"

        # Vérifier que admin est dans le groupe admin
        admin_group = conn.execute(
            "SELECT group_key FROM user_groups WHERE username = 'admin' AND group_key = 'admin'"
        ).fetchone()
        assert admin_group, "L'utilisateur 'admin' doit être dans le groupe 'admin'"

        print("+ Scenario 1 PASSED : base vide cree admin/admin et les groupes")
        conn.close()


def test_scenario_2_existing_database_no_admin():
    """Scénario 2 : Base existante (avec utilisateur samir, pas admin)
    - appeler init_users_db() ne doit pas créer admin/admin
    - les groupes manquants doivent être créés
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_users.db')

        # Créer une base existante avec un utilisateur samir (pas admin)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        conn.executescript("""
            CREATE TABLE users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                service TEXT,
                db_manage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE groups (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                data_scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE user_groups (
                username TEXT NOT NULL,
                group_key TEXT NOT NULL,
                PRIMARY KEY (username, group_key),
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY(group_key) REFERENCES groups(key) ON DELETE RESTRICT
            );
        """)

        # Créer un utilisateur samir (pas admin)
        now = utc_now()
        conn.execute(
            "INSERT INTO users (username, password_hash, is_active, status, service, db_manage, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            ("samir", "hash_samir", 1, "active", "", 0, now, now)
        )
        conn.commit()

        # Appeler seed_default_groups avec une connexion existante
        seed_default_groups(conn)

        # Vérifier que admin/admin n'a pas été créé
        admin_user = conn.execute("SELECT username FROM users WHERE username = 'admin'").fetchone()
        assert not admin_user, "admin/admin ne doit pas être créé sur base existante"

        # Vérifier que samir existe toujours
        samir_user = conn.execute("SELECT username FROM users WHERE username = 'samir'").fetchone()
        assert samir_user, "L'utilisateur samir doit rester"

        # Vérifier que les groupes par défaut ont été créés
        groups = conn.execute("SELECT key FROM groups ORDER BY key").fetchall()
        group_keys = [g['key'] for g in groups]

        assert 'admin' in group_keys, "Groupe 'admin' doit être créé"
        assert 'user' in group_keys, "Groupe 'user' doit être créé"

        print("+ Scenario 2 PASSED : base non vide cree les groupes manquants, pas admin/admin")
        conn.close()


def test_scenario_3_manual_permission_change():
    """Scénario 3 : Changement manuel de permissions
    - retirer une permission d'un groupe
    - relancer init_users_db() ou seed_default_groups
    - vérifier que la permission retirée n'a pas été réajoutée
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, 'test_users.db')

        # Créer une base avec les groupes par défaut
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        conn.executescript("""
            CREATE TABLE users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                service TEXT,
                db_manage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE groups (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                data_scope TEXT NOT NULL DEFAULT 'full',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE user_groups (
                username TEXT NOT NULL,
                group_key TEXT NOT NULL,
                PRIMARY KEY (username, group_key),
                FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY(group_key) REFERENCES groups(key) ON DELETE RESTRICT
            );
        """)

        # Créer les groupes avec les permissions par défaut
        now = utc_now()
        default_admin_perms = ["users.manage", "forms.view_all", "db.manage", "unc.view_all"]
        conn.execute(
            "INSERT INTO groups (key, label, description, permissions_json, data_scope, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            ("admin", "Administrateur", "Accès complet", json.dumps(default_admin_perms), "full", now, now)
        )
        conn.commit()

        # Vérifier les permissions initiales
        admin_group = conn.execute("SELECT permissions_json FROM groups WHERE key = 'admin'").fetchone()
        initial_perms = json.loads(admin_group['permissions_json'])
        assert "users.manage" in initial_perms, "Permission 'users.manage' doit exister initialement"

        # Retirer une permission manuellement
        modified_perms = [p for p in initial_perms if p != "users.manage"]
        conn.execute(
            "UPDATE groups SET permissions_json = ? WHERE key = 'admin'",
            (json.dumps(modified_perms),)
        )
        conn.commit()

        # Vérifier que la permission a été retirée
        admin_group = conn.execute("SELECT permissions_json FROM groups WHERE key = 'admin'").fetchone()
        current_perms = json.loads(admin_group['permissions_json'])
        assert "users.manage" not in current_perms, "Permission 'users.manage' doit être retirée"

        # Relancer seed_default_groups
        seed_default_groups(conn)

        # Vérifier que la permission n'a pas été réajoutée
        admin_group = conn.execute("SELECT permissions_json FROM groups WHERE key = 'admin'").fetchone()
        final_perms = json.loads(admin_group['permissions_json'])
        assert "users.manage" not in final_perms, "Permission retirée ne doit pas être réajoutée par le seed"

        # Vérifier que les autres permissions restent
        assert "forms.view_all" in final_perms, "Les autres permissions doivent rester"

        print("+ Scenario 3 PASSED : permissions retirees ne sont pas reinjected")
        conn.close()


if __name__ == "__main__":
    import traceback

    tests = [
        ("Scénario 1: Base vide", test_scenario_1_empty_database),
        ("Scénario 2: Base existante sans admin", test_scenario_2_existing_database_no_admin),
        ("Scénario 3: Changement manuel de permissions", test_scenario_3_manual_permission_change),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            print(f"\n> {name}...")
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"X {name} FAILED: {e}")
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"X {name} ERROR: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Resultats: {passed} passed, {failed} failed")
    print(f"{'='*50}")

    exit(0 if failed == 0 else 1)
