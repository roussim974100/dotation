"""Un dossier de regularisation (restitution sans attribution saisie) doit naitre
directement en restitution en cours et exposer ses ressources a restituer."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.forms import normalize_workflow_before_save
from models.workflow import collect_resource_entries, compute_effective_workflow_status


def _regularisation_payload():
    return {
        "dossier": {"type": "sortie", "regularisation": True},
        "beneficiaire": {"nom": "Dupont", "prenom": "Anne", "qualite": "agent"},
        "resources": {"additional": [{
            "id": 1, "code": "ordinateur", "label": "Ordinateur", "category": "materiel",
            "requiresReturn": True, "selected": True, "fields": {},
            "details": "Non renseigné (régularisation)",
        }]},
        "restitution": {"notes": "Régularisation", "pendingFinalization": True, "items": {}},
        "workflow": {"status": "partial_return"},
        "meta": {},
    }


def test_regularisation_stays_partial_return_on_save():
    payload = normalize_workflow_before_save(_regularisation_payload())
    assert payload["workflow"]["status"] == "partial_return"


def test_regularisation_is_not_recomputed_to_returned_without_items():
    assert compute_effective_workflow_status(_regularisation_payload()) == "partial_return"


def test_regularisation_resources_are_listed_for_restitution():
    entries = collect_resource_entries(_regularisation_payload())
    assert [e["label"] for e in entries] == ["Ordinateur"]
