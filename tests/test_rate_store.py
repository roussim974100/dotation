"""Limitation de debit partagee entre processus (gunicorn -w N) et persistante."""
import subprocess
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

import rate_store


def test_limit_is_reached_then_released_after_the_window(tmp_path):
    db = str(tmp_path / "rl.db")
    results = [rate_store.hit("t1", "1.1.1.1", 3, 60, now=1000 + i, path=db) for i in range(5)]
    assert results == [False, False, False, True, True]
    assert rate_store.hit("t1", "1.1.1.1", 3, 60, now=1000 + 61 + 2, path=db) is False  # fenetre glissante


def test_counters_are_per_scope_and_per_key(tmp_path):
    db = str(tmp_path / "rl.db")
    for _ in range(3):
        rate_store.hit("login", "1.1.1.1", 3, 60, now=10, path=db)
    assert rate_store.hit("login", "1.1.1.1", 3, 60, now=11, path=db) is True
    assert rate_store.hit("login", "2.2.2.2", 3, 60, now=11, path=db) is False
    assert rate_store.hit("autre", "1.1.1.1", 3, 60, now=11, path=db) is False


def test_counter_survives_a_restart_and_is_shared_between_processes(tmp_path):
    """4 « workers » (processus distincts) tentent 5 connexions chacun avec une limite de 10 : 10 passent, pas 20."""
    db = str(tmp_path / "rl.db")
    code = (
        "import sys; sys.path.insert(0, %r); import rate_store, time;"
        "n = sum(1 for _ in range(5) if not rate_store.hit('login', '9.9.9.9', 10, 600, now=time.time(), path=%r));"
        "print(n)" % (backend_path, db)
    )
    processes = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(4)]
    allowed = sum(int(p.communicate()[0].strip()) for p in processes)
    assert allowed == 10


def test_falls_back_to_memory_when_the_database_is_unusable(tmp_path):
    bad = str(tmp_path / "dossier_inexistant" / "rl.db")
    rate_store._memory.clear()
    results = [rate_store.hit("fb", "3.3.3.3", 2, 60, now=50 + i, path=bad) for i in range(4)]
    assert results == [False, False, True, True]  # jamais d'exception : la connexion n'est pas bloquee par une panne


def test_login_uses_the_shared_store(monkeypatch):
    import auth
    calls = []
    monkeypatch.setattr(auth.rate_store, "hit", lambda *args, **kwargs: calls.append(args) or False)
    assert auth._is_login_rate_limited("4.4.4.4") is False
    assert calls == [("login", "4.4.4.4", 10, 600)]
