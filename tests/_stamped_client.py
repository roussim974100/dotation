"""Client de test dont `session_transaction` complete la session comme une vraie connexion.

Les tests posent `session["user"]` a la main : sans l'empreinte du mot de passe et les dates de connexion, le controle de
validite des sessions (auth.enforce_session_validity) les refuserait. Un test qui veut une session perimee ecrit lui-meme
`login_at` / `pwd_fp` : on n'ecrase rien. Utilise par tests/conftest.py et par le sous-processus tests/_http_scenarios.py.
"""
import time
from contextlib import contextmanager

from flask.testing import FlaskClient


def install(app):
    import auth  # resolu a l'appel : certains scenarios remplacent auth.get_user_record

    class StampedSessionClient(FlaskClient):
        @contextmanager
        def session_transaction(self, *args, **kwargs):
            with super().session_transaction(*args, **kwargs) as flask_session:
                yield flask_session
                username = flask_session.get("user")
                if username and "login_at" not in flask_session:
                    with app.app_context():
                        record = auth.get_user_record(username)
                        flask_session["pwd_fp"] = auth.password_fingerprint(record["password_hash"]) if record else ""
                    now = int(time.time())
                    flask_session["login_at"] = now
                    flask_session["last_seen"] = now

    app.test_client_class = StampedSessionClient
