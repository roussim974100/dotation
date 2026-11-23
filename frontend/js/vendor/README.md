# Bibliothèques embarquées

Copiées ici (et non chargées depuis un CDN) pour que l'application fonctionne sur un intranet sans accès à Internet.

| Fichier | Origine | Licence |
|---|---|---|
| `qrcode-generator.js` | [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) 1.4.4, Kazuhiko Arase | MIT (texte dans l'en-tête du fichier) |
| `bootstrap.bundle.min.js` + `../../css/vendor/bootstrap.min.css` | [Bootstrap](https://getbootstrap.com) 5.3.2 | MIT (`bootstrap.LICENSE`) |
| `chart.umd.min.js` | [Chart.js](https://www.chartjs.org) 4.4.2 (tableau de bord) | MIT (`chartjs.LICENSE`) |
| `cookieconsent.umd.js` + `../../css/vendor/cookieconsent.css` | [CookieConsent](https://github.com/orestbida/cookieconsent) 3.1.0, Orest Bida (fenêtre « Cookies ») | MIT (`cookieconsent.LICENSE`) |

Aucune page ne charge quoi que ce soit depuis un serveur externe (`tests/test_no_external_assets.py` le vérifie, la politique de sécurité
`Content-Security-Policy` de `backend/app.py` n'autorise que `'self'`).

Mise à jour d'une bibliothèque : télécharger la version voulue (`https://cdn.jsdelivr.net/npm/<paquet>@<version>/dist/...`, ou
`.../gh/orestbida/cookieconsent@<version>/dist/...`), remplacer le fichier, **changer le `?v=` sur les pages qui le chargent** (ou le
numéro dans `branding.js` pour CookieConsent), puis lancer `python tests/browser/check_cookies_hors_ligne.py` (Bootstrap, Chart.js,
CookieConsent) et `python tests/browser/check_signature_qr.py` (il décode réellement le QR affiché).

Piège connu : CookieConsent **ne s'affiche pas pour un robot** (`navigator.webdriver`, option `hideFromBots`). Un test Selenium doit masquer ce
drapeau (voir `check_cookies_hors_ligne.py`), sinon la fenêtre n'est jamais construite.
