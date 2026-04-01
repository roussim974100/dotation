# A quai

Application interne de gestion des dossiers d'attribution et de restitution.

Version courante : `2.12.1`

## Ce que fait l'application

- creer un dossier pour un agent ou un(e) elu(e)
- enregistrer un dossier en brouillon ou en attribution partielle
- verrouiller un dossier complet une fois signe et valide RGPD
- generer un lien unique de signature a distance pour la remise
- generer un lien unique de signature a distance pour la restitution
- tracer les reouvertures de dossier encore modifiable
- suivre la restitution des ressources materielles
- administrer les comptes, les groupes, les services et les ressources attribuables
- définir des ressources personnalisées avec leurs champs métier, leur suivi Ã  l'attribution et leur restitution éventuelle
- réorganiser l'ordre d'affichage des ressources par service avec une page dédiée
- consulter un journal des actions
- restaurer des suppressions via une corbeille reservee aux admins
- exporter les dossiers et les restitutions en PDF via `fpdf2`
- proteger les signatures dans les exports PDF selon le profil connecte
- exporter les donnees en Excel

## Types de dossier

- `arrivee` : nouvelle arrivee
- `changement_service` : mobilite interne
- `mise_a_jour` : mise a jour de ressources
- `sortie` : sortie ou restitution

## Documents du projet

- `LIVRAISON.md` : vue de remise du projet
- `GUIDE_UTILISATEUR.md` : guide d'usage rapide
- `RECETTE_FONCTIONNELLE.md` : checklist et scenarios de test
- `wikijs.md` : documentation prete a integrer dans Wiki.js
- `version/versions/` : archives documentaires par version

## Architecture

- `frontend/` : interface HTML, CSS et JavaScript servie par Flask
- `backend/` : API Flask, authentification et persistance SQLite
  - `app.py` : point d'entree Flask, routes et initialisation
  - `config.py` : constantes et chemins
  - `utils.py` : fonctions utilitaires partagees
  - `database.py` : acces SQLite et helpers de schema
  - `auth.py` : decorateurs, gestion des comptes et rate limiting
  - `models/` : logique metier (workflow, dossier, signature, audit, settings)
  - `pdf/` : generation des PDF dossier et restitution via `fpdf2`

## Prerequis avant lancement

Pour un nouveau deploiement dans une collectivite ou une entreprise, prevoir :

- `Python 3.11` ou plus recent
- `pip`
- un systeme capable d'executer Flask en service
- un reverse proxy pour la production
  - par exemple `nginx` + `gunicorn`
- un stockage local rapide pour la base SQLite
  - eviter de placer la base sur un partage reseau SMB
- un certificat TLS si l'application est exposee en HTTPS

Dependances Python du projet :

- `flask`
- `bcrypt`
- `fpdf2`

Installation recommandee sous Windows :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Installation recommandee sous Linux `VM` ou `LXC` :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Premier deploiement

### 1. Copier le projet

Placer le projet dans un dossier applicatif, par exemple :

Sous Windows :

```text
C:\www\dotation
```

Sous Linux :

```text
/opt/dotation
```

### 2. Preparer les variables d'environnement

Variables recommandees avant le lancement :

- `APP_SECRET_KEY`
- `SESSION_COOKIE_SECURE=1` en production HTTPS

Exemple Windows PowerShell :

```powershell
$env:APP_SECRET_KEY="une-cle-longue-et-aleatoire"
$env:SESSION_COOKIE_SECURE="1"
python backend\app.py
```

Exemple Linux bash :

```bash
export APP_SECRET_KEY="une-cle-longue-et-aleatoire"
export SESSION_COOKIE_SECURE="1"
python3 backend/app.py
```

### 3. Creer le fichier des utilisateurs

L'authentification repose sur :

- `backend/users.json`

Ce fichier contient :

- les groupes
- les permissions
- les comptes applicatifs
- les mots de passe sous forme de hash `bcrypt`

