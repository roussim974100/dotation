"""3.66.0 : le QR code des liens de signature est embarque (aucun CDN) et charge avant storage.js sur les quatre listes."""
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend"
LIST_PAGES = ("index.html", "assignments-completed.html", "restitutions-pending.html", "restitutions-completed.html")


def test_bibliotheque_embarquee_avec_sa_licence():
    library = (FRONTEND / "js" / "vendor" / "qrcode-generator.js").read_text(encoding="utf-8")
    assert "Kazuhiko Arase" in library and "MIT license" in library
    assert "function" in library and "createSvgTag" in library


def test_les_listes_chargent_la_bibliotheque_et_la_fenetre_avant_storage_js():
    for page in LIST_PAGES:
        html = (FRONTEND / page).read_text(encoding="utf-8")
        library, dialog, storage = (html.index(name) for name in ("js/vendor/qrcode-generator.js", "js/signature-qr.js", "js/storage.js"))
        assert library < dialog < storage, page
        assert "cdn" not in html[library - 60:library], page  # servie localement


def test_actions_du_menu_declarees():
    storage = (FRONTEND / "js" / "storage.js").read_text(encoding="utf-8")
    for name in ("showAssignmentSignatureQr", "showRestitutionSignatureQr", "data-signature-link-qr"):
        assert name in storage
