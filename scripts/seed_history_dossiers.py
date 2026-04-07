"""
Cree des dossiers pour les vues Suivi des dossiers et Suivi des restitutions.
- Suivi dossiers = status "active" sans restitution
- Suivi restitutions = status "returned"
Usage : python scripts/seed_history_dossiers.py
"""

import requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()

csrf = s.get(f"{BASE}/api/csrf-token").json()["token"]
s.post(f"{BASE}/login", data={
    "username": "claude.test",
    "password": "ClaudeTest@2026!",
    "csrf_token": csrf,
})

FAKE_SIG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAA"
    "fFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
created = []


def create(payload, label):
    r = s.post(f"{BASE}/api/forms", json=payload)
    if r.status_code == 201:
        fid = r.json()["summary"]["id"]
        status = r.json()["summary"]["status"]
        created.append((fid, label, status))
        print(f"  OK  [{status:22s}] {label}")
    else:
        print(f"  ERR {label} -> {r.status_code} {r.text[:120]}")


# =========================================================================
# Helpers
# =========================================================================

def active_dossier(nom, prenom, service, fonction, materiel, immateriel=None,
                   dossier_type="arrivee", qualite="agent", mandat=None,
                   start_at=None, unc_acces=None, unc_ref_ad=None):
    """Genere un payload complet qui sera calcule comme 'active'."""
    p = {
        "beneficiaire": {"nom": nom, "prenom": prenom, "qualite": qualite,
                         "service": service, "fonction": fonction},
        "dossier": {"type": dossier_type},
        "materiel": materiel,
        "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
        "workflow": {"status": "active"},
    }
    if mandat:
        p["beneficiaire"]["mandat"] = mandat
    if immateriel:
        p["immateriel"] = immateriel
    if start_at:
        p.setdefault("meta", {})["startAt"] = start_at
    if unc_acces:
        p["unc_acces"] = unc_acces
    if unc_ref_ad:
        p["unc_ref_ad"] = unc_ref_ad
    return p


# =========================================================================
# SUIVI DES DOSSIERS (active, sans restitution)
# =========================================================================
print("\n=== SUIVI DES DOSSIERS (active) ===\n")

create(active_dossier(
    "VIDAL", "Francoise", "Finances", "Directrice financiere",
    materiel={
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 7450",
                       "numeroSerie": "SN-DELL-FIN-01", "assignedAt": "2026-01-10"},
        "ecran": {"selected": True, "marque": "Dell", "modele": "U2723QE",
                  "numeroSerie": "SN-DELL-FIN-02", "assignedAt": "2026-01-10"},
        "badge": {"selected": True, "numero": "B-2026-FIN-01", "assignedAt": "2026-01-10"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "francoise.vidal@example.fr", "assignedAt": "2026-01-10"},
        "vpn": {"selected": True, "identifiant": "fvidal", "assignedAt": "2026-01-10"},
    },
    start_at="2026-01-15",
), "H1. Active — Agent finances, ordi+ecran+badge+email+vpn")

create(active_dossier(
    "CHEVALIER", "Pierre", "Police municipale", "Chef de service",
    materiel={
        "telephone": {"selected": True, "marque": "Samsung", "modele": "Galaxy XCover7",
                      "imei": "350000111222333", "assignedAt": "2025-11-01"},
        "vehicule": {"selected": True, "marque": "Renault", "modele": "Megane E-Tech",
                     "immatriculation": "KL-012-MN", "assignedAt": "2025-11-01"},
        "badge": {"selected": True, "numero": "B-2025-PM-01", "assignedAt": "2025-11-01"},
        "veste": {"selected": True, "assignedAt": "2025-11-01"},
        "chaussuresSecurite": {"selected": True, "assignedAt": "2025-11-01"},
    },
    start_at="2025-11-15",
), "H2. Active — PM, telephone+vehicule+badge+veste+chaussures")