Le projet charge ce fichier via `backend/app.py` avec :

- `USERS_FILE = os.path.join(BASE_DIR, "users.json")`

### 4. Generer un hash bcrypt pour le premier administrateur

Avant de creer le fichier, generer un hash pour le mot de passe admin :

Sous Windows :

```powershell
python -c "import bcrypt; print(bcrypt.hashpw('ChangezMoi123!'.encode(), bcrypt.gensalt()).decode())"
```

Sous Linux :

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw('ChangezMoi123!'.encode(), bcrypt.gensalt()).decode())"
```

Remplacer ensuite `ChangezMoi123!` par un mot de passe fort propre au client.

### 5. Exemple minimal de `backend/users.json`

Pour un nouveau deploiement, vous pouvez partir de ce modele minimal :

```json
{
  "_comment": "Configuration locale des groupes et comptes applicatifs. Les mots de passe sont stockes haches avec bcrypt.",
  "groups": {
    "lecture": {
      "label": "Lecture",
      "description": "Consultation seule, sans possibilite de saisie.",
      "permissions": [
        "forms.read_list",
        "forms.read_detail",
        "forms.export"
      ],
      "data_scope": "full"
    },
    "redaction": {
      "label": "Redaction",
      "description": "Creation et modification des fiches en cours.",
      "permissions": [
        "forms.read_list",
        "forms.read_detail",
        "forms.create",
        "forms.edit",
        "forms.export"
      ],
      "data_scope": "full"
    },
    "gestion": {
      "label": "Gestion",
      "description": "Gestion avancee avec restitution et export.",
      "permissions": [
        "forms.read_list",
        "forms.read_detail",
        "forms.create",
        "forms.edit",
        "forms.restitution",
        "forms.export"
      ],
      "data_scope": "full"
    },
    "admin": {
      "label": "Administration",
      "description": "Controle total et gestion des utilisateurs.",
      "permissions": [
        "forms.read_list",
        "forms.read_detail",
        "forms.create",
        "forms.edit",
        "forms.restitution",
        "forms.export",
        "forms.delete",
        "users.manage",
        "*"
      ],
      "data_scope": "full"
    }
  },
  "users": [
    {
      "username": "admin",
      "password_hash": "COLLER_ICI_LE_HASH_BCRYPT",
      "groups": [
        "admin"
      ],
      "is_active": true,
      "status": "active"
    }
  ]
}
```

### 6. Premier lancement

Depuis la racine du projet :

Sous Windows :

```powershell
python backend\app.py
```

Sous Linux :

```bash
python3 backend/app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/
```

Au premier lancement, l'application initialise automatiquement la base SQLite et les tables necessaires.

### 7. Verification minimale avant mise en service

- connexion avec le compte `admin`
- acces au tableau de bord
- acces au menu `Administration`
- creation d'un dossier test
- export PDF test
- verification de l'ecriture dans la base SQLite
- verification des droits sur `backend/users.json`

## Deploiement Linux VM ou LXC

Pour une `VM Linux` ou un conteneur `LXC`, la base recommandee est :

- `Debian 12` ou `Ubuntu 22.04/24.04`
- un utilisateur applicatif dedie
- `nginx` en frontal
- `gunicorn` pour servir Flask
- un repertoire applicatif local
  - par exemple `/opt/dotation`

### Paquets systeme recommandes

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

### Preparation du projet

```bash
sudo mkdir -p /opt/dotation
sudo chown -R $USER:$USER /opt/dotation
cd /opt/dotation
```

Puis copier les fichiers du projet dans ce repertoire, creer le venv et installer les dependances :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Lancement de verification

```bash
source /opt/dotation/.venv/bin/activate
export APP_SECRET_KEY="une-cle-longue-et-aleatoire"
python3 /opt/dotation/backend/app.py
```

### Service `gunicorn` conseille

Exemple de service systemd :

```ini
[Unit]
Description=Dotation Flask via Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/dotation
Environment="APP_SECRET_KEY=une-cle-longue-et-aleatoire"
Environment="SESSION_COOKIE_SECURE=1"
ExecStart=/opt/dotation/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 backend.app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Exemple de fichier :

