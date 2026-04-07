"""
Cree des dossiers de test couvrant tous les cas de figure.
Usage : python scripts/seed_test_dossiers.py
Necessite le serveur Flask en cours sur http://127.0.0.1:5000
"""

import requests
import json

BASE = "http://127.0.0.1:5000"
s = requests.Session()

# Login
csrf = s.get(f"{BASE}/api/csrf-token").json()["token"]
r = s.post(f"{BASE}/login", data={
    "username": "claude.test",
    "password": "ClaudeTest@2026!",
    "csrf_token": csrf,
})
print(f"Login: {r.status_code}")

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
        created.append((fid, label))
        print(f"  OK  [{status:22s}] {label}")
        return fid
    else:
        print(f"  ERR {label} -> {r.status_code} {r.text[:120]}")
        return None


# =========================================================================
# ATTRIBUTION — Brouillons
# =========================================================================
print("\n=== ATTRIBUTION — Brouillons ===\n")

create({
    "beneficiaire": {"nom": "DURAND", "prenom": "Marie", "qualite": "agent",
                     "service": "Comptabilite", "fonction": "Gestionnaire"},
    "dossier": {"type": "arrivee"},
}, "1. Brouillon vide (arrivee agent, aucune ressource)")

create({
    "beneficiaire": {"nom": "LECLERC", "prenom": "Thomas", "qualite": "agent",
                     "service": "Informatique", "fonction": "Technicien"},
    "dossier": {"type": "arrivee"},
    "materiel": {
        "ordinateur": {"selected": True},
        "ecran": {"selected": True},
        "telephone": {"selected": True},
    },
    "immateriel": {
        "email": {"selected": True},
        "vpn": {"selected": True},
    },
}, "2. Brouillon avec 5 ressources non remplies")

create({
    "beneficiaire": {"nom": "MOREAU", "prenom": "Sophie", "qualite": "agent",
                     "service": "RH", "fonction": "Responsable"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-15"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 5540",
                       "numeroSerie": "SN-DELL-001", "assignedAt": "2026-04-01"},
        "ecran": {"selected": True},
        "badge": {"selected": True},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "sophie.moreau@example.fr"},
    },
}, "3. Brouillon partiel (ordi OK, ecran+badge vides)")

create({
    "beneficiaire": {"nom": "PETIT", "prenom": "Jean-Marc", "qualite": "elu",
                     "mandat": "Adjoint au maire"},
    "dossier": {"type": "arrivee"},
    "materiel": {
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 15",
                      "imei": "123456789012345"},
        "tablette": {"selected": True},
    },
}, "4. Brouillon elu (telephone rempli, tablette vide)")

# =========================================================================
# ATTRIBUTION — Types de dossier
# =========================================================================
print("\n=== ATTRIBUTION — Types de dossier ===\n")

create({
    "beneficiaire": {"nom": "BERNARD", "prenom": "Claire", "qualite": "agent",
                     "service": "Urbanisme", "fonction": "Chef de projet",
                     "serviceDestination": "Environnement"},
    "dossier": {"type": "changement_service"},
    "materiel": {
        "badge": {"selected": True, "numero": "B-2026-042"},
    },
}, "5. Changement de service")

create({
    "beneficiaire": {"nom": "ROUX", "prenom": "Julien", "qualite": "agent",
                     "service": "Communication", "fonction": "Webmaster"},
    "dossier": {"type": "mise_a_jour"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Lenovo", "modele": "ThinkPad T14s",
                       "numeroSerie": "SN-LEN-042", "assignedAt": "2026-03-15"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "julien.roux@example.fr"},
        "vpn": {"selected": True, "identifiant": "jroux"},
    },
}, "6. Mise a jour (ressources completes, pas signe)")

create({
    "beneficiaire": {"nom": "LEROY", "prenom": "Patrick", "qualite": "agent",
                     "service": "Espaces verts", "fonction": "Chef d'equipe"},
    "dossier": {"type": "sortie"},
    "materiel": {
        "vehicule": {"selected": True, "marque": "Renault", "modele": "Kangoo",
                     "immatriculation": "AB-123-CD"},
        "badge": {"selected": True, "numero": "B-2024-012"},
        "cles": {"selected": True, "values": ["Cle depot municipal", "Cle vehicule"]},
        "veste": {"selected": True},
        "chaussuresSecurite": {"selected": True},
    },
}, "7. Sortie brouillon (5 ressources)")