create(active_dossier(
    "GUILLOT", "Marc", "Direction generale", "DGS",
    materiel={
        "ordinateur": {"selected": True, "marque": "Apple", "modele": "MacBook Pro 16",
                       "numeroSerie": "SN-APPLE-DG-01", "assignedAt": "2025-06-01"},
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 16 Pro",
                      "imei": "440000999888777", "assignedAt": "2025-06-01"},
        "tablette": {"selected": True, "marque": "Apple", "modele": "iPad Pro 13",
                     "numeroSerie": "SN-IPAD-DG-01", "assignedAt": "2025-06-01"},
        "badge": {"selected": True, "numero": "B-2025-DG-01", "assignedAt": "2025-06-01"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "marc.guillot@example.fr", "assignedAt": "2025-06-01"},
        "vpn": {"selected": True, "identifiant": "mguillot", "assignedAt": "2025-06-01"},
    },
    start_at="2025-06-15",
    unc_acces=[
        {"chemin": "\\\\SRVFIC01\\Direction", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC01\\Commun", "acces": "lecture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC01\\Budget", "acces": "lecture",
         "statut": "provisionne", "commentaire": ""},
    ],
    unc_ref_ad="mguillot@example.local",
), "H3. Active — DGS, Apple full + 3 UNC")

create(active_dossier(
    "RENAUD", "Sylvie", "Petite enfance", "ATSEM",
    materiel={
        "badge": {"selected": True, "numero": "B-2026-PE-05", "assignedAt": "2026-01-28"},
        "cles": {"selected": True, "values": ["Cle ecole maternelle", "Cle cantine"], "assignedAt": "2026-01-28"},
    },
    start_at="2026-02-01",
), "H4. Active — ATSEM, badge + cles seulement")

create(active_dossier(
    "BRUN", "Henri", "Espaces verts", "Agent polyvalent",
    materiel={
        "vehicule": {"selected": True, "marque": "Renault", "modele": "Master",
                     "immatriculation": "OP-345-QR", "assignedAt": "2025-08-28"},
        "badge": {"selected": True, "numero": "B-2025-EV-03", "assignedAt": "2025-08-28"},
        "cles": {"selected": True, "values": ["Cle depot", "Cle vestiaire"], "assignedAt": "2025-08-28"},
        "veste": {"selected": True, "assignedAt": "2025-08-28"},
        "chaussuresSecurite": {"selected": True, "assignedAt": "2025-08-28"},
    },
    start_at="2025-09-01",
), "H5. Active — Agent terrain, vehicule+badge+cles+EPI")

create(active_dossier(
    "LEROUX", "Corinne", None, None,
    qualite="elu", mandat="Maire adjointe - Culture",
    materiel={
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 15",
                      "imei": "550000123456789", "assignedAt": "2025-07-01"},
        "tablette": {"selected": True, "marque": "Apple", "modele": "iPad Air",
                     "numeroSerie": "SN-IPAD-ELU-01", "assignedAt": "2025-07-01"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "corinne.leroux@example.fr", "assignedAt": "2025-07-01"},
    },
    start_at="2025-07-01",
), "H6. Active — Elue, telephone+tablette+email")

create(active_dossier(
    "PICARD", "Jacques", None, None,
    qualite="elu", mandat="Conseiller municipal - Sport",
    materiel={
        "telephone": {"selected": True, "marque": "Samsung", "modele": "Galaxy A55",
                      "imei": "660000987654321", "assignedAt": "2025-10-01"},
    },
    start_at="2025-10-01",
), "H7. Active — Elu, telephone seul")

