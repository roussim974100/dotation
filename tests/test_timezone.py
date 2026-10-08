"""Fuseau horaire de l'organisation : les heures enregistrées en UTC sont affichées dans le fuseau réglé (Europe/Paris par défaut) dans
les PDF et exports ; une heure saisie à la main (sans fuseau) n'est jamais décalée ; un réglage inconnu retombe sur Europe/Paris.
Base temporaire (tests/conftest.py)."""
import io
from datetime import datetime, timezone

import pytest

from app import app
from database import get_db
from models.settings import SettingsValidationError, save_app_settings
from utils import DEFAULT_TIMEZONE, format_export_datetime, get_org_timezone, reset_timezone_cache

H = {"X-CSRF-Token": "jeton"}


def regler(nom):
    with get_db() as connection:
        save_app_settings(connection, {"timezone": nom})


@pytest.fixture(autouse=True)
def fuseau_par_defaut_apres_le_test():
    regler(DEFAULT_TIMEZONE)
    yield
    regler(DEFAULT_TIMEZONE)


def admin_client():
    client = app.test_client()
    with client.session_transaction() as s:
        s["user"] = "admin"
        s["csrf_token"] = "jeton"
    return client


def test_paris_heure_d_ete_et_d_hiver():
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 09:03"   # UTC+2 en octobre
    assert format_export_datetime("2026-01-10T10:00:00+00:00") == "10/01/2026 11:00"   # UTC+1 en janvier
    assert format_export_datetime("2026-10-08T07:03:00Z") == "08/10/2026 09:03"        # suffixe Z
    assert format_export_datetime("2026-10-08T07:03:12.345678+00:00") == "08/10/2026 09:03"  # microsecondes, comme utc_now()


def test_changement_d_heure_de_la_nuit_du_25_au_26_octobre():
    assert format_export_datetime("2026-10-25T00:30:00+00:00") == "25/10/2026 02:30"   # encore l'heure d'été (UTC+2)
    assert format_export_datetime("2026-10-25T01:30:00+00:00") == "25/10/2026 02:30"   # passage à l'heure d'hiver (UTC+1)


def test_une_heure_saisie_a_la_main_n_est_jamais_decalee():
    assert format_export_datetime("2026-09-01T09:00:00") == "01/09/2026 09:00"
    assert format_export_datetime("2026-09-01") == "01/09/2026 00:00"  # comportement historique pour une date seule
    assert format_export_datetime("01/09/2026") == "01/09/2026"
    assert format_export_datetime(None) == "-" and format_export_datetime("") == "-"
    assert format_export_datetime("pas une date") == "pas une date"


def test_une_heure_deja_dans_le_bon_fuseau_n_est_pas_decalee_deux_fois():
    assert format_export_datetime("2026-10-08T09:03:00+02:00") == "08/10/2026 09:03"


def test_autre_fuseau_selon_l_endroit_ou_se_trouve_l_application():
    regler("Indian/Reunion")  # UTC+4 toute l'année
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 11:03"
    assert format_export_datetime("2026-01-10T10:00:00+00:00") == "10/01/2026 14:00"
    regler("America/Montreal")  # UTC-4 l'été
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 03:03"
    regler("UTC")
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 07:03"


def test_le_changement_de_reglage_s_applique_tout_de_suite():
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 09:03"
    regler("Indian/Reunion")
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 11:03"  # sans attendre l'expiration du cache


def test_un_reglage_illisible_en_base_retombe_sur_paris_sans_exception():
    with get_db() as connection:
        connection.execute("INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES ('timezone', 'Nulle/Part', 'x') "
                           "ON CONFLICT(setting_key) DO UPDATE SET setting_value = 'Nulle/Part'")
    reset_timezone_cache()
    assert str(get_org_timezone()) == DEFAULT_TIMEZONE
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 09:03"


def test_validation_du_reglage():
    with get_db() as connection:
        with pytest.raises(SettingsValidationError):
            save_app_settings(connection, {"timezone": "Nulle/Part"})
        with pytest.raises(SettingsValidationError):
            save_app_settings(connection, {"timezone": "../../etc/passwd"})
        save_app_settings(connection, {"timezone": ""})
        assert connection.execute("SELECT setting_value FROM app_settings WHERE setting_key = 'timezone'").fetchone()[0] == DEFAULT_TIMEZONE


def test_reglage_par_l_api_d_administration():
    admin = admin_client()
    refus = admin.put("/api/admin/settings", json={"timezone": "Nulle/Part"}, headers=H)
    assert refus.status_code == 400 and "Fuseau horaire inconnu" in refus.get_data(as_text=True)
    ok = admin.put("/api/admin/settings", json={"timezone": "Indian/Reunion"}, headers=H)
    assert ok.status_code == 200, ok.get_data(as_text=True)
    assert admin.get("/api/settings/public").get_json()["timezone"] == "Indian/Reunion"
    assert format_export_datetime("2026-10-08T07:03:00+00:00") == "08/10/2026 11:03"


def test_l_en_tete_des_pdf_est_a_l_heure_de_l_organisation():
    from pdf.attribution import _AQuaiDoc
    doc = _AQuaiDoc("Titre", "Sous-titre", "Organisation", None, None)
    tz = get_org_timezone()
    attendus = {datetime.now(timezone.utc).astimezone(tz).strftime("%d/%m/%Y %H:%M")}
    attendus.add(datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 60, tz).strftime("%d/%m/%Y %H:%M"))  # bascule de minute
    assert doc._generated_at in attendus
    regler("Indian/Reunion")
    reunion = _AQuaiDoc("Titre", "Sous-titre", "Organisation", None, None)._generated_at
    assert reunion != doc._generated_at  # 2 h d'écart entre Paris (été) et La Réunion


def test_le_pdf_d_un_ajustement_affiche_l_heure_locale():
    pypdf = pytest.importorskip("pypdf")
    from pdf.adjustment import build_adjustment_pdf_bytes
    payload = {"beneficiaire": {"nom": "FUSEAU", "prenom": "Test", "qualite": "agent", "service": "DRH"},
               "ajustements": [{"id": "a1", "at": "2026-10-08T07:03:00+00:00", "by": "admin", "ajouts": [], "retraits": [], "service": None,
                                "signature": {"mode": "distance", "status": "substitute", "signedAt": "2026-10-08T07:05:00+00:00",
                                              "reason": "Absent", "substitute": {"name": "M. Martin", "quality": "RH"}}}]}
    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(build_adjustment_pdf_bytes(payload, "a1"))).pages)
    assert "08/10/2026 09:03" in text and "08/10/2026 09:05" in text  # et non 07:03 / 07:05 (UTC)
    assert "07:03" not in text
