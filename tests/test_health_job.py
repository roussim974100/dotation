"""Controle de sante quotidien : consigne au journal seulement s'il y a quelque chose a examiner ; desactivable."""
import sys
from pathlib import Path

backend_path = str(Path(__file__).parent.parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from models.health import start_daily_health_check


def test_desactive_quand_intervalle_nul():
    assert start_daily_health_check(0) is None
    assert start_daily_health_check(-1) is None


def test_fil_daemon_demarre_sans_bloquer(monkeypatch):
    import utils
    monkeypatch.setattr(utils, "single_instance_lock", lambda name, wait_seconds=0: object())  # verrou obtenu
    thread = start_daily_health_check(24, first_delay_seconds=3600)
    assert thread is not None and thread.daemon is True and thread.is_alive()


def test_un_seul_processus_lance_le_controle(monkeypatch):
    import utils
    monkeypatch.setattr(utils, "single_instance_lock", lambda name, wait_seconds=0: None)  # un autre worker le detient
    assert start_daily_health_check(24, first_delay_seconds=3600) is None
