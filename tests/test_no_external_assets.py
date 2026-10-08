"""L'application ne doit contacter AUCUN serveur externe pour s'afficher (intranet sans Internet) : Bootstrap, Chart.js, CookieConsent et le
générateur de QR code sont embarqués (frontend/js/vendor, frontend/css/vendor). Ce test échoue si une page ou un script retourne vers un CDN."""
import re
from pathlib import Path

import pytest

from app import app

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
EXTERNE = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//(?!www\.w3\.org)[^"']+""", re.I)
PAGES = sorted(FRONTEND.glob("*.html"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_aucune_page_ne_charge_une_ressource_externe(page):
    texte = page.read_text(encoding="utf-8")
    assert not EXTERNE.findall(texte), f"{page.name} charge une ressource externe : {EXTERNE.findall(texte)}"


def test_les_scripts_ne_chargent_aucune_bibliotheque_externe():
    for script in sorted((FRONTEND / "js").glob("*.js")):  # hors vendor : ce sont les bibliothèques elles-mêmes
        texte = script.read_text(encoding="utf-8")
        assert not re.search(r"https?://cdn\.|jsdelivr|unpkg|cdnjs|googleapis", texte), f"{script.name} référence un CDN"


def test_les_bibliotheques_embarquees_sont_servies_et_ont_leur_licence():
    client = app.test_client()
    for chemin, marque in (("/css/vendor/bootstrap.min.css", "Bootstrap"), ("/js/vendor/bootstrap.bundle.min.js", "Bootstrap"),
                           ("/js/vendor/chart.umd.min.js", "Chart.js"), ("/css/vendor/cookieconsent.css", "cc-main"),
                           ("/js/vendor/cookieconsent.umd.js", "CookieConsent"), ("/js/vendor/qrcode-generator.js", "qrcode")):
        reponse = client.get(chemin)
        assert reponse.status_code == 200 and len(reponse.data) > 5000, chemin
        assert marque.lower() in reponse.data[:600].decode("utf-8", "replace").lower() or marque.lower() in reponse.data.decode("utf-8", "replace").lower()[:200000], chemin
    for licence in ("bootstrap", "chartjs", "cookieconsent"):
        assert "MIT License" in (FRONTEND / "js" / "vendor" / f"{licence}.LICENSE").read_text(encoding="utf-8")


def test_la_politique_de_securite_n_autorise_plus_de_serveur_externe():
    reponse = app.test_client().get("/login")
    politique = reponse.headers["Content-Security-Policy"]
    for directive in ("script-src", "style-src", "font-src", "default-src"):
        valeur = next(d for d in politique.split(";") if d.strip().startswith(directive))
        assert "http" not in valeur, valeur
    assert "jsdelivr" not in politique


def test_la_fenetre_des_cookies_annonce_les_vraies_durees_de_session():
    import auth
    reponse = app.test_client().get("/api/settings/public")
    session = reponse.get_json()["session"]
    assert session == {"maxHours": auth.SESSION_MAX_HOURS, "idleMinutes": auth.SESSION_IDLE_MINUTES}
    source = (FRONTEND / "js" / "branding.js").read_text(encoding="utf-8")
    assert "session navigateur" not in source  # l'ancien texte, faux depuis la 3.67.3