# =========================================================================
# ATTRIBUTION — Statuts avances
# =========================================================================
print("\n=== ATTRIBUTION — Statuts avances ===\n")

create({
    "beneficiaire": {"nom": "GARCIA", "prenom": "Elena", "qualite": "agent",
                     "service": "Finances", "fonction": "Comptable"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-03-20"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "HP", "modele": "ProBook 450",
                       "numeroSerie": "SN-HP-007", "assignedAt": "2026-03-18"},
        "badge": {"selected": True, "numero": "B-2026-007"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "elena.garcia@example.fr"},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "active"},
}, "8. Active (signee, RGPD, tout complet)")

create({
    "beneficiaire": {"nom": "LAMBERT", "prenom": "Nicolas", "qualite": "agent",
                     "service": "Voirie", "fonction": "Agent technique"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-10"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "OptiPlex",
                       "numeroSerie": "SN-DELL-099", "assignedAt": "2026-04-05"},
        "vehicule": {"selected": True},
        "badge": {"selected": True, "numero": "B-2026-099"},
        "chaussuresSecurite": {"selected": True},
        "veste": {"selected": True},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
}, "9. Attribution partielle (vehicule/veste/chaussures non remplis)")

create({
    "beneficiaire": {"nom": "FOURNIER", "prenom": "Isabelle", "qualite": "agent",
                     "service": "Etat civil", "fonction": "Responsable"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-08"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 7440",
                       "numeroSerie": "SN-DELL-055", "assignedAt": "2026-04-02"},
        "badge": {"selected": True, "numero": "B-2026-055"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "isabelle.fournier@example.fr"},
    },
    "validation": {"rgpdAccepted": True},
}, "10. En attente de signature (tout rempli, pas signe)")

# =========================================================================
# ATTRIBUTION — Avec UNC
# =========================================================================
print("\n=== ATTRIBUTION — Avec UNC ===\n")

create({
    "beneficiaire": {"nom": "MARTIN", "prenom": "Luc", "qualite": "agent",
                     "service": "DSI", "fonction": "Administrateur systeme"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-20"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Precision 5680",
                       "numeroSerie": "SN-DELL-DSI-01", "assignedAt": "2026-04-15"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "luc.martin@example.fr"},
        "vpn": {"selected": True, "identifiant": "lmartin"},
    },
    "unc_acces": [
        {"chemin": "\\\\SRVFIC01\\Services\\DSI", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC01\\Commun", "acces": "lecture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC02\\Projets\\Migration", "acces": "lecture_ecriture",
         "statut": "en_cours", "commentaire": "Demande en cours aupres de la DSI"},
    ],
    "unc_ref_ad": "lmartin@example.local",
}, "11. Brouillon avec 3 UNC (DSI)")

create({
    "beneficiaire": {"nom": "DUBOIS", "prenom": "Amandine", "qualite": "agent",
                     "service": "Direction generale", "fonction": "Directrice"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-03-15"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 9440",
                       "numeroSerie": "SN-DELL-DG-01", "assignedAt": "2026-03-12"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "amandine.dubois@example.fr"},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "active"},
    "unc_acces": [
        {"chemin": "\\\\SRVFIC01\\Direction", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": ""},
        {"chemin": "\\\\SRVFIC01\\Commun", "acces": "lecture",
         "statut": "provisionne", "commentaire": ""},
    ],
    "unc_ref_ad": "adubois@example.local",
}, "12. Active avec 2 UNC (Direction)")

# =========================================================================
# RESTITUTION
# =========================================================================
print("\n=== RESTITUTION ===\n")

