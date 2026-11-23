"""22/11 : l'ETag de GET /api/forms (liste) doit changer avec la version de l'application ET avec tout redémarrage
du serveur, pas seulement avec les données. Sans ça, une mise à jour qui change le CALCUL d'un résumé (ex. 3.74.3,
Progression/Pilotage réalistes en restitution) sans toucher `updated_at` des dossiers déjà en base servirait un 304
(donc des données périmées) tant qu'aucun de ces dossiers n'est resauvegardé — constaté en conditions réelles.
Second constat, plus embêtant : la version seule ne suffit pas en itération rapide (plusieurs correctifs du calcul
se sont succédé ce soir-là sous le même numéro de version avant qu'on pense à l'incrémenter) — d'où
`_PROCESS_BOOT_ID`, un identifiant régénéré à chaque chargement du module, qui invalide le cache à CHAQUE
redémarrage sans dépendre de la discipline de version."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app
import routes.forms as forms_routes

H = {"X-CSRF-Token": "jeton"}


def client_for(user="admin"):
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["user"] = user
        flask_session["csrf_token"] = "jeton"
    return client


def test_la_liste_repond_304_si_rien_n_a_change():
    client = client_for()
    first = client.get("/api/forms")
    etag = first.headers.get("ETag")
    assert etag
    second = client.get("/api/forms", headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_un_changement_de_version_invalide_le_cache_meme_sans_changement_de_donnees(monkeypatch):
    client = client_for()
    first = client.get("/api/forms")
    etag = first.headers.get("ETag")

    monkeypatch.setattr(forms_routes, "raw_version", lambda: "9.9.9-test")
    second = client.get("/api/forms", headers={"If-None-Match": etag})
    assert second.status_code == 200, "une version differente doit invalider le cache, pas renvoyer 304"


def test_un_redemarrage_invalide_le_cache_meme_sans_bump_de_version(monkeypatch):
    """`_PROCESS_BOOT_ID` (regenere a chaque chargement du module, donc a chaque redemarrage reel du serveur)
    doit a lui seul invalider le cache, independamment de raw_version() qui ne change pas forcement entre deux
    redemarrages successifs en cours d'iteration."""
    client = client_for()
    first = client.get("/api/forms")
    etag = first.headers.get("ETag")

    monkeypatch.setattr(forms_routes, "_PROCESS_BOOT_ID", "autre-processus")
    second = client.get("/api/forms", headers={"If-None-Match": etag})
    assert second.status_code == 200, "un nouveau processus (redemarrage) doit invalider le cache, pas renvoyer 304"
