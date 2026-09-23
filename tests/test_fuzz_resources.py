"""Batterie de propriétés sur des descriptions de champs hostiles : aucune erreur, normalisation idempotente, rôles cohérents,
aller-retour du catalogue sans perte. Graines fixes (reproductible) ; sans dépendance externe."""
import json
import random
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.catalog import normalize_resource_catalog_payload
from models.workflow import FIELD_ROLES, MAX_FIELDS_PER_RESOURCE, normalize_resource_field_schema

LABELS = ["N° de série", "Numéro de série", "IMEI", "Номер", "序列号", "😀", "", "   ", "a" * 500, "Prix (€)", "O'Brien \"x\"", "<script>alert(1)</script>",
          "quantité", "Quantité", "taille", "Émail", "x", "Ünï-cödé", "a;b,c", "=CMD()", "‮\u0000ctrl"]
TYPES = ["text", "textarea", "select", "date", "number", "checkbox", "list", "email_with_domain", "inconnu", "", None, 5]
KEYS = [None, "", "numeroSerie", "numero_serie", "N°", "cle avec espaces", "CLE_MAJ", "é", "a" * 80, 12]


def random_schema(rng):
    fields = []
    for _ in range(rng.choice([0, 1, 2, 5, 12, 70, 200])):
        field = {}
        if rng.random() < 0.9:
            field["label"] = rng.choice(LABELS)
        if rng.random() < 0.5:
            field["key"] = rng.choice(KEYS)
        if rng.random() < 0.8:
            field["type"] = rng.choice(TYPES)
        if rng.random() < 0.3:
            field["role"] = rng.choice(list(FIELD_ROLES) + ["", "n_importe_quoi", None])
        for flag in ("identifier", "quantity", "variant", "required", "hidden", "suggest"):
            if rng.random() < 0.15:
                field[flag] = rng.choice([True, False, "oui", 0, None])
        if rng.random() < 0.3:
            field["options"] = rng.choice([[], ["a", "a", "b"], "pas une liste", [1, None, "x"], ["z"] * 500])
        if rng.random() < 0.2:
            field["aliases"] = rng.choice([["old"], "x", [None, 3, "Ö"], []])
        fields.append(rng.choice([field, field, "pas un dict", None, 7, ["liste"]]))
    return rng.choice([fields, fields, None, {"a": 1}, "texte", 42])


def test_200_schemas_hostiles_ne_levent_aucune_erreur_et_restent_coherents():
    for seed in range(200):
        rng = random.Random(seed)
        raw = random_schema(rng)
        first = normalize_resource_field_schema(raw)
        assert isinstance(first, list) and len(first) <= MAX_FIELDS_PER_RESOURCE, seed
        # idempotence : renormaliser un schema deja normalise ne change rien
        assert normalize_resource_field_schema(first) == first, seed
        keys = [f["key"] for f in first]
        assert all(keys) and all(f["label"] for f in first), seed
        # un seul champ par role, drapeaux derives du role
        for role in FIELD_ROLES:
            assert sum(1 for f in first if f["role"] == role) <= 1, (seed, role)
        assert all(f[r] == (f["role"] == r) for f in first for r in FIELD_ROLES), seed
        json.dumps(first, ensure_ascii=False)  # serialisable


def test_le_catalogue_fait_l_aller_retour_sans_perte_ni_erreur():
    for seed in range(100):
        rng = random.Random(1000 + seed)
        payload = {"code": f"res_{seed}", "label": "Ressource", "field_schema": random_schema(rng)}
        first = normalize_resource_catalog_payload(payload)
        stored = {"field_schema_json": json.dumps(first["field_schema"], ensure_ascii=False)}
        # sauvegarde suivante sans rien changer (l'editeur renvoie les champs tels quels) : rien ne bouge, aucun identifiant ne change
        second = normalize_resource_catalog_payload({"code": first["code"], "label": first["label"], "field_schema": [dict(f) for f in first["field_schema"]]}, stored)
        assert [f["id"] for f in second["field_schema"]] == [f["id"] for f in first["field_schema"]], seed
        assert [f["key"] for f in second["field_schema"]] == [f["key"] for f in first["field_schema"]], seed
        assert all(f["id"] for f in first["field_schema"]), seed
