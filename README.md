# À Quai

Application interne de gestion des dotations matérielles — attribution et restitution de ressources pour les agents, collaborateurs ou élus d'une organisation.

**Version :** `3.0.4` | **Stack :** Flask · SQLite · Vanilla JS | **Licence :** usage interne

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Déploiement rapide — Debian / LXC](#déploiement-rapide--debian--lxc)
- [Déploiement manuel — Debian / Ubuntu](#déploiement-manuel--debian--ubuntu)
- [Déploiement Windows — IIS + Waitress](#déploiement-windows--iis--waitress)
- [Déploiement derrière un reverse proxy existant](#déploiement-derrière-un-reverse-proxy-existant)
- [Configuration initiale (setup wizard)](#configuration-initiale-setup-wizard)
- [Fichier users.json](#fichier-usersjson)
- [Mise à jour en production](#mise-à-jour-en-production)
- [Variables d'environnement](#variables-denvironnement)
- [Architecture](#architecture)
- [Sécurité](#sécurité)
- [Limites SQLite](#limites-sqlite)
- [Développement local](#développement-local)

---

## Fonctionnalités

**Dossiers**
- Créer, modifier et verrouiller des dossiers d'attribution pour agents, élus, salariés…
- 4 types de dossier : nouvelle arrivée, changement de service, mise à jour, sortie
- Ressources configurables par l'admin (avec champs métier, suivi à l'attribution, restitution)
- Import / export CSV du catalogue de services

**Signature**
- Signature directe sur l'écran ou via lien sécurisé à usage unique envoyé au bénéficiaire
- Signature de restitution distincte
- Protection de la signature dans les PDF selon les droits du profil

**Restitution**
- Écran dédié : état par ressource (conforme, dégradé, manquant…), commentaires, date
- PDF de restitution distinct du PDF d'attribution

**Exports**
- PDF dossier et PDF restitution
- Export Excel (dossiers + ressources)
- Export groupé multi-sélection

**Administration**
- Gestion des comptes, groupes et permissions
- Catalogue des services et des ressources (ordre, activation, champs)
- Personnalisation : logo, couleur, nom d'organisation, email DPO, contact support
- Contexte organisationnel : collectivité, administration, entreprise, association
- Journal d'audit, corbeille avec restauration
- Mode sombre intégré

**White-label**
- Setup wizard guidé au premier lancement
- Types de bénéficiaires configurables selon le contexte (agent, élu, fonctionnaire, militaire, salarié…)
- Aucune référence au déploiement initial dans une installation neuve

---

## Prérequis

| Composant | Version minimale |
|---|---|
| Python | 3.11 |
| pip | récent |
| Système | Debian 12+, Ubuntu 22.04+, Windows Server 2019+ |
| Reverse proxy | nginx (Linux) ou IIS avec ARR (Windows) |

Dépendances Python (installées automatiquement) :

```
flask==3.1.3
bcrypt==5.0.0
fpdf2==2.8.7
werkzeug==3.1.7
```

> **Important :** la base SQLite doit être sur le disque local du serveur. Ne jamais placer `dotation.db` sur un partage réseau SMB — risque de corruption par verrouillage.

---

## Déploiement rapide — Debian / LXC

Un script automatisé est disponible pour un conteneur LXC ou une VM Debian 12+ vierge :

```bash
# Depuis la racine du projet (ou après git clone)
chmod +x scripts/deploy-debian.sh
sudo ./scripts/deploy-debian.sh
```

Le script effectue automatiquement :
1. Installation des paquets système (Python, nginx, git)
2. Clonage du dépôt dans `/opt/dotation`
3. Création du venv Python et installation des dépendances
4. Génération de la clé secrète applicative
5. Configuration du service systemd `dotation`
6. Configuration nginx en proxy sur le port 80
7. Vérification de l'accessibilité HTTP

Pour mettre à jour les paquets système en même temps :

```bash
sudo ./scripts/deploy-debian.sh --upgrade
```

Après l'installation, accéder à :

```
http://<IP_DU_SERVEUR>/
```

> Le setup wizard s'affiche automatiquement au premier lancement pour configurer l'organisation.

---

## Déploiement manuel — Debian / Ubuntu

### 1. Paquets système

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git
```

### 2. Récupérer le projet

```bash
sudo mkdir -p /opt/dotation
sudo chown $USER:$USER /opt/dotation
git clone https://github.com/roussim974100/dotation.git /opt/dotation
cd /opt/dotation
```

### 3. Environnement Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install gunicorn
```

### 4. Clé secrète

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > backend/.app_secret_key
chmod 600 backend/.app_secret_key
```

La clé est lue automatiquement par l'application au démarrage.

### 5. Service systemd

Créer `/etc/systemd/system/dotation.service` :

```ini
[Unit]
Description=A Quai — Dotation Flask via Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/dotation
Environment="SESSION_COOKIE_SECURE=1"
ExecStart=/opt/dotation/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 backend.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dotation
sudo systemctl status dotation
```

### 6. Nginx — proxy HTTP

Créer `/etc/nginx/sites-available/dotation` :

```nginx
server {
    listen 80;
    server_name dotation.exemple.local;

    client_max_body_size 5M;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   X-Forwarded-Host  $host;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 7. Nginx — proxy HTTPS (certificat existant)

```nginx
server {
    listen 80;
    server_name dotation.exemple.local;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name dotation.exemple.local;

    ssl_certificate     /etc/ssl/certs/dotation.crt;
    ssl_certificate_key /etc/ssl/private/dotation.key;

    client_max_body_size 5M;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   X-Forwarded-Host  $host;
    }
}
```

> **Note LXC :** si un reverse proxy externe (Proxmox, HAProxy) termine déjà le TLS avant le conteneur, conserver `SESSION_COOKIE_SECURE=1` et s'assurer que les headers `X-Forwarded-*` sont bien transmis jusqu'au backend Flask.

---

## Déploiement Windows — IIS + Waitress

Cette configuration convient à un serveur Windows Server avec IIS existant.

**Architecture :**
```
Internet → IIS (ARR reverse proxy, port 443/80) → Waitress (port 5000) → Flask
```

### Prérequis IIS

Depuis le **Gestionnaire de serveur** ou PowerShell, installer :
- IIS (rôle Serveur Web)
- Module **URL Rewrite** — [téléchargement Microsoft](https://www.iis.net/downloads/microsoft/url-rewrite)
- Module **Application Request Routing (ARR)** — [téléchargement Microsoft](https://www.iis.net/downloads/microsoft/application-request-routing)

Activer le proxy dans ARR :

```
IIS Manager → Application Request Routing Cache → Server Proxy Settings
→ cocher "Enable proxy" → Apply
```

### 1. Installer Python

Télécharger Python 3.11+ depuis [python.org](https://www.python.org/downloads/) et cocher **"Add Python to PATH"** lors de l'installation.

### 2. Préparer le projet

```powershell
# Placer le projet dans un répertoire applicatif
# Exemple : C:\inetpub\dotation

python -m venv C:\inetpub\dotation\.venv
C:\inetpub\dotation\.venv\Scripts\pip install -r C:\inetpub\dotation\backend\requirements.txt
C:\inetpub\dotation\.venv\Scripts\pip install waitress
```

### 3. Clé secrète

```powershell
python -c "import secrets; print(secrets.token_hex(32))" | Out-File -Encoding ASCII C:\inetpub\dotation\backend\.app_secret_key
```

### 4. Lancer Waitress comme service Windows (via NSSM)

Télécharger **NSSM** (Non-Sucking Service Manager) sur [nssm.cc](https://nssm.cc/download).

```powershell
# Depuis le répertoire de nssm
nssm install dotation "C:\inetpub\dotation\.venv\Scripts\waitress-serve.exe"
nssm set dotation AppParameters "--port=5000 --threads=4 backend.app:app"
nssm set dotation AppDirectory "C:\inetpub\dotation"
nssm set dotation AppEnvironmentExtra "SESSION_COOKIE_SECURE=1"
nssm start dotation
```

Vérifier que Waitress répond :

```powershell
Invoke-WebRequest http://localhost:5000/login
```

### 5. Configurer IIS comme proxy

Dans le **Gestionnaire IIS**, créer un nouveau site ou utiliser le site par défaut.

Créer le fichier `web.config` à la racine du site IIS (`C:\inetpub\dotation\` ou le répertoire du site) :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="Proxy vers Waitress" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://localhost:5000/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_PROTO" value="https" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="5242880" />
      </requestFiltering>
    </security>
  </system.webServer>
</configuration>
```

> Adapter `value="https"` en `value="http"` si le site IIS n'est pas en HTTPS.

### 6. Droits sur les fichiers

Le compte d'application IIS (`IIS AppPool\NomDuPool` ou `NETWORK SERVICE`) doit avoir les droits **lecture/écriture** sur :

```
C:\inetpub\dotation\backend\dotation.db
C:\inetpub\dotation\backend\users.json
C:\inetpub\dotation\backend\.app_secret_key
```

### 7. Vérification

Ouvrir un navigateur et accéder à l'URL configurée dans IIS. Le setup wizard doit s'afficher au premier lancement.

---

## Déploiement derrière un reverse proxy existant

Ce scénario s'applique quand une infrastructure centralisée (HAProxy, nginx frontal, Traefik, Proxmox…) gère déjà les certificats TLS. L'application tourne alors en **HTTP simple** sur son serveur, sans certificat local.

**Architecture :**
```
Internet ──HTTPS──▶ Reverse proxy (certificat TLS) ──HTTP──▶ Serveur app (gunicorn/waitress, port 5000)
```

### Comment l'application gère ce cas

Flask est déjà configuré avec `ProxyFix` (`x_for=1, x_proto=1, x_host=1`). Il lit le header `X-Forwarded-Proto` transmis par le proxy pour savoir si la connexion cliente est en HTTPS.

> **Point critique — boucle de login :** si `SESSION_COOKIE_SECURE=1` est activé mais que le header `X-Forwarded-Proto: https` n'est pas transmis, Flask pense que la connexion est en HTTP et refuse de poser le cookie sécurisé → boucle de login infinie. Toujours vérifier ce header en premier lors d'un problème de session.

### Configuration de l'application (côté serveur app)

Le service systemd ou NSSM doit avoir :

```
SESSION_COOKIE_SECURE=1
```

L'application n'a pas besoin de certificat. Le gunicorn ou Waitress écoute en HTTP sur `127.0.0.1:5000`.

Aucun changement dans la configuration nginx locale (si présent sur le serveur app) — il reste en HTTP.

### Exemples de configuration côté reverse proxy

#### HAProxy

```haproxy
frontend https_in
    bind *:443 ssl crt /etc/ssl/certs/dotation.pem
    default_backend dotation_back

backend dotation_back
    http-request set-header X-Forwarded-Proto https
    http-request set-header X-Forwarded-Host  %[req.hdr(Host)]
    http-request set-header X-Real-IP         %[src]
    server app1 192.168.1.10:80 check
```

> Remplacer `192.168.1.10` par l'IP du serveur applicatif (ou du LXC). Le port `80` suppose que nginx tourne localement sur le serveur app ; utiliser `5000` si Waitress ou gunicorn est exposé directement.

#### Nginx frontal (sur une machine séparée)

```nginx
server {
    listen 443 ssl;
    server_name dotation.exemple.local;

    ssl_certificate     /etc/ssl/certs/dotation.crt;
    ssl_certificate_key /etc/ssl/private/dotation.key;

    location / {
        proxy_pass         http://192.168.1.10:80;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $remote_addr;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_set_header   X-Forwarded-Host  $host;
    }
}

server {
    listen 80;
    server_name dotation.exemple.local;
    return 301 https://$host$request_uri;
}
```

#### Traefik (docker-compose)

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.dotation.rule=Host(`dotation.exemple.local`)"
  - "traefik.http.routers.dotation.entrypoints=websecure"
  - "traefik.http.routers.dotation.tls=true"
  - "traefik.http.services.dotation.loadbalancer.server.port=5000"
```

Traefik transmet automatiquement `X-Forwarded-Proto: https` quand TLS est activé sur le routeur.

### Nginx local (sur le serveur app) — HTTP uniquement

Si nginx est présent sur le serveur applicatif, sa configuration reste simple — pas de TLS, pas de redirection :

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 5M;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $remote_addr;
        proxy_set_header   X-Forwarded-Proto $http_x_forwarded_proto;
        proxy_set_header   X-Forwarded-Host  $http_x_forwarded_host;
    }
}
```

> Le nginx local **relaie** les headers `X-Forwarded-*` reçus du proxy frontal plutôt que de les réécrire. C'est ce `proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto` qui préserve la valeur `https` positionnée par le reverse proxy externe.

### Diagnostic rapide

Si l'application semble accessible mais que la connexion boucle ou que les cookies ne sont pas posés :

```bash
# Vérifier ce que Flask reçoit réellement
curl -I http://127.0.0.1:5000/login
# Doit retourner 200

# Tester avec le header attendu
curl -I -H "X-Forwarded-Proto: https" http://127.0.0.1:5000/login
```

Depuis les logs gunicorn/waitress, vérifier qu'aucune erreur 400 ou 500 n'apparaît lors de la connexion.

---

## Configuration initiale (setup wizard)

Au premier accès en tant qu'administrateur, l'application affiche un assistant de configuration en 5 étapes :

1. **Type d'organisation** — collectivité territoriale, administration, entreprise privée, association
2. **Identité** — nom de l'organisation, email DPO
3. **Contact support** — nom, rôle et email de l'administrateur applicatif
4. **Types de bénéficiaires** — pré-remplis selon le contexte (modifiables)
5. **Récapitulatif** — validation avant enregistrement

Les types de bénéficiaires par défaut selon le contexte :

| Contexte | Types par défaut |
|---|---|
| Collectivité territoriale | Agent, Élu(e) |
| Administration publique | Fonctionnaire, Contractuel(le), Prestataire |
| Entreprise privée | Salarié(e), Prestataire |
| Association | Salarié(e), Bénévole |

Ces valeurs sont personnalisables. Pour un ministère avec personnel militaire, ajouter `militaire:Militaire` dans les types.

---

## Authentification et base de données utilisateurs

L'authentification repose sur **`backend/users.db`** — une base SQLite dédiée qui stocke les utilisateurs, groupes et permissions. Cette séparation garantit que les credentials et les paramètres locaux survivent aux déploiements.

### Migration automatique depuis users.json

À la première démarrage après la migration (v3.13.0+), l'application :
1. Détecte si `backend/users.json` existe
2. Importe automatiquement les utilisateurs et groupes dans `backend/users.db`
3. Renomme `backend/users.json` en `backend/users.json.migrated` (sauvegarde sécurisée)

Après migration, **`users.json` n'est plus utilisé** — tout est en SQLite.

### Gestion des utilisateurs

**En développement :** Utilisez l'interface d'administration (`/admin-comptes.html`) pour :
- Créer, modifier, supprimer des comptes
- Assigner des groupes et permissions
- Réinitialiser les mots de passe

**En production :** Mêmes fonctionnalités via l'interface d'admin (accessible uniquement aux comptes avec permission `users.manage`).

### Déploiement sans perte de données

```bash
# Avant (era fragile, users.json écrasé par git reset) :
./deploy.sh  # Sauvegarde, merge, risque d'erreur, etc.

# Après (robuste, users.db en dehors de git) :
./deploy.sh  # git fetch + restart, c'est tout
```

Aucune sauvegarde/fusion nécessaire — `users.db` persiste entre les déploiements.

### Tableau des permissions

| Permission | Description |
|---|---|
| `forms.read_list` | Voir la liste des dossiers |
| `forms.read_detail` | Ouvrir le détail d'un dossier |
| `forms.create` | Créer un dossier |
| `forms.edit` | Modifier un dossier |
| `forms.restitution` | Gérer les restitutions |
| `forms.export` | Exporter PDF et Excel |
| `forms.delete` | Supprimer des dossiers |
| `users.manage` | Gérer les comptes utilisateurs |
| `db.manage` | Accès aux outils d'export/import de base de données |
| `*` | Toutes les permissions (admin) |

> `data_scope: "masked"` : les noms des bénéficiaires sont masqués pour conformité RGPD.

---

## Mise à jour en production

### Debian / LXC

```bash
cd /opt/dotation
git pull origin main
/opt/dotation/.venv/bin/pip install -r backend/requirements.txt
sudo systemctl restart dotation
```

### Windows / IIS

```powershell
cd C:\inetpub\dotation
git pull origin main
C:\inetpub\dotation\.venv\Scripts\pip install -r backend\requirements.txt
nssm restart dotation
```

L'application applique automatiquement les évolutions de schéma de base de données au redémarrage (`ensure_column` — non destructif).

---

## Variables d'environnement

| Variable | Rôle | Valeur dev | Valeur prod |
|---|---|---|---|
| `APP_SECRET_KEY` | Clé de chiffrement des sessions | auto-générée | lire depuis `.app_secret_key` |
| `SESSION_COOKIE_SECURE` | Cookie HTTPS uniquement | `0` | `1` |

> Si `APP_SECRET_KEY` n'est pas définie, l'application cherche automatiquement `backend/.app_secret_key` et génère une clé si le fichier n'existe pas.

---

## Architecture

```
dotation/
├── backend/
│   ├── app.py              # Point d'entrée Flask, blueprints, init DB
│   ├── auth.py             # Login, bcrypt, décorateurs, rate limiting
│   ├── config.py           # Constantes et variables d'environnement
│   ├── database.py         # Connexion SQLite, ensure_column()
│   ├── models/
│   │   ├── forms.py        # CRUD dossiers
│   │   ├── workflow.py     # Calcul des statuts
│   │   ├── settings.py     # Branding et configuration
│   │   ├── catalog.py      # Catalogue ressources et services
│   │   ├── signature.py    # Liens de signature à usage unique
│   │   └── audit.py        # Journal d'audit
│   ├── routes/
│   │   ├── admin.py        # Endpoints admin (comptes, settings, catalogs)
│   │   ├── forms.py        # Endpoints dossiers (CRUD, export)
│   │   ├── pages.py        # Authentification et service HTML
│   │   └── signature.py    # Endpoints signature publique
│   └── pdf/
│       ├── attribution.py  # Génération PDF dossier
│       └── restitution.py  # Génération PDF restitution
├── frontend/               # HTML + JS statique servi par Flask
│   ├── index.html          # Tableau de bord
│   ├── form.html           # Dossier
│   ├── restitution.html    # Restitution
│   ├── signature.html      # Signature publique (sans compte)
│   ├── setup.html          # Assistant de configuration initiale
│   └── admin*.html         # Pages administration
├── scripts/
│   └── deploy-debian.sh    # Script de déploiement automatisé
└── backend/requirements.txt
```

**Base de données SQLite — tables principales :**

| Table | Contenu |
|---|---|
| `dotation_forms` | Dossiers avec `payload_json` |
| `dotation_items` | Lignes de suivi restitution |
| `app_settings` | Paramètres branding et configuration |
| `resource_catalog` | Catalogue des ressources |
| `service_catalog` | Catalogue des services |
| `app_logs` | Journal d'audit global |
| `audit_events` | Historique par dossier |
| `signature_links` | Tokens de signature à usage unique |
| `deleted_items` | Corbeille (soft delete) |

---

## Sécurité

- **Sessions** : cookie `HttpOnly`, `SameSite=Lax`, `Secure` en production
- **CSRF** : token requis sur tous les endpoints JSON authentifiés
- **CSP** : `script-src 'self'` — aucun script inline autorisé
- **Rate limiting** : 10 tentatives de login / 10 min par IP, rate limiting sur les endpoints sensibles
- **Mots de passe** : hashés avec `bcrypt` (coût 12)
- **IP réelle** : transmise par `X-Real-IP` depuis nginx ou IIS

**Points d'attention :**
- `SESSION_COOKIE_SECURE=1` obligatoire en HTTPS
- Ne jamais exposer `backend/users.json` ou `backend/dotation.db` via HTTP
- `backend/.app_secret_key` doit être en lecture seule pour le compte applicatif
- Sauvegarder régulièrement `dotation.db` (copie simple du fichier, application arrêtée ou via `VACUUM INTO`)

---

## Limites SQLite

SQLite convient pour un usage interne modéré :

| Charge | Comportement attendu |
|---|---|
| < 30 utilisateurs simultanés | Confortable |
| 30 à 80 simultanés | Possible selon le volume d'écritures |
| > 80 simultanés ou écritures intensives | Risque de contention — envisager PostgreSQL |

SQLite gère bien les lectures concurrentes. Les écritures sont sérialisées. Pour une organisation de taille importante ou une forte concurrence en écriture, une migration vers PostgreSQL est recommandée.

---

## Développement local

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

export APP_SECRET_KEY="dev-key"
export SESSION_COOKIE_SECURE="0"
python3 backend/app.py
```

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

$env:APP_SECRET_KEY="dev-key"
$env:SESSION_COOKIE_SECURE="0"
python backend\app.py
```

Ouvrir `http://127.0.0.1:5000/`

### Tests

```bash
pytest backend/tests/ -v
pytest backend/tests/test_auth.py       # un fichier spécifique
pytest backend/tests/ -k "test_login"  # filtre par nom
```

### Vérification syntaxe

```bash
python3 -m py_compile backend/app.py
python3 -m py_compile backend/auth.py backend/models/*.py backend/routes/*.py
```
