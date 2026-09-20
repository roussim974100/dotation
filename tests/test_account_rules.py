"""Regles de modification du profil par l'utilisateur lui-meme."""
import sys
from pathlib import Path

import pytest

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from account_rules import build_self_update, normalize_person_name


def _user(**extra):
    return {"username": "jdupont", "email": "", "first_name": "", "last_name": "", **extra}


@pytest.mark.parametrize("raw, expected", [
    ("Jean", "Jean"), ("  Jean   Pierre ", "Jean Pierre"), ("Marie-Ange", "Marie-Ange"),
    ("D'Alembert", "D'Alembert"), ("Éloïse", "Éloïse"), ("", ""), (None, ""),
])
def test_valid_names_are_normalized(raw, expected):
    assert normalize_person_name(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["<script>", "Jean3", "-Jean", "x" * 90, "a;b"])
def test_invalid_names_are_rejected(raw):
    assert normalize_person_name(raw)[1] == "invalid_name"


def test_user_can_set_email_freely_and_change_it_later():
    fields, error = build_self_update(_user(), {"email": "Jean@Mairie.fr"})
    assert (fields, error) == ({"email": "jean@mairie.fr"}, None)
    fields, error = build_self_update(_user(email="jean@mairie.fr"), {"email": "nouveau@mairie.fr"})
    assert fields == {"email": "nouveau@mairie.fr"} and error is None


def test_email_can_be_removed_and_invalid_email_is_refused():
    assert build_self_update(_user(email="a@b.fr"), {"email": ""}) == ({"email": ""}, None)
    assert build_self_update(_user(), {"email": "pas-un-email"}) == (None, "invalid_email")


def test_names_can_be_set_once_when_empty():
    fields, error = build_self_update(_user(), {"first_name": "Jean", "last_name": "Dupont"})
    assert fields == {"first_name": "Jean", "last_name": "Dupont"} and error is None


def test_names_are_locked_once_set():
    current = _user(first_name="Jean", last_name="Dupont")
    assert build_self_update(current, {"first_name": "Paul"}) == (None, "identity_locked")
    assert build_self_update(current, {"last_name": ""}) == (None, "identity_locked")


def test_resending_the_same_locked_values_is_not_an_error():
    current = _user(first_name="Jean", last_name="Dupont")
    assert build_self_update(current, {"first_name": "Jean", "last_name": "Dupont", "email": "a@b.fr"}) == ({"email": "a@b.fr"}, None)


def test_only_the_empty_name_can_be_completed():
    current = _user(first_name="Jean")
    fields, error = build_self_update(current, {"first_name": "Jean", "last_name": "Dupont"})
    assert fields == {"last_name": "Dupont"} and error is None


def test_login_can_never_be_changed():
    assert build_self_update(_user(), {"username": "autre"}) == (None, "identity_locked")
    assert build_self_update(_user(), {"username": "jdupont", "email": "a@b.fr"})[1] is None


def test_unknown_fields_are_ignored():
    assert build_self_update(_user(), {"groups": ["admin"], "status": "active", "service": "DSI"}) == ({}, None)
