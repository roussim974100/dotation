"""Types de beneficiaires : drapeau « |mandat », compatibilite du type historique « elu »."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import pytest

from models.settings import SettingsValidationError, _parse_beneficiary_types, normalize_beneficiary_types


def test_elu_sans_drapeau_garde_son_mandat_pour_les_anciennes_bases():
    parsed = {t["value"]: t["mandate"] for t in _parse_beneficiary_types("agent:Agent,elu:Élu(e)")}
    assert parsed == {"agent": False, "elu": True}


def test_drapeau_mandat_sur_un_type_personnalise():
    parsed = {t["value"]: t for t in _parse_beneficiary_types("agent:Agent,conseiller:Conseiller municipal|mandat")}
    assert parsed["conseiller"]["mandate"] is True and parsed["conseiller"]["label"] == "Conseiller municipal"
    assert parsed["agent"]["mandate"] is False


def test_normalisation_conserve_le_drapeau_et_refuse_les_options_inconnues():
    assert normalize_beneficiary_types("agent:Agent, elu:Élu(e)|mandat") == "agent:Agent,elu:Élu(e)|mandat"
    with pytest.raises(SettingsValidationError):
        normalize_beneficiary_types("agent:Agent|bizarre")


def test_elu_explicitement_sans_mandat():
    # un drapeau explicite autre que « mandat » n'existe pas : sans « |mandat », seul le type historique « elu » reste avec mandat
    assert {t["value"]: t["mandate"] for t in _parse_beneficiary_types("agent:Agent,stagiaire:Stagiaire")} == {"agent": False, "stagiaire": False}
