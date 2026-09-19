"""Regles de modification par l'utilisateur de son propre compte.

Un utilisateur peut modifier son adresse e-mail. Son identifiant n'est jamais modifiable, et son nom et
prenom ne sont renseignables qu'UNE SEULE FOIS (tant qu'ils sont vides) : ensuite seul un administrateur
peut les changer. Fonctions pures, testables sans Flask ni base.
"""
import re

from auth import normalize_email

_NAME_RE = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '’.\-]){0,79}$", re.UNICODE)
SELF_EDITABLE_ONCE = ("first_name", "last_name")


def normalize_person_name(value):
    """Nom ou prenom : retourne (valeur nettoyee, erreur). Vide accepte ; erreur = None si valide."""
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    if not name:
        return "", None
    if not _NAME_RE.match(name):
        return name, "invalid_name"
    return name, None


def build_self_update(current, payload):
    """Retourne (champs a enregistrer, code d'erreur). `current` = enregistrement actuel du compte."""
    fields = {}
    if "username" in payload and str(payload["username"] or "").strip() != current.get("username"):
        return None, "identity_locked"

    if "email" in payload:
        email, error = normalize_email(payload["email"])
        if error:
            return None, error
        if email != (current.get("email") or ""):
            fields["email"] = email

    for key in SELF_EDITABLE_ONCE:
        if key not in payload:
            continue
        name, error = normalize_person_name(payload[key])
        if error:
            return None, error
        existing = current.get(key) or ""
        if name == existing:
            continue
        if existing:
            return None, "identity_locked"
        fields[key] = name
    return fields, None
