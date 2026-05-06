# À Quai — Gestion des dotations matérielles

**Version :** `3.17.1-dev` | **Stack :** Flask · SQLite · Vanilla JS | **Licence :** usage interne  
**Statut :** Production ✅ | **Dernière MAJ :** Mai 2026

---

## 🚀 Installation rapide (5 minutes)

### Déploiement automatisé — Debian 12 / LXC

**Une seule commande pour une installation complète :**

```bash
sudo bash setup/install-debian.sh
```

C'est tout ! Le script :
- ✅ Installe Python, nginx, Gunicorn
- ✅ Crée la base de données
- ✅ Configure le service systemd
- ✅ Lance l'application

**Puis accédez à :** `http://<IP_DE_VOTRE_SERVEUR>`

### 🔓 Identifiants par défaut

L'application est prête immédiatement. Connectez-vous avec :

| Champ | Valeur |
|---|---|
| **Utilisateur** | `admin` |
| **Mot de passe** | `admin` |

### 🔒 ⚠️ SÉCURITÉ — À FAIRE EN PREMIER

**Vous DEVEZ changer le mot de passe admin immédiatement :**

1. Allez dans **Administration → Utilisateurs**
2. Cliquez sur `admin`
3. Définissez un mot de passe fort (minimum 12 caractères)
4. Enregistrez

> Cet identifiant par défaut n'existe que pour l'initialisation et doit être sécurisé avant toute autre action.

### Configurer votre organisation

1. Connecté en `admin`, allez dans **Paramètres**
2. Remplissez :
   - Nom de l'organisation
   - Contexte (collectivité, entreprise, etc.)
   - Contacts (support, DPO)
   - Logo et personnalisation
3. Créez vos utilisateurs métier et assignez les groupes

**[Guide complet de configuration →](DEPLOYMENT_GUIDE.md)**

---

## 🌊 À propos d'À Quai

### La vision

> **À Quai, c'est l'application pour organiser son voyage professionnel.**
>
> Comme pour un voyage, il y a le **onboarding** et l'**offboarding**. À Quai vous aide dans la **gestion des richesses humaines** dans votre organisation.

### Pourquoi cette métaphore ?

Tout comme un voyage, le parcours professionnel d'un collaborateur comporte des étapes clés :
- **L'embarquement** : accueil et dotation initiale (onboarding)
- **Le voyage** : vie professionnelle avec changements et évolutions
- **Le retour** : départ et restitution des ressources (offboarding)

À Quai accompagne votre organisation à chaque étape, en centralisant la gestion des dotations matérielles et en garantissant une traçabilité complète du parcours.

---

## Fonctionnalités principales

### 📋 Gestion des dossiers

- Créer, modifier et verrouiller des dossiers d'attribution
- 4 types de dossier : nouvelle arrivée, changement de service, mise à jour, sortie
- Ressources configurables par l'admin (champs métier, suivi, restitution)
- Import / export CSV du catalogue de services

### 🖊️ Signature sécurisée

- Signature directe sur l'écran ou via lien à usage unique
- Signature de restitution distincte
- Protection de la signature dans les PDF selon les droits du profil

### 📦 Restitution de ressources

- Écran dédié : état par ressource (conforme, dégradé, manquant…), commentaires, dates
- PDF de restitution distinct du PDF d'attribution
- Traçabilité complète du parcours

### 📊 Exports et rapports

- Export PDF dossier et restitution
- Export Excel (dossiers + ressources)
- Export groupé multi-sélection
- Journal d'audit complet

### ⚙️ Administration complète

- Gestion des comptes, groupes et permissions
- Catalogue des services et ressources (ordre, activation, champs)
- Personnalisation : logo, couleur, nom, email DPO, contact support
- Contexte organisationnel : collectivité, administration, entreprise, association
- Corbeille avec restauration
- Mode sombre intégré

### 🎨 White-label

- Setup wizard guidé au premier lancement
- Types de bénéficiaires configurables selon le contexte
- Aucune référence au déploiement initial dans une install neuve

---

## Sommaire documentation

