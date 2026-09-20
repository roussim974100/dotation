"""Observabilité sans donnée personnelle : identifiant de requête, code d'erreur communicable, journal fichier structuré.

Objectif : quand un client rencontre une erreur, il communique un CODE court (« E-4F2A9C ») et l'éditeur retrouve la cause sans avoir
la base. Le code est déterministe (même défaut = même code) ; le journal ne contient que des types d'exception, des positions
dans le code (fichier:ligne:fonction), des routes, des statuts et des durées : JAMAIS de valeur saisie, de message brut ni de pile avec code source."""
import hashlib
import json
import logging
import logging.handlers
import os
import re
import time
import traceback
import uuid

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from config import DATA_DIR

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")  # accepte l'identifiant d'un proxy, refuse tout ce qui pourrait fausser le journal
LOG_DIR = os.path.join(DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "aquai.log")
_logger = logging.getLogger("aquai.events")


def _setup_logger():
    if _logger.handlers:
        return
    level = getattr(logging, os.environ.get("APP_LOG_LEVEL", "INFO").upper(), logging.INFO)
    _logger.setLevel(level)
    _logger.propagate = False
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
    except OSError:
        _logger.addHandler(logging.NullHandler())  # dossier non inscriptible : jamais un motif d'echec


def error_code(exc):
    """Code court et STABLE pour un défaut : dérivé du type d'exception et de l'endroit du code où elle survient."""
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    last = frames[-1] if frames else None
    where = f"{os.path.basename(last.filename)}:{last.name}" if last else "?"
    return "E-" + hashlib.sha1(f"{type(exc).__name__}|{where}".encode("utf-8")).hexdigest()[:6].upper()


def _frames(exc, limit=8):
    """Positions dans le code (fichier:ligne:fonction), sans texte de code source ni valeurs."""
    return [f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}" for f in traceback.extract_tb(exc.__traceback__)[-limit:]]


def log_event(kind, **fields):
    _setup_logger()
    record = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **fields}
    _logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def init_observability(app):
    _setup_logger()

    @app.before_request
    def _assign_request_id():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex[:12]
        g.request_started = time.time()

    @app.after_request
    def _echo_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        started = getattr(g, "request_started", None)
        if started is not None and response.status_code >= 500 and not getattr(g, "error_logged", False):
            log_event("http_5xx", rid=getattr(g, "request_id", ""), method=request.method, route=str(request.url_rule or request.path)[:120],
                      status=response.status_code, ms=int((time.time() - started) * 1000))
        return response

    @app.errorhandler(Exception)
    def _handle_unexpected(exc):
        if isinstance(exc, HTTPException):
            return exc  # 404, 405, 413... : reponses normales de Flask, inchangees
        code = error_code(exc)
        g.error_logged = True
        log_event("exception", code=code, rid=getattr(g, "request_id", ""), type=type(exc).__name__, method=request.method,
                  route=str(request.url_rule or request.path)[:120], frames=_frames(exc))
        payload = {"error": "internal_error", "code": code, "requestId": getattr(g, "request_id", ""),
                   "message": f"Une erreur est survenue. Communiquez ce code au support : {code}"}
        if request.path.startswith("/api/"):
            return jsonify(payload), 500
        return (f"<!doctype html><meta charset='utf-8'><title>Erreur</title><h1>Une erreur est survenue</h1>"
                f"<p>Communiquez ce code au support : <strong>{code}</strong></p>", 500, {"Content-Type": "text/html; charset=utf-8"})


def recent_events(limit=50):
    """Derniers événements du journal (déjà sans valeur personnelle) pour le paquet de diagnostic."""
    events = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as handle:
            for line in handle.readlines()[-limit:]:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return events