```text
/etc/systemd/system/dotation.service
```

Activation :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dotation
sudo systemctl status dotation
```

### Proxy `nginx` conseille

Exemple de virtual host :

```nginx
server {
    listen 80;
    server_name dotation.exemple.local;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name dotation.exemple.local;

    ssl_certificate /etc/ssl/certs/dotation.crt;
    ssl_certificate_key /etc/ssl/private/dotation.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

Puis :

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Points d'attention LXC

Dans un conteneur `LXC` :

- conserver la base SQLite sur le disque local du conteneur
- eviter les montages reseau pour la base
- verifier les droits d'ecriture sur :
  - `backend/users.json`
  - le fichier SQLite cree par l'application
  - les assets de branding personnalises si le televersement de logo est utilise
- si un reverse proxy externe termine deja le HTTPS, conserver tout de meme les bons headers `X-Forwarded-*`

## Capacite SQLite

L'application utilise `SQLite`, ce qui convient bien a un usage interne modere.

En pratique :

- quelques dizaines d'utilisateurs sont generalement supportes sans difficulte
- autour de `10 a 30 utilisateurs simultanes`, le fonctionnement reste en general confortable
- entre `30 et 80 utilisateurs simultanes`, cela peut encore tenir selon le serveur et le volume d'ecritures
- au-dela, le point de vigilance principal devient la concurrence en ecriture

Important :

- `SQLite` gere bien les lectures concurrentes
- `SQLite` serialise les ecritures
- si beaucoup d'utilisateurs enregistrent en meme temps, des attentes ou verrous peuvent apparaitre

Pour une petite ou moyenne collectivite, cette architecture peut suffire.

Si l'application doit supporter :

- beaucoup d'utilisateurs simultanes
- de fortes ecritures concurrentes
- plusieurs services actifs en permanence
- une volumetrie croissante sur plusieurs annees

alors il faut envisager a terme une migration vers `PostgreSQL`.

## Fichiers principaux

- `frontend/index.html` : tableau de bord des dossiers
- `frontend/form.html` : creation et mise a jour d'un dossier
- `frontend/restitution.html` : restitution des ressources materielles
- `frontend/signature.html` : page publique de signature via lien securise
- `frontend/admin.html` : portail administration
- `frontend/admin-comptes.html` : gestion des comptes
- `frontend/admin-services.html` : catalogue des services
- `frontend/admin-ressources.html` : catalogue des ressources
- `frontend/logs.html` : journal des actions
- `frontend/trash.html` : corbeille administrateur
- `backend/app.py` : point d'entree Flask et routes
- `backend/auth.py` : authentification, decorateurs et gestion des comptes
- `backend/models/workflow.py` : calculs de statut, validation des ressources
- `backend/models/settings.py` : parametres applicatifs, logo et theme
- `backend/models/signature.py` : liens de signature a distance
- `backend/models/audit.py` : journal et tracabilite
- `backend/pdf/attribution.py` : generation du PDF dossier
- `backend/pdf/restitution.py` : generation du PDF restitution

## Lancement

Depuis la racine du projet :

```powershell
python backend\app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/
```

## Authentification

- la connexion est obligatoire
- un message d'erreur s'affiche si les identifiants sont incorrects
- un message specifique s'affiche si la session ne peut pas etre conservee

En environnement proxy `nginx + gunicorn`, il est recommande de definir :

- `APP_SECRET_KEY`
- `SESSION_COOKIE_SECURE=1` si le contexte HTTPS est stabilise

Et de transmettre correctement au backend :

- `X-Forwarded-For`
- `X-Real-IP`
- `X-Forwarded-Proto`
- `Host`

## Tableau de bord

Le tableau de bord permet de :

- creer un nouveau dossier
- rechercher et filtrer les dossiers
- ouvrir un dossier
- lancer une restitution
- exporter un `PDF dossier`
- exporter un `PDF restitution`
- exporter plusieurs `PDF dossier`
- exporter plusieurs `PDF restitution`
- supprimer une selection de dossiers
- exporter les donnees en Excel

Le tableau de bord se rafraichit automatiquement sans `F5` :

- toutes les 20 secondes si l'onglet est visible
- au retour de focus
- avec signal visuel des nouveaux dossiers
- avec acquittement utilisateur `J'ai vu`
- avec conservation de la selection pendant le rafraichissement

## Dossier

Un dossier peut contenir :

- les informations de la personne
- la qualite `Agent` ou `Elu(e)`
- le type de dossier
- les ressources attribuees par service
- la signature de remise
- un lien de signature a distance a usage unique pour la remise
- un lien de signature de restitution a usage unique
- la validation RGPD
- la tracabilite de reouverture

## Signature a distance

Depuis la fiche dossier, un profil autorise peut :

- generer un lien unique de signature
- copier ce lien
- revoquer le lien
- regenerer un nouveau lien

La page publique de signature permet a la personne concernee de :

- consulter l'identite et les ressources remises
- prendre connaissance du RGPD
- signer le dossier sans compte applicatif

Le lien est :

- limite a un seul dossier
- a usage unique
- expirable
- revocable

Un dossier complet passe en `Attribution active`.

Un dossier incomplet reste en `Attribution partielle` et demeure modifiable.

## Restitution

La restitution est geree sur un ecran separe.

Elle permet de :

- saisir une date de restitution
- definir rapidement l'etat de chaque materiel
- ajouter un commentaire uniquement si necessaire
- signer la restitution ou indiquer pourquoi la signature est impossible ou differee
- exporter un `PDF restitution` distinct

La restitution reste modifiable tant qu'un materiel est `Non restitue`.

## Administration

L'administration permet de :

- creer, modifier, desactiver ou supprimer un compte
- changer le mot de passe d'un compte
- creer, modifier, activer ou desactiver un service
- creer, modifier ou supprimer une ressource attribuable
- consulter le journal
- acceder a la corbeille admin

L'administration est maintenant organisee en sous-pages :

- `admin.html` pour la vue d'ensemble
- `admin-comptes.html` pour les comptes et les groupes
- `admin-services.html` pour les services
- `admin-ressources.html` pour les ressources

## Journal et corbeille

- le journal recense les actions systeme et utilisateur
- la corbeille est reservee au groupe `admin`
- un dossier, un compte ou une ressource supprime(e) peut etre restaure(e)

## Exports

### PDF dossier

Document officiel de remise avec :

- entete institutionnel
- informations de la personne
- ressources attribuees
- RGPD
- signature
- date de signature

Pour un profil non autorise a consulter les signatures, le PDF reste exportable mais la signature est masquee avec une mention reservee aux personnes autorisees.

### PDF restitution

Document distinct avec :

- informations de la personne
- date de restitution
- toutes les ressources materielles avec leur etat
- commentaires d'anomalie
- signature de restitution ou motif d'absence

Pour un profil non autorise a consulter les signatures, la signature de restitution est masquee dans le document exporte.

### Export Excel

L'export Excel fournit un classeur lisible avec :

- une feuille `Dossiers`
- une feuille `Ressources`

## Verification technique

Controle minimal recommande apres modification :

```powershell
python -m py_compile backend\app.py
python -m py_compile backend\auth.py
python -m py_compile backend\models\workflow.py
python -m py_compile backend\models\settings.py
python -m py_compile backend\pdf\attribution.py
python -m py_compile backend\pdf\restitution.py
```