create(active_dossier(
    "NGUYEN", "Thi", "Informatique", "Developpeur",
    materiel={
        "ordinateur": {"selected": True, "marque": "Lenovo", "modele": "ThinkPad X1 Carbon",
                       "numeroSerie": "SN-LEN-DSI-05", "assignedAt": "2026-03-01"},
        "ecran": {"selected": True, "marque": "Dell", "modele": "U3423WE",
                  "numeroSerie": "SN-DELL-DSI-ECR-05", "assignedAt": "2026-03-01"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "thi.nguyen@example.fr", "assignedAt": "2026-03-01"},
        "vpn": {"selected": True, "identifiant": "tnguyen", "assignedAt": "2026-03-01"},
    },
    start_at="2026-03-15",
    unc_acces=[
        {"chemin": "\\\\SRVFIC01\\Services\\DSI", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC02\\Developpement", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC01\\Commun", "acces": "lecture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC02\\Sauvegarde\\Dev", "acces": "lecture",
         "statut": "en_cours", "commentaire": "Demande recente"},
    ],
    unc_ref_ad="tnguyen@example.local",
), "H8. Active — Dev, ordi+ecran+email+vpn + 4 UNC")

create(active_dossier(
    "MARTINEZ", "Rosa", "Etat civil", "Agent d'accueil",
    dossier_type="changement_service",
    materiel={
        "ordinateur": {"selected": True, "marque": "HP", "modele": "ProDesk 400",
                       "numeroSerie": "SN-HP-EC-03", "assignedAt": "2026-02-15"},
        "badge": {"selected": True, "numero": "B-2026-EC-03", "assignedAt": "2026-02-15"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "rosa.martinez@example.fr", "assignedAt": "2026-02-15"},
    },
    start_at="2026-03-01",
), "H9. Active — Changement de service")

create(active_dossier(
    "DUPUIS", "Laurent", "Communication", "Responsable",
    dossier_type="mise_a_jour",
    materiel={
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 5550",
                       "numeroSerie": "SN-DELL-COM-01", "assignedAt": "2026-03-20"},
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 15 Pro",
                      "imei": "770000111222333", "assignedAt": "2026-03-20"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "laurent.dupuis@example.fr", "assignedAt": "2026-03-20"},
    },
    start_at="2026-03-25",
), "H10. Active — Mise a jour (nouveau telephone)")


# =========================================================================
# SUIVI DES RESTITUTIONS (returned)
# =========================================================================
print("\n=== SUIVI DES RESTITUTIONS (returned) ===\n")

def returned_dossier(nom, prenom, service, fonction, materiel, immateriel=None,
                     restitution_items=None, returned_at="2026-03-15",
                     reason="Depart", notes="", qualite="agent"):
    p = {
        "beneficiaire": {"nom": nom, "prenom": prenom, "qualite": qualite,
                         "service": service, "fonction": fonction},
        "dossier": {"type": "sortie"},
        "materiel": materiel,
        "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
        "workflow": {"status": "returned"},
        "restitution": {
            "returnedAt": returned_at,
            "reason": reason,
            "notes": notes,
            "items": restitution_items or {},
        },
    }
    if immateriel:
        p["immateriel"] = immateriel
    return p


create(returned_dossier(
    "PERRIN", "Michele", "Accueil", "Hotesse d'accueil",
    materiel={
        "ordinateur": {"selected": True, "marque": "HP", "modele": "ProDesk",
                       "numeroSerie": "SN-HP-ACC-05", "assignedAt": "2022-09-01"},
        "badge": {"selected": True, "numero": "B-2022-ACC-05"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "michele.perrin@example.fr"},
    },
    restitution_items={
        "ordinateur": {"state": "returned", "returnedAt": "2026-02-28", "notes": "Bon etat"},
        "badge": {"state": "returned", "returnedAt": "2026-02-28", "notes": ""},
        "email": {"state": "returned", "returnedAt": "2026-02-28", "notes": "Compte supprime"},
    },
    returned_at="2026-02-28",
    reason="Retraite",
    notes="Depart apres 4 ans de service",
), "R1. Returned — Retraite, tout conforme")

