"""Outil de test navigateur (Selenium + Chrome sans interface) sur une instance ISOLEE :
base temporaire (APP_DATA_DIR), serveur sur un port libre, session administrateur injectee par cookie signe.

    python tests/browser/browser_harness.py            # demarre, puis attend (Ctrl+C) : usage interactif
Usage en bibliotheque :
    with Instance(copy_db="backend/dotation.db") as inst:
        driver = inst.driver(width=1366)
        driver.get(inst.url("/index.html"))

Aucune vraie base n'est modifiee : la base source n'est que COPIEE dans le dossier temporaire.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class Instance:
    def __init__(self, copy_db=None, port=5055, user="admin", env=None):
        self.extra_env = env or {}
        self.copy_db = copy_db
        self.port = port
        self.user = user
        self.dir = None
        self.process = None
        self._drivers = []

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="aquai_browser_")
        if self.copy_db:
            source = sqlite3.connect(str(ROOT / self.copy_db))
            target = sqlite3.connect(os.path.join(self.dir, "dotation.db"))
            source.backup(target)  # copie coherente (WAL compris) ; la source n'est jamais modifiee
            target.close()
            source.close()
        env = dict(os.environ, **self.extra_env, APP_DATA_DIR=self.dir, APP_CUSTOM_BRANDING_DIR=os.path.join(self.dir, "branding"), PYTHONIOENCODING="utf-8")
        code = f"import sys; sys.path.insert(0, r'{ROOT / 'backend'}'); import app; app.app.run(host='127.0.0.1', port={self.port}, debug=False, threaded=True)"
        self.log = open(os.path.join(self.dir, "server.log"), "w", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-c", code], cwd=str(ROOT), env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                urllib.request.urlopen(self.url("/login"), timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("serveur isole injoignable : " + open(os.path.join(self.dir, "server.log"), encoding="utf-8").read()[-800:])
        return self

    def __exit__(self, *exc):
        for driver in self._drivers:
            try:
                driver.quit()
            except Exception:
                pass
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except Exception:
                self.process.kill()
        self.log.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def url(self, path="/"):
        return f"http://127.0.0.1:{self.port}{path}"

    def session_cookie(self):
        """Cookie de session Flask signe avec la cle secrete de l'instance isolee (aucun mot de passe utilise)."""
        env_code = (
            "import sys, json; sys.path.insert(0, r'%s'); import app;"
            "s = app.app.session_interface.get_signing_serializer(app.app);"
            "print(s.dumps({'user': %r, 'csrf_token': 'jeton-navigateur'}))" % (ROOT / "backend", self.user)
        )
        env = dict(os.environ, **self.extra_env, APP_DATA_DIR=self.dir, APP_CUSTOM_BRANDING_DIR=os.path.join(self.dir, "branding"), PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, "-c", env_code], cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8")
        return out.stdout.strip().splitlines()[-1]

    def driver(self, width=1366, height=900):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument(f"--window-size={width},{height}")
        options.add_argument("--force-device-scale-factor=1")
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        options.binary_location = CHROME
        driver = webdriver.Chrome(options=options)
        self._drivers.append(driver)
        driver.get(self.url("/login"))
        driver.add_cookie({"name": "publier_session", "value": self.session_cookie(), "path": "/"})
        return driver

    def console_errors(self, driver):
        return [e["message"] for e in driver.get_log("browser") if e["level"] in ("SEVERE",)]


if __name__ == "__main__":
    with Instance(copy_db="backend/dotation.db") as instance:
        print("Instance isolee sur", instance.url("/"), "- Ctrl+C pour arreter")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