create({
    "beneficiaire": {"nom": "ROUSSEAU", "prenom": "Catherine", "qualite": "agent",
                     "service": "Accueil", "fonction": "Hotesse"},
    "dossier": {"type": "sortie"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "HP", "modele": "ProDesk",
                       "numeroSerie": "SN-HP-ACC-01", "assignedAt": "2024-06-15"},
        "badge": {"selected": True, "numero": "B-2024-033"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "catherine.rousseau@example.fr"},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "returned"},
    "restitution": {
        "returnedAt": "2026-04-01",
        "reason": "Depart en retraite",
        "notes": "Materiel en bon etat general",
        "items": {
            "ordinateur": {"state": "returned", "returnedAt": "2026-04-01", "notes": "Bon etat"},
            "badge": {"state": "returned", "returnedAt": "2026-04-01", "notes": ""},
            "email": {"state": "returned", "returnedAt": "2026-04-01", "notes": "Compte desactive"},
        },
    },
}, "13. Restitution complete (tous rendus)")

create({
    "beneficiaire": {"nom": "SIMON", "prenom": "David", "qualite": "agent",
                     "service": "Police municipale", "fonction": "Agent"},
    "dossier": {"type": "sortie"},
    "materiel": {
        "telephone": {"selected": True, "marque": "Samsung", "modele": "Galaxy A54",
                      "imei": "987654321098765", "assignedAt": "2025-01-10"},
        "badge": {"selected": True, "numero": "B-2025-PM-08"},
        "vehicule": {"selected": True, "marque": "Peugeot", "modele": "Partner",
                     "immatriculation": "EF-456-GH"},
        "veste": {"selected": True},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "partial_return"},
    "restitution": {
        "returnedAt": "2026-03-28",
        "reason": "Mutation vers autre commune",
        "items": {
            "telephone": {"state": "returned", "returnedAt": "2026-03-28",
                          "notes": "Ecran fissure"},
            "badge": {"state": "returned", "returnedAt": "2026-03-28", "notes": ""},
            "vehicule": {"state": "non_restitue",
                         "notes": "En attente - agent en conge maladie"},
            "veste": {"state": "non_restitue", "notes": ""},
        },
    },
}, "14. Restitution partielle (vehicule + veste non rendus)")

create({
    "beneficiaire": {"nom": "BLANC", "prenom": "Nathalie", "qualite": "agent",
                     "service": "Bibliotheque", "fonction": "Bibliothecaire"},
    "dossier": {"type": "sortie"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Lenovo", "modele": "ThinkCentre",
                       "numeroSerie": "SN-LEN-BIB-01", "assignedAt": "2023-09-01"},
        "ecran": {"selected": True, "marque": "LG", "modele": "27UK850",
                  "numeroSerie": "SN-LG-BIB-01", "assignedAt": "2023-09-01"},
        "badge": {"selected": True, "numero": "B-2023-BIB-04"},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "returned"},
    "restitution": {
        "returnedAt": "2026-04-02",
        "reason": "Fin de contrat CDD",
        "notes": "Ordinateur endommage, ecran OK",
        "items": {
            "ordinateur": {"state": "returned_damaged", "returnedAt": "2026-04-02",
                           "notes": "Clavier casse, traces de choc sur le capot"},
            "ecran": {"state": "returned", "returnedAt": "2026-04-02", "notes": "Bon etat"},
            "badge": {"state": "returned", "returnedAt": "2026-04-02", "notes": ""},
        },
    },
}, "15. Restitution complete avec materiel degrade")

