# Gestion des dépendances Python en production

## Contexte

Le projet tourne dans un LXC Debian sous Gunicorn avec un **virtualenv dédié** situé dans :

```
/opt/dotation/backend/venv/
```

Gunicorn est lancé via `/opt/dotation/backend/venv/bin/python3`. Il est donc **isolé du Python système** — `pip` système n'a aucun effet sur lui.

---

## Installer une nouvelle dépendance

### 1. Ajouter le paquet dans `requirements.txt`

```
backend/requirements.txt
```

### 2. Déployer : le script s'en charge

```bash
cd /opt/dotation
sudo bash deploy.sh          # production (branche prod)
sudo bash deploy-dev.sh      # préprod / version dev (branche dev)
```

Le script lit le venv réellement utilisé par le service dans `/etc/systemd/system/dotation.service`, y installe `requirements.txt`, redémarre le service et vérifie qu'il répond. Voir le README (« Mise à jour en production »).

### 2 bis. Installation manuelle (si le script n'est pas utilisable)

```bash
# Dans le LXC de prod
/opt/dotation/backend/venv/bin/pip install -r /opt/dotation/backend/requirements.txt
systemctl restart dotation
systemctl status dotation
```

> Ne pas utiliser `pip install` seul — il cible le Python système et non le venv.

---

## Historique des dépendances ajoutées

| Date       | Paquet  | Raison                                      |
|------------|---------|---------------------------------------------|
| 2026-03-31 | fpdf2   | Génération PDF (remplacement du PDF brut maison) |
| 2026-09-19 | cryptography | Chiffrement des sauvegardes (AES-256-GCM, scrypt). Importée à la demande : si elle manque, l'application démarre et seules les sauvegardes chiffrées sont indisponibles |

---

## Vérifier les paquets installés dans le venv

```bash
/opt/dotation/backend/venv/bin/pip list
```

## En cas d'erreur `ModuleNotFoundError` après un déploiement

C'est presque toujours qu'un nouveau paquet a été ajouté à `requirements.txt` mais pas installé dans le venv (symptôme côté reverse proxy : **502 Bad Gateway**, car le service ne démarre plus). Le plus simple : `sudo bash deploy.sh` (ou `deploy-dev.sh`). À la main, avec **le venv du service** (ligne `ExecStart` du fichier systemd ; ici `/opt/dotation/backend/venv`, mais l'installateur peut avoir créé `/opt/dotation/venv`) :

```bash
/opt/dotation/backend/venv/bin/pip install -r /opt/dotation/backend/requirements.txt
systemctl restart dotation
```

Lire l'erreur exacte : `journalctl -u dotation -n 40 --no-pager`. Si systemd affiche `Start request repeated too quickly`, corriger puis `systemctl reset-failed dotation && systemctl restart dotation`.
