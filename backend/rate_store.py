"""Compteur de limitation de debit PARTAGE entre les processus (gunicorn -w N) et conserve au redemarrage.

Sans lui, chaque processus comptait ses propres tentatives : avec 4 workers la limite de 10 essais de connexion
devenait 40. Les tentatives sont stockees dans users.db (table `rate_limit_hits`).

En cas d'erreur de base (verrou prolonge, disque plein), on retombe sur un compteur en memoire : la limitation
reste active pour le processus, et surtout la connexion n'est jamais bloquee par une panne du compteur.
"""
import sqlite3
import threading
import time

from config import DB_USERS_PATH

_lock = threading.Lock()
_memory = {}
_schema_ready = set()
_calls = 0
_PURGE_EVERY = 500          # une purge globale toutes les N verifications
_PURGE_AFTER_SECONDS = 3600  # les lignes plus vieilles qu'une heure ne servent plus


def _connect(path=None):
    connection = sqlite3.connect(path or DB_USERS_PATH, timeout=5, check_same_thread=False, isolation_level=None)
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _ensure_schema(connection, path):
    if path in _schema_ready:
        return
    connection.execute(
        "CREATE TABLE IF NOT EXISTS rate_limit_hits (scope TEXT NOT NULL, key TEXT NOT NULL, ts REAL NOT NULL)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_hits ON rate_limit_hits (scope, key, ts)")
    _schema_ready.add(path)


def _hit_memory(scope, key, max_requests, window_seconds, now):
    with _lock:
        bucket = _memory.setdefault((scope, key), [])
        bucket[:] = [t for t in bucket if now - t < window_seconds]
        if len(bucket) >= max_requests:
            return True
        bucket.append(now)
        return False


def hit(scope, key, max_requests, window_seconds, now=None, path=None):
    """Enregistre une tentative et retourne True si la limite est depassee (la tentative n'est alors pas comptee)."""
    global _calls
    now = time.time() if now is None else now
    connection = None
    try:
        connection = _connect(path)
        _ensure_schema(connection, path or DB_USERS_PATH)
        connection.execute("BEGIN IMMEDIATE")  # verrou d'ecriture : comptage + insertion atomiques entre processus
        connection.execute("DELETE FROM rate_limit_hits WHERE scope = ? AND key = ? AND ts < ?", (scope, key, now - window_seconds))
        count = connection.execute("SELECT COUNT(*) FROM rate_limit_hits WHERE scope = ? AND key = ?", (scope, key)).fetchone()[0]
        limited = count >= max_requests
        if not limited:
            connection.execute("INSERT INTO rate_limit_hits (scope, key, ts) VALUES (?, ?, ?)", (scope, key, now))
        _calls += 1
        if _calls % _PURGE_EVERY == 0:
            connection.execute("DELETE FROM rate_limit_hits WHERE ts < ?", (now - _PURGE_AFTER_SECONDS,))
        connection.execute("COMMIT")
        return limited
    except sqlite3.Error:
        if connection is not None:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        return _hit_memory(scope, key, max_requests, window_seconds, now)
    finally:
        if connection is not None:
            connection.close()
