"""Adresse e-mail facultative des comptes."""
import sqlite3
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import database
from auth import normalize_email


@pytest.mark.parametrize("raw, expected", [
    ("", ""), (None, ""), ("   ", ""),
    ("Prenom.Nom@Collectivite.FR", "prenom.nom@collectivite.fr"),
    ("  a@b.co ", "a@b.co"),
])
def test_valid_or_empty_emails_are_normalized(raw, expected):
    assert normalize_email(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["sans-arobase", "a@b", "a b@c.fr", "@c.fr", "a@@c.fr", "x" * 250 + "@c.fr"])
def test_invalid_emails_are_rejected(raw):
    assert normalize_email(raw)[1] == "invalid_email"


def test_existing_users_database_gets_the_email_column(tmp_path, monkeypatch):
    path = str(tmp_path / "users.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)")
    conn.execute("INSERT INTO users VALUES ('alice','x')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DB_USERS_PATH", path)

    database.ensure_users_schema()
    database.ensure_users_schema()  # idempotent

    conn = sqlite3.connect(path)
    assert conn.execute("SELECT username, email FROM users").fetchall() == [("alice", "")]
    conn.close()
