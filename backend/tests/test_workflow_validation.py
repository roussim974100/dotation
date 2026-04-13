"""Tests de validation des ressources dynamiques dans workflow.py.

Couvre les cas de figure à risque :
- Clés camelCase dans fields{} vs slugify_field_key (ex: numeroSerie → numeroserie)
- Champs requis manquants vs renseignés
- Format legacy (materiel/immateriel) vs nouveau (resources.additional)
- Non-régression du bug imei/numeroSerie
- Intégration bout-en-bout via persist_form
"""

import pytest
from models.workflow import (
    collect_resource_validation_errors,
    is_dynamic_resource_complete,
    compute_effective_workflow_status,
    normalize_resource_field_schema,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resource(code="telephone", label="Téléphone", fields=None, field_schema=None, selected=True, assigned_at="2026-01-01"):
    return {
        "id": f"resource_{code}",
        "code": code,
        "label": label,
        "selected": selected,
        "fields": fields or {},
        "fieldSchema": field_schema or [],
        "assignedAt": assigned_at,
        "hasAssignmentDate": True,
    }


def _schema(*fields):
    """Raccourci pour construire un fieldSchema."""
    return [
        {"key": key, "label": label, "type": "text", "required": required}
        for key, label, required in fields
    ]


def _payload(resources=None, materiel=None, immateriel=None):
    return {
        "materiel": materiel or {},
        "immateriel": immateriel or {},
        "resources": {"additional": resources or []},
    }


# ---------------------------------------------------------------------------
# collect_resource_validation_errors — format dynamique (resources.additional)
# ---------------------------------------------------------------------------

class TestDynamicResourceValidation:

    def test_champ_requis_renseigne_camelcase(self):
        """Clé camelCase (numeroSerie) stockée dans fields{} — ne doit PAS générer d'erreur."""
        schema = _schema(
            ("numeroserie", "N° de série (SN)", True),  # clé slugifiée dans fieldSchema
        )
        resource = _resource(
            fields={"numeroSerie": "SN-APPLE-001"},  # clé camelCase dans fields{}
            field_schema=schema,
        )
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert errors == [], f"Erreurs inattendues : {errors}"

    def test_champ_requis_vide_genere_erreur(self):
        """Champ requis vide → erreur attendue."""
        schema = _schema(("numeroserie", "N° de série (SN)", True))
        resource = _resource(fields={}, field_schema=schema)
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert len(errors) == 1
        assert "N° de série (SN)" in errors[0]

    def test_champ_non_requis_vide_pas_erreur(self):
        """Champ non requis vide → pas d'erreur."""
        schema = _schema(("nomtelephone", "Nom du téléphone", False))
        resource = _resource(fields={}, field_schema=schema)
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert errors == []

    def test_plusieurs_champs_requis_tous_renseignes(self):
        """Tous les champs requis renseignés (camelCase) → pas d'erreur."""
        schema = _schema(
            ("marque", "Marque", True),
            ("modele", "Modèle", True),
            ("numeroserie", "N° de série (SN)", True),
        )
        resource = _resource(
            fields={"marque": "Apple", "modele": "iPhone 15", "numeroSerie": "SN-001"},
            field_schema=schema,
        )
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert errors == [], f"Erreurs inattendues : {errors}"

    def test_plusieurs_champs_requis_un_manquant(self):
        """Un champ requis manquant → une seule erreur."""
        schema = _schema(
            ("marque", "Marque", True),
            ("modele", "Modèle", True),
            ("numeroserie", "N° de série (SN)", True),
        )
        resource = _resource(
            fields={"marque": "Apple", "modele": "iPhone 15"},  # numeroSerie absent
            field_schema=schema,
        )
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert len(errors) == 1
        assert "N° de série (SN)" in errors[0]

    def test_ressource_non_selectionnee_ignoree(self):
        """Ressource non sélectionnée → ignorée même si champs requis vides."""
        schema = _schema(("numeroserie", "N° de série (SN)", True))
        resource = _resource(fields={}, field_schema=schema, selected=False)
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert errors == []

    def test_date_attribution_manquante_genere_erreur(self):
        """Date d'attribution manquante → erreur."""
        schema = _schema(("marque", "Marque", True))
        resource = _resource(
            fields={"marque": "Apple"},
            field_schema=schema,
            assigned_at="",
        )
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert any("date d'attribution" in e.lower() for e in errors), f"Erreur date attendue, obtenu : {errors}"

    def test_sans_schema_sans_details_genere_erreur(self):
        """Ressource sans fieldSchema et sans details → erreur incomplète."""
        resource = _resource(fields={}, field_schema=[])
        # Pas de details, pas de fieldSchema → summarize_dynamic_resource retourne ""
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert any("incomplète" in e or "Téléphone" in e for e in errors), f"Erreur attendue : {errors}"


# ---------------------------------------------------------------------------
# Non-régression bug imei → numeroSerie
# ---------------------------------------------------------------------------

class TestLegacyImeiBug:

    def test_numeroserie_camelcase_valide(self):
        """Régression : fields.numeroSerie doit être reconnu même après slugify du schema."""
        schema = _schema(
            ("marque", "Marque", True),
            ("modele", "Modèle", True),
            ("numeroserie", "N° de série (SN)", True),
        )
        resource = _resource(
            code="telephone",
            label="Téléphone",
            fields={"marque": "Samsung", "modele": "Galaxy A54", "numeroSerie": "987654321098765"},
            field_schema=schema,
        )
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert errors == [], f"Régression bug imei détectée : {errors}"

    def test_imei_ancien_format_non_reconnu_dans_fields(self):
        """L'ancienne clé 'imei' dans fields{} n'est PAS reconnue si le schema attend 'numeroserie'."""
        schema = _schema(("numeroserie", "N° de série (SN)", True))
        resource = _resource(
            fields={"imei": "123456789"},  # ancienne clé, plus supportée dans fields{}
            field_schema=schema,
        )
        # Ce cas génère une erreur — c'est le comportement attendu.
        # La migration JS migrateLegacyResourcesToAdditional doit avoir converti imei → numeroSerie
        # AVANT que les données atteignent le backend.
        errors = collect_resource_validation_errors(_payload(resources=[resource]))
        assert len(errors) == 1  # imei non reconnu → SN manquant


# ---------------------------------------------------------------------------
# is_dynamic_resource_complete — même logique de lookup
# ---------------------------------------------------------------------------

class TestIsDynamicResourceComplete:

    def test_complet_avec_camelcase(self):
        schema = _schema(("numeroserie", "N° de série (SN)", True))
        resource = _resource(
            fields={"numeroSerie": "SN-001"},
            field_schema=schema,
        )
        assert is_dynamic_resource_complete(resource) is True

    def test_incomplet_champ_requis_vide(self):
        schema = _schema(("numeroserie", "N° de série (SN)", True))
        resource = _resource(fields={}, field_schema=schema)
        assert is_dynamic_resource_complete(resource) is False

    def test_non_selectionne_retourne_false(self):
        resource = _resource(fields={"marque": "Apple"}, selected=False)
        assert is_dynamic_resource_complete(resource) is False

    def test_sans_schema_avec_details_retourne_true(self):
        """Sans fieldSchema, details suffit comme indicateur de complétion."""
        resource = {
            "id": "resource_autre",
            "code": "autre",
            "label": "Autre",
            "selected": True,
            "fields": {},
            "details": "Description de l'équipement",
            "fieldSchema": [],
            "assignedAt": "2026-01-01",
            "hasAssignmentDate": True,
        }
        assert is_dynamic_resource_complete(resource) is True


# ---------------------------------------------------------------------------
# Format legacy materiel/immateriel (fixed_rules)
# ---------------------------------------------------------------------------

class TestLegacyFixedRules:

    def test_telephone_legacy_avec_numeroserie(self):
        """Ancien format materiel.telephone avec numeroSerie → pas d'erreur."""
        payload = _payload(materiel={
            "telephone": {
                "selected": True,
                "marque": "Apple",
                "modele": "iPhone 15",
                "numeroSerie": "SN-001",
            }
        })
        errors = collect_resource_validation_errors(payload)
        assert errors == [], f"Erreurs inattendues : {errors}"

    def test_telephone_legacy_avec_imei_genere_erreur(self):
        """Ancien format avec clé 'imei' (pas 'numeroSerie') → erreur attendue (clé inconnue)."""
        payload = _payload(materiel={
            "telephone": {
                "selected": True,
                "marque": "Apple",
                "modele": "iPhone 15",
                "imei": "123456789",  # ancienne clé non reconnue par fixed_rules
            }
        })
        errors = collect_resource_validation_errors(payload)
        assert any("série" in e.lower() or "SN" in e for e in errors)

    def test_telephone_legacy_non_selectionne_ignore(self):
        payload = _payload(materiel={
            "telephone": {"selected": False, "marque": "", "modele": "", "numeroSerie": ""}
        })
        errors = collect_resource_validation_errors(payload)
        assert errors == []


# ---------------------------------------------------------------------------
# normalize_resource_field_schema — vérifier la transformation slugify
# ---------------------------------------------------------------------------

class TestNormalizeFieldSchema:

    def test_camelcase_key_slugified(self):
        """Les clés camelCase sont transformées en minuscules par slugify_field_key."""
        schema = [{"key": "numeroSerie", "label": "SN", "type": "text", "required": True}]
        normalized = normalize_resource_field_schema(schema)
        assert normalized[0]["key"] == "numeroserie"

    def test_already_lowercase_unchanged(self):
        schema = [{"key": "marque", "label": "Marque", "type": "text", "required": True}]
        normalized = normalize_resource_field_schema(schema)
        assert normalized[0]["key"] == "marque"

    def test_accented_key_stripped(self):
        schema = [{"key": "numéroSérie", "label": "SN", "type": "text"}]
        normalized = normalize_resource_field_schema(schema)
        assert normalized[0]["key"] == "numeroserie"


# ---------------------------------------------------------------------------
# Intégration bout-en-bout : workflow status avec ressources camelCase
# ---------------------------------------------------------------------------

class TestWorkflowStatusIntegration:

    def _full_payload(self, resources, status="draft", signed=True, rgpd=True):
        return {
            "beneficiaire": {"nom": "Test", "prenom": "User", "service": "DSI", "qualite": "agent"},
            "dossier": {"type": "arrivee"},
            "materiel": {},
            "immateriel": {},
            "resources": {"additional": resources},
            "unc_acces": [],
            "restitution": {},
            "validation": {
                "rgpdAccepted": rgpd,
                "signatureDataUrl": "data:image/png;base64,abc" if signed else "",
            },
            "workflow": {"status": status},
            "meta": {"startAt": "2026-01-15"},
        }

    def test_complet_camelcase_donne_partial_assignment_pas_active(self):
        """Un dossier complet en draft passe en partial_assignment (active nécessite une demande explicite)."""
        schema = _schema(("marque", "Marque", True), ("numeroserie", "N° de série", True))
        resource = _resource(
            fields={"marque": "Apple", "numeroSerie": "SN-001"},
            field_schema=schema,
        )
        payload = self._full_payload([resource])
        errors = collect_resource_validation_errors(payload)
        payload["meta"]["resourceValidationErrors"] = errors
        status = compute_effective_workflow_status(payload)
        assert errors == [], f"Erreurs inattendues : {errors}"
        # draft → partial_assignment (pas active sans demande explicite)
        assert status == "partial_assignment"

    def test_complet_deja_active_reste_active(self):
        """Un dossier déjà active avec champs camelCase reste active."""
        schema = _schema(("marque", "Marque", True), ("numeroserie", "N° de série", True))
        resource = _resource(
            fields={"marque": "Apple", "numeroSerie": "SN-001"},
            field_schema=schema,
        )
        payload = self._full_payload([resource], status="active")
        errors = collect_resource_validation_errors(payload)
        payload["meta"]["resourceValidationErrors"] = errors
        status = compute_effective_workflow_status(payload)
        assert errors == []
        assert status == "active"

    def test_champ_manquant_donne_partial_assignment(self):
        """Champ requis manquant → partial_assignment."""
        schema = _schema(("marque", "Marque", True), ("numeroserie", "N° de série", True))
        resource = _resource(
            fields={"marque": "Apple"},  # SN manquant
            field_schema=schema,
        )
        payload = self._full_payload([resource])
        errors = collect_resource_validation_errors(payload)
        payload["meta"]["resourceValidationErrors"] = errors
        status = compute_effective_workflow_status(payload)
        assert len(errors) == 1
        assert status == "partial_assignment"

    def test_sans_signature_sans_rgpd_ressource_incomplete_donne_draft(self):
        """Sans signature ni RGPD + ressource incomplète → draft."""
        schema = _schema(("marque", "Marque", True))
        resource = _resource(fields={}, field_schema=schema)  # champ requis manquant
        payload = self._full_payload([resource], signed=False, rgpd=False)
        errors = collect_resource_validation_errors(payload)
        payload["meta"]["resourceValidationErrors"] = errors
        status = compute_effective_workflow_status(payload)
        assert status == "draft"

    def test_sans_signature_complet_donne_awaiting(self):
        """Sans signature mais ressources complètes + RGPD → awaiting_signature."""
        schema = _schema(("marque", "Marque", True))
        resource = _resource(fields={"marque": "Apple"}, field_schema=schema)
        payload = self._full_payload([resource], signed=False, rgpd=True)
        errors = collect_resource_validation_errors(payload)
        payload["meta"]["resourceValidationErrors"] = errors
        status = compute_effective_workflow_status(payload)
        assert errors == []
        assert status == "awaiting_signature"