- [Prérequis système](#prérequis)
- [Installation rapide — Debian/LXC](#déploiement-rapide--debian--lxc)
- [Installation manuelle — Debian/Ubuntu](#déploiement-manuel--debian--ubuntu)
- [Installation Windows — IIS + Waitress](#déploiement-windows--iis--waitress)
- [Proxy inverse existant](#déploiement-derrière-un-reverse-proxy-existant)
- [Sécurité initiale](#-sécurité-initiale)
- [Mise à jour en production](#mise-à-jour-en-production)
- [Configuration avancée](#avancé)

---

## Prérequis

| Composant | Version minimale |
|---|---|
| Python | 3.11+ |
| pip | récent |
| Système | Debian 12+, Ubuntu 22.04+, Windows Server 2019+ |
| Reverse proxy | nginx (Linux) ou IIS avec ARR (Windows) |

Dépendances Python (installées automatiquement) :
- flask==3.1.3
- bcrypt==5.0.0
- fpdf2==2.8.7
- werkzeug==3.1.7

> ⚠️ **SQLite en production :** la base SQLite doit être sur le disque local du serveur. Ne jamais placer `dotation.db` sur un partage réseau SMB — risque de corruption par verrouillage.

---

## Déploiement rapide — Debian / LXC

Un script automatisé configure tout pour une LXC ou VM Debian 12+ vierge :

```bash
sudo bash setup/install-debian.sh
```

**Le script effectue automatiquement :**
1. Installation des paquets système (Python 3, nginx, git)
2. Clonage du dépôt dans `/opt/dotation`
3. Création du venv Python et installation des dépendances
4. Installation de Gunicorn (serveur WSGI production)
5. Initialisation de la base de données
6. Configuration du service systemd `dotation`
7. Configuration nginx en reverse proxy (port 80)
8. Vérifications finales (services, ports, logs)

### Personnaliser la branche déployée

Par défaut, le script utilise la branche `dev`. Pour une autre branche :

```bash
GIT_BRANCH=main sudo bash setup/install-debian.sh
```

### Après l'installation

L'application est accessible immédiatement :

```
http://<IP_DU_SERVEUR>
```

Vérifier le statut du service :

```bash
systemctl status dotation
journalctl -u dotation -n 50
```

---

## ⚠️ Sécurité initiale

### Changement du mot de passe par défaut

Immédiatement après l'installation :

1. Accédez à `http://<IP>/login`
2. Connectez-vous : **admin** / **admin**
3. Allez dans **Administration → Utilisateurs**
4. Cliquez sur l'utilisateur `admin`
5. Changez le mot de passe vers quelque chose de fort (minimum 12 caractères)
6. Enregistrez

### Création des premiers utilisateurs

1. Allez dans **Administration → Utilisateurs**
2. Créez les comptes de vos collaborateurs
3. Assignez-les aux groupes appropriés :
   - **admin** : accès complet, gestion utilisateurs
   - **direction** : visualisation dashboard + gestion dossiers
   - **gestion** : création/modification dossiers
   - **redaction** : lecture seule + création formulaires
   - **lecture** : lecture seule

### HTTPS en production

En production, toujours terminer TLS en amont :
- Via un **reverse proxy** (nginx, HAProxy, Traefik)
- Via **Proxmox/HAProxy** si infrastructure centralisée
- Via **IIS + certificat Windows** si sur Windows Server

L'application supporte transparemment le header `X-Forwarded-Proto` pour détecter le HTTPS.

---

## Déploiement manuel — Debian / Ubuntu

Pour une installation pas à pas avec contrôle total :

### 1. Paquets système

```bash
sudo apt update
sudo apt install -y \
  python3.11 python3.11-venv python3.11-dev \
  python3-pip python3-dev \
  git curl nginx \
  ca-certificates net-tools
```

### 2. Récupérer le projet

```bash
sudo mkdir -p /opt/dotation
sudo chown $USER:$USER /opt/dotation
git clone --branch dev https://github.com/roussim974100/dotation.git /opt/dotation
cd /opt/dotation
```

### 3. Environnement Python

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
pip install gunicorn
```

### 4. Clé secrète applicative

```bash
python3 -c "import secrets; print(secrets.token_hex(32))" > backend/.app_secret_key
chmod 600 backend/.app_secret_key
```

### 5. Initialiser les bases de données

```bash
source venv/bin/activate
cd /opt/dotation/backend
python -c "from app import init_db, init_users_db; init_db(); init_users_db()"
```

### 6. Service systemd

Créer `/etc/systemd/system/dotation.service` :

```ini
[Unit]
Description=À Quai — Dotation via Gunicorn
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/dotation/backend
Environment="FLASK_ENV=production"
Environment="PYTHONUNBUFFERED=1"
Environment="HOME=/opt/dotation/backend/data"
ExecStart=/opt/dotation/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 120 app:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Ensuite :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dotation
sudo systemctl status dotation
```

### 7. Nginx — proxy HTTP/HTTPS

Créer `/etc/nginx/sites-available/dotation` :

```nginx
upstream dotation_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    listen [::]:80;
    server_name dotation.exemple.local;
    
    client_max_body_size 5M;

    location / {
        proxy_pass http://dotation_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activer la configuration :

```bash
sudo ln -s /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## Déploiement Windows — IIS + Waitress

> ⚠️ **ATTENTION** — Cette approche **n'a pas été testée en production**. Elle est fournie à titre informatif.
> 
> Le déploiement standard et validé est **Debian 12+ avec Gunicorn + nginx**. Si vous devez utiliser Windows, contactez le support pour discuter des alternatives.

Pour Windows Server avec IIS existant.

### Prérequis IIS

Via le **Gestionnaire de serveur**, installer :
- Module **URL Rewrite** — [téléchargement](https://www.iis.net/downloads/microsoft/url-rewrite)
- Module **Application Request Routing (ARR)** — [téléchargement](https://www.iis.net/downloads/microsoft/application-request-routing)

Activer le proxy dans ARR : `IIS Manager → Application Request Routing Cache → Server Proxy Settings → cocher "Enable proxy"`.

### 1. Installer Python

[Télécharger Python 3.11+](https://www.python.org/downloads/) et cocher **"Add Python to PATH"**.

### 2. Préparer le projet

```powershell
python -m venv C:\inetpub\dotation\venv
C:\inetpub\dotation\venv\Scripts\pip install -r C:\inetpub\dotation\backend\requirements.txt
C:\inetpub\dotation\venv\Scripts\pip install waitress
```

### 3. Lancer Waitress comme service

Télécharger **NSSM** ([nssm.cc](https://nssm.cc/download)) :

```powershell
nssm install dotation "C:\inetpub\dotation\venv\Scripts\waitress-serve.exe"
nssm set dotation AppParameters "--port=5000 --threads=4 backend.app:app"
nssm set dotation AppDirectory "C:\inetpub\dotation\backend"
nssm start dotation
```

### 4. Configurer IIS comme proxy

Créer `C:\inetpub\dotation\web.config` :

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
  </system.webServer>
</configuration>
```

---

## Déploiement derrière un reverse proxy existant

Si une infrastructure centralisée gère déjà HTTPS (Proxmox, HAProxy, Traefik), À Quai tourne en HTTP simple.

**Architecture :**
```
Internet ──HTTPS──▶ Reverse proxy (certificat) ──HTTP──▶ Serveur app (port 5000)
```

Flask lit automatiquement le header `X-Forwarded-Proto` transmis par le proxy. **Point critique** : si `SESSION_COOKIE_SECURE=1` mais que ce header n'est pas transmis, boucle de login infinie.

Configuration du service :

```ini
Environment="SESSION_COOKIE_SECURE=1"
```

Et vérifier que le reverse proxy transmet :

```
X-Forwarded-Proto: https
X-Forwarded-For: <IP_CLIENT>
X-Forwarded-Host: <DOMAINE_PUBLIC>
```

---

## Mise à jour en production

### Depuis la branche dev (test)

```bash
cd /opt/dotation
git pull origin dev
source venv/bin/activate
pip install -r backend/requirements.txt
systemctl restart dotation
```

**Les bases de données sont préservées** — les tables existantes ne sont jamais supprimées, seules les manquantes sont créées.

---

# Avancé

## Variables d'environnement

| Variable | Par défaut | Utilité |
|---|---|---|
| `FLASK_ENV` | `production` | Mode de Flask |
| `SESSION_COOKIE_SECURE` | `0` | Forcer les cookies sécurisés (HTTPS seulement) |
| `DEBUG` | `0` | Mode debug (JAMAIS en production) |
| `GIT_BRANCH` | `dev` | Branche à déployer (pour le script) |

Exemple au démarrage du service :

```bash
export SESSION_COOKIE_SECURE=1
export FLASK_ENV=production
python backend/app.py
```

## Architecture

**Frontend :**
- Vanilla JS + CSS3 (pas de dépendances JavaScript)
- HTML5 sémantique
- Responsive, accessibilité WCAG 2.1

**Backend :**
- Flask 3.1.3
- SQLite (base locale)
- Gunicorn 20+ (serveur WSGI production)
- Bcrypt pour les mots de passe

**Stockage :**
- `/opt/dotation/backend/dotation.db` — base métier (dossiers, ressources, signatures)
- `/opt/dotation/backend/users.db` — base authentification (utilisateurs, groupes, permissions)
- `/opt/dotation/backend/data/` — uploads, PDF, documents

## Sécurité

- ✅ CSRF protection sur tous les POST/PUT/PATCH/DELETE
- ✅ Mots de passe hashés en bcrypt
- ✅ Headers de sécurité : CSP, X-Frame-Options, X-Content-Type-Options
- ✅ Authentification par session cookie
- ✅ Gestion des groupes et permissions granulaires
- ✅ Audit complet des actions utilisateur
- ✅ Journaux d'accès

## Limites SQLite

SQLite convient pour :
- Petites à moyennes organisations (< 10k dossiers)
- Équipes réduites (< 50 utilisateurs)
- Usage métier courant

**Ne pas utiliser SQLite si :**
- Forte concurrence (centaines de requêtes simultanées)
- Beaucoup d'écritures en parallèle
- Nécessité de réplication entre serveurs

**Évolution future :** migration vers PostgreSQL possible, elle nécessiterait une migration de schéma mais l'application est conçue pour y être compatible.

## Développement local

### Cloner et installer

```bash
git clone --branch dev https://github.com/roussim974100/dotation.git
cd dotation
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install pytest pytest-cov
```

### Lancer en dev

```bash
cd backend
python app.py
```

Accéder à `http://localhost:5000/login`.

### Tests

```bash
pytest tests/
```

---

## Support et contribution

**Support applicatif :** [computing.bs@gmail.com](mailto:computing.bs@gmail.com)

**Développement :** [GitHub — roussim974100/dotation](https://github.com/roussim974100/dotation)

Toute contribution ou signalement de bug est bienvenu.

---

**© 2026 À Quai — Tous droits réservés.**