create(returned_dossier(
    "CARON", "Didier", "Voirie", "Cantonnier",
    materiel={
        "vehicule": {"selected": True, "marque": "Renault", "modele": "Kangoo",
                     "immatriculation": "ST-678-UV"},
        "badge": {"selected": True, "numero": "B-2023-VOI-07"},
        "veste": {"selected": True},
        "chaussuresSecurite": {"selected": True},
        "cles": {"selected": True, "values": ["Cle depot voirie", "Cle portail"]},
    },
    restitution_items={
        "vehicule": {"state": "returned", "returnedAt": "2026-03-10", "notes": "Rayure aile droite"},
        "badge": {"state": "returned", "returnedAt": "2026-03-10", "notes": ""},
        "veste": {"state": "returned_damaged", "returnedAt": "2026-03-10", "notes": "Dechirure epaule"},
        "chaussuresSecurite": {"state": "returned_damaged", "returnedAt": "2026-03-10",
                                "notes": "Semelles usees, a jeter"},
        "cles": {"state": "returned", "returnedAt": "2026-03-10", "notes": "2 cles rendues"},
    },
    returned_at="2026-03-10",
    reason="Mutation autre commune",
    notes="Materiel use mais rendu complet, veste et chaussures HS",
), "R2. Returned — Mutation, materiel degrade (veste+chaussures)")

create(returned_dossier(
    "FLEURY", "Agathe", "Bibliotheque", "Mediatrice culturelle",
    materiel={
        "ordinateur": {"selected": True, "marque": "Lenovo", "modele": "ThinkCentre M70q",
                       "numeroSerie": "SN-LEN-BIB-03", "assignedAt": "2024-01-15"},
        "badge": {"selected": True, "numero": "B-2024-BIB-03"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "agathe.fleury@example.fr"},
    },
    restitution_items={
        "ordinateur": {"state": "returned", "returnedAt": "2026-01-31", "notes": "RAS"},
        "badge": {"state": "returned", "returnedAt": "2026-01-31", "notes": ""},
        "email": {"state": "returned", "returnedAt": "2026-01-31", "notes": "Desactive"},
    },
    returned_at="2026-01-31",
    reason="Fin de CDD",
), "R3. Returned — Fin CDD, tout conforme")

create(returned_dossier(
    "COLLIN", "Bruno", "DSI", "Administrateur systeme",
    materiel={
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Precision 5680",
                       "numeroSerie": "SN-DELL-DSI-10", "assignedAt": "2023-06-01"},
        "ecran": {"selected": True, "marque": "Dell", "modele": "U3423WE",
                  "numeroSerie": "SN-DELL-DSI-ECR-10", "assignedAt": "2023-06-01"},
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 14",
                      "imei": "880000444555666", "assignedAt": "2023-06-01"},
        "badge": {"selected": True, "numero": "B-2023-DSI-10"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "bruno.collin@example.fr"},
        "vpn": {"selected": True, "identifiant": "bcollin"},
    },
    restitution_items={
        "ordinateur": {"state": "returned", "returnedAt": "2026-03-20", "notes": "Reinstalle"},
        "ecran": {"state": "returned", "returnedAt": "2026-03-20", "notes": ""},
        "telephone": {"state": "returned", "returnedAt": "2026-03-20", "notes": ""},
        "badge": {"state": "returned", "returnedAt": "2026-03-20", "notes": ""},
        "email": {"state": "returned", "returnedAt": "2026-03-20", "notes": "Supprime AD"},
        "vpn": {"state": "returned", "returnedAt": "2026-03-20", "notes": "Certificat revoque"},
    },
    returned_at="2026-03-20",
    reason="Demission",
    notes="Poste sensible, tous les acces revoques le jour meme",
), "R4. Returned — DSI demission, 6 ressources rendues")

