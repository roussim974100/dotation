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

### 2. Déployer et installer dans le venv de prod

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

---

## Vérifier les paquets installés dans le venv

```bash
/opt/dotation/backend/venv/bin/pip list
```

## En cas d'erreur `ModuleNotFoundError` après un déploiement

C'est presque toujours qu'un nouveau paquet a été ajouté à `requirements.txt` mais pas installé dans le venv. Faire :

```bash
/opt/dotation/backend/venv/bin/pip install -r /opt/dotation/backend/requirements.txt
systemctl restart dotation
```