create({
    "beneficiaire": {"nom": "GIRARD", "prenom": "Philippe", "qualite": "agent",
                     "service": "Sports", "fonction": "Directeur"},
    "dossier": {"type": "sortie"},
    "meta": {"startAt": "2025-09-01"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Latitude 5530",
                       "numeroSerie": "SN-DELL-SPO-01", "assignedAt": "2025-09-01"},
        "telephone": {"selected": True, "marque": "Apple", "modele": "iPhone 14",
                      "imei": "111222333444555", "assignedAt": "2025-09-01"},
        "vehicule": {"selected": True, "marque": "Citroen", "modele": "C5 Aircross",
                     "immatriculation": "GH-789-IJ"},
        "badge": {"selected": True, "numero": "B-2025-SPO-01"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "philippe.girard@example.fr"},
        "vpn": {"selected": True, "identifiant": "pgirard"},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "partial_return"},
    "restitution": {
        "reason": "Depart volontaire",
        "items": {
            "ordinateur": {"state": "returned", "returnedAt": "2026-03-30", "notes": ""},
            "telephone": {"state": "non_restitue",
                          "notes": "Agent en conge, restitution prevue semaine prochaine"},
            "vehicule": {"state": "non_restitue",
                         "notes": "Rendez-vous garage le 10/04"},
            "badge": {"state": "returned", "returnedAt": "2026-03-30", "notes": ""},
            "email": {"state": "returned", "returnedAt": "2026-03-30",
                      "notes": "Desactive"},
            "vpn": {"state": "returned", "returnedAt": "2026-03-30",
                    "notes": "Revoque"},
        },
    },
    "unc_acces": [
        {"chemin": "\\\\SRVFIC01\\Sports", "acces": "lecture_ecriture",
         "statut": "provisionne", "commentaire": "A revoquer apres depart"},
    ],
}, "16. Restitution partielle + UNC (telephone + vehicule en attente)")

create({
    "beneficiaire": {"nom": "MERCIER", "prenom": "Sandrine", "qualite": "agent",
                     "service": "Petite enfance", "fonction": "Directrice creche"},
    "dossier": {"type": "sortie"},
    "materiel": {
        "telephone": {"selected": True, "marque": "Samsung", "modele": "Galaxy A34",
                      "imei": "555666777888999", "assignedAt": "2024-03-01"},
        "badge": {"selected": True, "numero": "B-2024-PE-02"},
        "cles": {"selected": True, "values": ["Cle creche Les Lutins", "Cle bureau directrice"]},
    },
    "validation": {"rgpdAccepted": True, "signatureDataUrl": FAKE_SIG},
    "workflow": {"status": "returned"},
    "restitution": {
        "returnedAt": "2026-04-01",
        "reason": "Retraite",
        "signatureStatus": "deferred",
        "items": {
            "telephone": {"state": "returned", "returnedAt": "2026-04-01", "notes": ""},
            "badge": {"state": "returned", "returnedAt": "2026-04-01", "notes": ""},
            "cles": {"state": "returned", "returnedAt": "2026-04-01",
                     "notes": "2 cles rendues"},
        },
    },
}, "17. Restitution en attente de signature distante")

# =========================================================================
# TIMING (pilotage)
# =========================================================================
print("\n=== TIMING (pilotage) ===\n")

create({
    "beneficiaire": {"nom": "FAURE", "prenom": "Christophe", "qualite": "agent",
                     "service": "Patrimoine", "fonction": "Technicien"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-03-15"},
    "materiel": {
        "ordinateur": {"selected": True},
        "badge": {"selected": True},
    },
}, "18. En retard (date passee, ressources vides)")

create({
    "beneficiaire": {"nom": "ANDRE", "prenom": "Valerie", "qualite": "agent",
                     "service": "Action sociale", "fonction": "Assistante sociale"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-04"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "HP", "modele": "EliteBook",
                       "numeroSerie": "SN-HP-SOC-01", "assignedAt": "2026-04-01"},
        "badge": {"selected": True},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "valerie.andre@example.fr"},
    },
}, "19. En danger (J-2, badge non rempli)")

create({
    "beneficiaire": {"nom": "MASSON", "prenom": "Olivier", "qualite": "agent",
                     "service": "Urbanisme", "fonction": "Ingenieur"},
    "dossier": {"type": "arrivee"},
    "meta": {"startAt": "2026-04-20"},
    "materiel": {
        "ordinateur": {"selected": True, "marque": "Dell", "modele": "Precision 3580",
                       "numeroSerie": "SN-DELL-URB-01", "assignedAt": "2026-04-01"},
    },
    "immateriel": {
        "email": {"selected": True, "adresse": "olivier.masson@example.fr"},
        "vpn": {"selected": True, "identifiant": "omasson"},
    },
}, "20. Dans les temps (J-18, ordi pret)")

# =========================================================================
# Resume
# =========================================================================
print(f"\n{'='*60}")
print(f"Total : {len(created)} dossiers crees")
print(f"{'='*60}")