create(returned_dossier(
    "MOREL", "Genevieve", None, None, qualite="elu",
    materiel={
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 15",
                      "imei": "990000123456789", "assignedAt": "2024-07-01"},
        "tablette": {"selected": True, "marque": "Apple", "modele": "iPad Air M2",
                     "numeroSerie": "SN-IPAD-ELU-05", "assignedAt": "2024-07-01"},
    },
    restitution_items={
        "telephone": {"state": "returned", "returnedAt": "2026-03-25", "notes": ""},
        "tablette": {"state": "returned", "returnedAt": "2026-03-25", "notes": "Avec housse"},
    },
    returned_at="2026-03-25",
    reason="Fin de mandat",
    notes="Elections mars 2026 — mandat non renouvele",
), "R5. Returned — Elu fin de mandat, telephone+tablette")

create(returned_dossier(
    "VASSEUR", "Eric", "Sports", "Maitre nageur",
    materiel={
        "badge": {"selected": True, "numero": "B-2024-SPO-09"},
        "cles": {"selected": True, "values": ["Cle piscine", "Cle local technique", "Cle vestiaire MNS"]},
        "veste": {"selected": True},
    },
    restitution_items={
        "badge": {"state": "returned", "returnedAt": "2026-02-15", "notes": ""},
        "cles": {"state": "returned", "returnedAt": "2026-02-15", "notes": "3 cles rendues"},
        "veste": {"state": "returned", "returnedAt": "2026-02-15", "notes": ""},
    },
    returned_at="2026-02-15",
    reason="Mobilite interne vers service jeunesse",
    notes="Transfert de poste, pas de nouveau materiel attribue",
), "R6. Returned — Mobilite interne, badge+cles+veste")

create(returned_dossier(
    "BOUCHER", "Christiane", "Petite enfance", "Auxiliaire puericulture",
    materiel={
        "badge": {"selected": True, "numero": "B-2021-PE-11"},
        "cles": {"selected": True, "values": ["Cle creche Papillons"]},
    },
    restitution_items={
        "badge": {"state": "returned", "returnedAt": "2026-01-10", "notes": ""},
        "cles": {"state": "returned", "returnedAt": "2026-01-10", "notes": ""},
    },
    returned_at="2026-01-10",
    reason="Retraite anticipee",
), "R7. Returned — Retraite anticipee, badge+cle")

create(returned_dossier(
    "LEVY", "Sarah", "Action sociale", "Chef de service",
    materiel={
        "ordinateur": {"selected": True, "marque": "HP", "modele": "EliteBook 840",
                       "numeroSerie": "SN-HP-SOC-01", "assignedAt": "2021-09-01"},
        "telephone": {"selected": True, "marque": "Samsung", "modele": "Galaxy A53",
                      "imei": "110000555666777", "assignedAt": "2022-03-01"},
        "badge": {"selected": True, "numero": "B-2021-SOC-01"},
    },
    immateriel={
        "email": {"selected": True, "adresse": "sarah.levy@example.fr"},
        "vpn": {"selected": True, "identifiant": "slevy"},
    },
    restitution_items={
        "ordinateur": {"state": "returned_damaged", "returnedAt": "2026-03-31",
                       "notes": "Batterie HS, fissure capot"},
        "telephone": {"state": "returned", "returnedAt": "2026-03-31", "notes": "Ecran impeccable"},
        "badge": {"state": "returned", "returnedAt": "2026-03-31", "notes": ""},
        "email": {"state": "returned", "returnedAt": "2026-03-31", "notes": "Forwarding 3 mois"},
        "vpn": {"state": "returned", "returnedAt": "2026-03-31", "notes": "Revoque"},
    },
    returned_at="2026-03-31",
    reason="Mutation departementale",
    notes="Ordi tres use apres 5 ans, batterie a remplacer",
), "R8. Returned — Mutation, ordi degrade, 5 ressources")


# =========================================================================
print(f"\n{'='*60}")
print(f"Total : {len(created)} dossiers crees")
print(f"{'='*60}")
for fid, label, status in created:
    print(f"  [{status:22s}] {label}")
