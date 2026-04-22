"""Script de seeding dev : supprime toutes les données et crée des dossiers propres.

Scénarios couverts :
  1.  Marie FONTAINE   — DSI        — Arrivée complète (PC, email, badge)      active
  2.  Thomas RENAUD    — Finances   — Arrivée (téléphone, badge, VPN)           active
  3.  Claire DUPONT    — DST        — Arrivée (PC, écran, badge)                active
  4.  Emma LEROY       — DRH        — Arrivée en cours, incomplet               draft
  5.  Robert MEYER     — Cabinet    — Arrivée élu (PC, badge, véhicule)         active
  6.  Paul LAMBERT     — DRH        — Changement de service (PC, badge)         active
  7.  Sophie VIDAL     — Accueil    — Mise à jour (téléphone, badge, email)     active
  8.  Julien LEBLANC   — Bâtiment  — Mutualisation ×2 PC portable              active
  9.  Hélène GERARD    — DST        — Mutualisation ×2 PC portable              active
  10. Antoine PERRIER  — Finances   — Mutualisation ×3 PC portable              active
  11. Lucie FAURE      — DRH        — Mutualisation ×3 PC portable              active
  12. Marc JOURDAIN    — Comm.      — Mutualisation ×3 PC portable              active
  13. Eric MOREAU      — Sports     — Sortie complète (badge, veste, clés)      returned
  14. Nathalie SIMON   — Accueil    — Sortie partielle (badge OK, clés manq.)   partial_return

Usage (depuis C:\\www\\dotation) :
    python scripts/seed_dev_dossiers.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("APP_SECRET_KEY", "dev-seed-secret")

from app import app          # noqa: E402
from database import get_db  # noqa: E402
from models.forms import persist_form  # noqa: E402
from models.pools import sync_shared_pools_for_form  # noqa: E402
from utils import utc_now  # noqa: E402

# ---------------------------------------------------------------------------
# IDs ressources catalogue
# ---------------------------------------------------------------------------
R_ORDI  = "resource_a3fb350b54c540afa4d879ccd247d053"
R_ECRAN = "resource_3ac95771a9614a3984b6b68efb90bd3c"
R_TEL   = "resource_ca8a784197674d31a2b560f20c394b7d"
R_VPN   = "resource_0a75caa443404255af96f4a27794dbd8"
R_EMAIL = "resource_0ec41573cfb94c67be0de75cc30ebb41"
R_BADGE = "resource_191259d4479646349ade32528ba773f3"
R_CLES  = "resource_e2723d7666cf4065a3f898fea3fae6de"
R_VESTE = "resource_9e0c709f18bc45e5b80cc5308cdd206d"
R_VEHIC = "resource_ae478036300c4bd6b559aaf24f1cfb25"

# ---------------------------------------------------------------------------
# Constructeurs de ressources
# ---------------------------------------------------------------------------

def res(rid, code, label, cat, fields, selected=True, shared=False, shared_with=None):
    return {"id": rid, "code": code, "label": label, "category": cat,
            "selected": selected, "fields": fields or {},
            "shared": shared, "sharedWith": shared_with or []}

def ordi(nom, marque, modele, sn, **kw):
    return res(R_ORDI, "ordinateur", "Ordinateur", "materiel",
               {"nomPoste": nom, "marque": marque, "modele": modele, "numeroSerie": sn}, **kw)

def ecran(marque, modele, sn):
    return res(R_ECRAN, "ecran", "Écran", "materiel",
               {"marque": marque, "modele": modele, "numeroSerie": sn})

def tel(nom, marque, modele, sn):
    return res(R_TEL, "telephone", "Téléphone", "materiel",
               {"nomTelephone": nom, "marque": marque, "modele": modele, "numeroSerie": sn})

def vpn(ident):
    return res(R_VPN, "vpn", "VPN (télétravail)", "immateriel", {"identifiant": ident})

def email(adr):
    return res(R_EMAIL, "email", "Email", "immateriel", {"adresse": adr})

def badge(num):
    return res(R_BADGE, "badge", "Badge d'accès", "materiel", {"numero": num})

def cles(liste):
    return res(R_CLES, "cles", "Clé(s)", "materiel", {"values": liste})

def veste():
    return res(R_VESTE, "veste", "Veste", "materiel", {})

def vehicule(marque, modele, immat):
    return res(R_VEHIC, "vehicule", "Véhicule", "materiel",
               {"marque": marque, "modele": modele, "immatriculation": immat})

# ---------------------------------------------------------------------------
# Constructeur de payload
# ---------------------------------------------------------------------------

def payload(nom, prenom, service, qualite, fonction, dtype, resources, rgpd=True, extra=None):
    return {
        "meta": {"startAt": "2026-04-15"},
        "dossier": {"type": dtype, **(extra or {})},
        "beneficiaire": {"nom": nom, "prenom": prenom, "service": service,
                         "qualite": qualite, "fonction": fonction, "mandat": ""},
        "resources": {"additional": resources},
        "validation": {"rgpdAccepted": rgpd},
    }

def save(p):
    return persist_form(p)["summary"]["id"]

# ---------------------------------------------------------------------------
# Phase 1 — création des dossiers (persist_form gère ses propres connexions)
# ---------------------------------------------------------------------------

def seed_forms():
    ids = {}

    ids["fontaine"] = save(payload(
        "FONTAINE", "Marie", "DSI", "agent", "Administratrice systèmes", "arrivee",
        [ordi("PC-DSI-MF01", "Dell", "Latitude 5540", "SN-MF-001"),
         email("m.fontaine@mairie.fr"), badge("1042")],
    ))
    print(f"  1.  Marie FONTAINE   (DSI/active)             → {ids['fontaine']}")

    ids["renaud"] = save(payload(
        "RENAUD", "Thomas", "Finances", "agent", "Contrôleur de gestion", "arrivee",
        [tel("TEL-TH-01", "Apple", "iPhone 14", "IMEI-TR-001"),
         badge("2087"), vpn("trenaud")],
    ))
    print(f"  2.  Thomas RENAUD    (Finances/active)         → {ids['renaud']}")

    ids["dupont"] = save(payload(
        "DUPONT", "Claire", "DST", "agent", "Technicienne voirie", "arrivee",
        [ordi("PC-DST-CD01", "HP", "EliteBook 840", "SN-CD-001"),
         ecran("Dell", "P2422H", "SN-ECR-001"), badge("3015")],
    ))
    print(f"  3.  Claire DUPONT    (DST/active)              → {ids['dupont']}")

    ids["leroy"] = save(payload(
        "LEROY", "Emma", "DRH", "agent", "Chargée de recrutement", "arrivee",
        [ordi("", "Lenovo", "", ""), badge("")],
        rgpd=False,
    ))
    print(f"  4.  Emma LEROY       (DRH/draft)               → {ids['leroy']}")

    ids["meyer"] = save(payload(
        "MEYER", "Robert", "Cabinet du Maire", "elu", "Adjoint à la culture", "arrivee",
        [ordi("PC-ELU-RM01", "Apple", "MacBook Air M2", "SN-RM-001"),
         badge("0042"), vehicule("Renault", "Zoé", "AA-001-BB")],
    ))
    print(f"  5.  Robert MEYER     (Cabinet/élu/active)      → {ids['meyer']}")

    ids["lambert"] = save(payload(
        "LAMBERT", "Paul", "DRH", "agent", "Responsable formation", "changement_service",
        [ordi("PC-DRH-PL01", "HP", "ProBook 450", "SN-PL-001"), badge("1876")],
        extra={"serviceDestination": "DRH"},
    ))
    print(f"  6.  Paul LAMBERT     (changement service)      → {ids['lambert']}")

    ids["vidal"] = save(payload(
        "VIDAL", "Sophie", "Accueil", "agent", "Agente d'accueil", "mise_a_jour",
        [tel("TEL-SV-01", "Samsung", "Galaxy S23", "IMEI-SV-001"),
         badge("4521"), email("s.vidal@mairie.fr")],
    ))
    print(f"  7.  Sophie VIDAL     (mise à jour/active)      → {ids['vidal']}")

    # Mutualisation ×2 — créés sans sharedWith d'abord (IDs inconnus)
    ids["leblanc"] = save(payload(
        "LEBLANC", "Julien", "Bâtiment", "agent", "Technicien bâtiment", "arrivee",
        [badge("5102"), email("j.leblanc@mairie.fr")],
    ))
    ids["gerard"] = save(payload(
        "GERARD", "Hélène", "DST", "agent", "Ingénieure travaux", "arrivee",
        [badge("5203"), email("h.gerard@mairie.fr")],
    ))
    print(f"  8.  Julien LEBLANC   (Bâtiment/mutu×2)        → {ids['leblanc']}")
    print(f"  9.  Hélène GERARD    (DST/mutu×2)              → {ids['gerard']}")

    # Mutualisation ×3
    ids["perrier"] = save(payload(
        "PERRIER", "Antoine", "Finances", "agent", "Analyste financier", "arrivee",
        [badge("6101"), email("a.perrier@mairie.fr"), vpn("aperrier")],
    ))
    ids["faure"] = save(payload(
        "FAURE", "Lucie", "DRH", "agent", "Gestionnaire paie", "arrivee",
        [badge("6202"), email("l.faure@mairie.fr"), vpn("lfaure")],
    ))
    ids["jourdain"] = save(payload(
        "JOURDAIN", "Marc", "Communication", "agent", "Chargé de communication", "arrivee",
        [badge("6303"), email("m.jourdain@mairie.fr"), vpn("mjourdain")],
    ))
    print(f" 10.  Antoine PERRIER  (Finances/mutu×3)         → {ids['perrier']}")
    print(f" 11.  Lucie FAURE      (DRH/mutu×3)              → {ids['faure']}")
    print(f" 12.  Marc JOURDAIN    (Communication/mutu×3)    → {ids['jourdain']}")

    ids["moreau"] = save(payload(
        "MOREAU", "Eric", "Sports", "agent", "Éducateur sportif", "sortie",
        [badge("7001"), veste(), cles(["Bâtiment B", "Vestiaire 12"])],
    ))
    print(f" 13.  Eric MOREAU      (Sports/sortie complète)  → {ids['moreau']}")

    ids["simon"] = save(payload(
        "SIMON", "Nathalie", "Accueil", "agent", "Hôtesse d'accueil", "sortie",
        [badge("8002"), cles(["Salle des fêtes", "Local technique"])],
    ))
    print(f" 14.  Nathalie SIMON   (Accueil/sortie partielle)→ {ids['simon']}")

    return ids

# ---------------------------------------------------------------------------
# Phase 2 — post-traitement : pools, statuts, items restitution
# ---------------------------------------------------------------------------

def setup_pool(conn, owner_id, resource_obj, other_members):
    """Crée un pool et injecte la ressource dans les dossiers membres."""
    row = conn.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (owner_id,)).fetchone()
    p = json.loads(row["payload_json"])
    p["resources"]["additional"].insert(0, resource_obj)
    conn.execute("UPDATE dotation_forms SET payload_json = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(p, ensure_ascii=False), utc_now(), owner_id))

    sync_shared_pools_for_form(conn, owner_id, p["resources"]["additional"])

    # Récupérer le poolId créé
    pool_row = conn.execute(
        "SELECT p.id FROM shared_pools p JOIN shared_pool_members m ON m.pool_id = p.id WHERE m.form_id = ?",
        (owner_id,)
    ).fetchone()
    if not pool_row:
        return

    pool_id = pool_row["id"]

    # Injecter poolId dans tous les membres
    for fid in [owner_id] + [m["formId"] for m in other_members]:
        row = conn.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (fid,)).fetchone()
        p = json.loads(row["payload_json"])
        for r in p["resources"]["additional"]:
            if r.get("id") == R_ORDI:
                r["poolId"] = pool_id
        conn.execute("UPDATE dotation_forms SET payload_json = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(p, ensure_ascii=False), utc_now(), fid))


def force_status(conn, form_id, status):
    row = conn.execute("SELECT payload_json FROM dotation_forms WHERE id = ?", (form_id,)).fetchone()
    p = json.loads(row["payload_json"])
    p.setdefault("workflow", {})["status"] = status
    conn.execute("UPDATE dotation_forms SET payload_json = ?, status = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(p, ensure_ascii=False), status, utc_now(), form_id))


def add_items(conn, form_id, returned, missing=None):
    for item in returned:
        conn.execute(
            """INSERT INTO dotation_items
               (form_id, item_key, category, label, assigned, returned, returned_at,
                return_condition, notes, details_json)
               VALUES (?, ?, ?, ?, 1, 1, '2026-04-20', 'bon', '', '{}')""",
            (form_id, item[0], item[1], item[2]),
        )
    for item in (missing or []):
        conn.execute(
            """INSERT INTO dotation_items
               (form_id, item_key, category, label, assigned, returned, returned_at,
                return_condition, notes, details_json)
               VALUES (?, ?, ?, ?, 1, 0, NULL, NULL, 'Non restitué', '{}')""",
            (form_id, item[0], item[1], item[2]),
        )


def seed_post(conn, ids):

    # --- Mutualisation ×2 : Julien ↔ Hélène ---
    id8, id9 = ids["leblanc"], ids["gerard"]
    setup_pool(conn, id8,
        ordi("PC-POOL-A", "Lenovo", "ThinkPad X1 Carbon", "SN-POOL-A",
             shared=True,
             shared_with=[{"formId": id9, "nom": "GERARD", "prenom": "Hélène", "service": "DST"}]),
        other_members=[{"formId": id9}],
    )

    # --- Mutualisation ×3 : Antoine, Lucie, Marc ---
    id10, id11, id12 = ids["perrier"], ids["faure"], ids["jourdain"]
    members_B = [
        {"formId": id10, "nom": "PERRIER",  "prenom": "Antoine", "service": "Finances"},
        {"formId": id11, "nom": "FAURE",    "prenom": "Lucie",   "service": "DRH"},
        {"formId": id12, "nom": "JOURDAIN", "prenom": "Marc",    "service": "Communication"},
    ]
    setup_pool(conn, id10,
        ordi("PC-POOL-B", "Dell", "Latitude 5430", "SN-POOL-B",
             shared=True,
             shared_with=[m for m in members_B if m["formId"] != id10]),
        other_members=[{"formId": id11}, {"formId": id12}],
    )

    # --- Forcer "active" sur les dossiers complets (hors draft et sorties) ---
    for key in ["fontaine", "renaud", "dupont", "meyer", "lambert",
                "vidal", "leblanc", "gerard", "perrier", "faure", "jourdain"]:
        force_status(conn, ids[key], "active")

    # --- Sortie complète ---
    add_items(conn, ids["moreau"],
        returned=[(R_BADGE, "materiel", "Badge d'accès"),
                  (R_VESTE, "materiel", "Veste"),
                  (R_CLES,  "materiel", "Clé(s)")],
    )
    force_status(conn, ids["moreau"], "returned")

    # --- Sortie partielle ---
    add_items(conn, ids["simon"],
        returned=[(R_BADGE, "materiel", "Badge d'accès")],
        missing=[(R_CLES, "materiel", "Clé(s)")],
    )
    force_status(conn, ids["simon"], "partial_return")

    print("  Pools et statuts configurés.")


# ---------------------------------------------------------------------------
# Nettoyage
# ---------------------------------------------------------------------------

def clean_all(conn):
    for table in ["shared_pool_items", "shared_pool_members", "shared_pools",
                  "dotation_items", "audit_events", "deleted_items",
                  "signature_links", "dotation_forms"]:
        conn.execute(f"DELETE FROM {table}")
    print("  Base nettoyée.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with app.test_request_context():
        with get_db() as conn:
            print("\n=== Nettoyage ===")
            clean_all(conn)

        print("\n=== Création des dossiers ===")
        ids = seed_forms()

        with get_db() as conn:
            print("\n=== Configuration pools et statuts ===")
            seed_post(conn, ids)

    print(f"\nDone — {len(ids)} dossiers créés.")


if __name__ == "__main__":
    main()
