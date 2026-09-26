# Bibliothèques embarquées

Copiées ici (et non chargées depuis un CDN) pour que l'application fonctionne sur un intranet sans accès à Internet.

| Fichier | Origine | Licence |
|---|---|---|
| `qrcode-generator.js` | [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) 1.4.4, Kazuhiko Arase | MIT (texte de licence dans l'en-tête du fichier) |

Mise à jour : télécharger la version voulue depuis `https://cdn.jsdelivr.net/npm/qrcode-generator@<version>/qrcode.js`, remplacer le
fichier, puis relancer `python tests/browser/check_signature_qr.py` (il décode réellement le QR affiché).
