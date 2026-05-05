# 🌊 À Quai - Guide de Déploiement v3.17.1

## 🎯 Qu'est-ce qu'À Quai ?

**À Quai**, c'est bien plus qu'une application de gestion matérielle. C'est **l'endroit mutualisé** où vous organisez le voyage professionnel de vos collaborateurs.

### La métaphore du voyage

Comme tout voyage, le parcours professionnel dans votre organisation comporte plusieurs étapes :
- 🚀 **L'embarquement** (onboarding) : arrivée d'un nouvel agent, dotation en ressources
- ✈️ **Le voyage** (vie professionnelle) : changement de service, mise à jour des dotations
- 🏝️ **Les escales** (gestion continue) : suivi des ressources, inventaire
- 🏠 **Le retour** (offboarding) : départ de l'agent, restitution des ressources

### Gestion des richesses humaines

À Quai vous aide à :
- ✅ **Accueillir efficacement** vos nouvelles recrues en leur fournissant les ressources adaptées
- ✅ **Suivre les dotations** matérielles tout au long du parcours professionnel
- ✅ **Organiser les restitutions** de manière structurée et traçable
- ✅ **Adapter les ressources** à chaque changement (changement de service, promotion, départ)
- ✅ **Garantir la traçabilité** avec signatures numériques et audit complet

### Pour quels types d'organisations ?

À Quai s'adapte à votre contexte :
- 🏛️ **Collectivités** (mairies, intercommunalités, administrations locales)
- 🏢 **Administrations** (ministères, préfectures, services déconcentrés)
- 🏭 **Entreprises privées** (PME, grandes entreprises)
- 🤝 **Associations** (ONG, structures solidaires)

---

**Version :** 3.17.1-prod | **Branche :** main | **Dernière mise à jour :** 5 mai 2026

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis système](#prérequis-système)
3. [Déploiement rapide (Debian/LXC)](#déploiement-rapide--debianxlc)
4. [Déploiement manuel](#déploiement-manuel)
5. [Configuration initiale](#configuration-initiale)
6. [Vérification du déploiement](#vérification-du-déploiement)
7. [Troubleshooting](#troubleshooting)
8. [Support](#support)

---

## 🎯 Vue d'ensemble technique

À Quai est une application web modulaire (Flask + SQLite) qui digitalise le parcours des dotations matérielles, du onboarding à l'offboarding.

### Cas d'usage concrets

**Scénario 1 : Nouvelle arrivée (Onboarding)**
1. Un nouvel agent arrive dans votre organisation
2. L'admin crée un dossier "Nouvelle arrivée" dans À Quai
3. Les ressources (ordinateur, téléphone, clés, etc.) sont dotées
4. Un lien de signature est envoyé à l'agent (par email ou SMS)
5. L'agent signe numériquement et reçoit une confirmation
6. Tous les documents sont archivés automatiquement

**Scénario 2 : Changement de service**
1. Un agent change de service au sein de l'organisation
2. Un dossier "Mise à jour" est créé
3. Certaines ressources sont reprises, d'autres nouvelles sont dotées
4. Même processus de signature sécurisée
5. Historique complet du parcours de l'agent

**Scénario 3 : Départ de l'agent (Offboarding)**
1. Création d'un dossier "Sortie" pour l'agent
2. Inventaire des ressources à restituer
3. Enregistrement de l'état (bon état, endommagé, manquant)
4. Signature numérique de restitution
5. Clôture du dossier avec rapport d'audit

### Nouvelles fonctionnalités v3.17.1

✅ **Migration SQLite complète**
- Plus de fichier `users.json`, authentification via base SQLite
- Groupes et permissions granulaires
- Utilisateur `admin/admin` créé automatiquement à la première installation

✅ **Setup wizard amélioré**
- Configuration guidée au premier lancement
- Définition de l'organisation et contexte (collectivité, administration, entreprise, association)
- Types de bénéficiaires configurables

✅ **Authentification sécurisée**
- Bcrypt pour le hachage des mots de passe
- CSRF token automatique
- Sessions sécurisées (HTTPS en prod, HTTP en dev)

---

## 🖥️ Prérequis système

| Composant | Version minimale | Recommandé |
|-----------|------------------|-----------|
| Python | 3.11 | 3.11+ |
| pip | 23.0+ | Récent |
| Système d'exploitation | Debian 12+ / Ubuntu 22.04+ | Debian 12, Ubuntu 22.04 |
| Espace disque | 500 MB | 1 GB |
| RAM | 512 MB | 1+ GB |
| Reverse proxy | nginx | nginx ou Apache |

### Dépendances système (Debian/Ubuntu)

```bash
apt-get update
apt-get install -y \
  python3.11 \
  python3.11-venv \
  git \
  nginx \
  curl
```

---

## 🚀 Déploiement rapide (Debian/LXC)

**Durée estimée : 5 minutes**

### Étape 1 : Cloner le repository

```bash
cd /opt
git clone https://github.com/roussim974100/dotation.git
cd dotation
git checkout main  # ⚠️ IMPORTANT : utiliser la branche main
```

### Étape 2 : Créer l'environnement virtuel

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
```

### Étape 3 : Configurer le serveur

```bash
# Copier la configuration nginx
sudo cp deployment/nginx.conf /etc/nginx/sites-available/dotation
sudo ln -s /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Créer le service systemd
sudo cp deployment/dotation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dotation
sudo systemctl start dotation
```

### Étape 4 : Accéder à l'application

```
http://localhost/login
```

Identifiants par défaut :
- **Utilisateur** : `admin`
- **Mot de passe** : `admin`

---

## 🔧 Déploiement manuel (sans script)

### Étape 1 : Préparer l'environnement

```bash
# Créer le répertoire d'installation
mkdir -p /var/www/dotation
cd /var/www/dotation

# Cloner le code
git clone https://github.com/roussim974100/dotation.git .
git checkout main

# Créer l'environnement virtuel
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### Étape 2 : Configurer les permissions

```bash
sudo chown -R www-data:www-data /var/www/dotation
sudo chmod -R 755 /var/www/dotation
sudo chmod -R 775 /var/www/dotation/backend/data  # Base de données
```

### Étape 3 : Configurer nginx

Créer `/etc/nginx/sites-available/dotation` :

```nginx
upstream dotation_app {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://dotation_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /assets/ {
        alias /var/www/dotation/frontend/assets/;
        expires 7d;
    }

    location /css/ {
        alias /var/www/dotation/frontend/css/;
        expires 1h;
    }

    location /js/ {
        alias /var/www/dotation/frontend/js/;
        expires 1h;
    }
}
```

Activer la configuration :

```bash
sudo ln -s /etc/nginx/sites-available/dotation /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Étape 4 : Lancer l'application

```bash
cd /var/www/dotation
source venv/bin/activate
export FLASK_ENV=production
python backend/app.py
```

Ou en arrière-plan avec gunicorn :

```bash
pip install gunicorn
gunicorn -w 4 -b 127.0.0.1:5000 backend.app:app &
```

---

## ⚙️ Configuration initiale

### Première connexion (Setup Wizard)

1. **Accéder à l'application** : `http://server-ip/login`
2. **Se connecter** avec les identifiants par défaut :
   - Utilisateur : `admin`
   - Mot de passe : `admin`
3. **Redirection automatique** vers `/setup.html`
4. **Remplir le wizard en 5 étapes** :
   - **Étape 1** : Type d'organisation (collectivité, administration, entreprise, association)
   - **Étape 2** : Identité (nom, email DPO)
   - **Étape 3** : Contact support
   - **Étape 4** : Types de bénéficiaires
   - **Étape 5** : Récapitulatif et validation

5. **Accès à l'admin** après configuration

### Créer les premiers utilisateurs

Après la configuration initiale, aller dans **Administration → Comptes** pour :
- Créer des utilisateurs
- Assigner des groupes
- Gérer les permissions

### Groupes et permissions par défaut

| Groupe | Permissions | Usage |
|--------|------------|-------|
| **admin** | Toutes | Administrateurs système |
| **user** | Accès formulaires | Utilisateurs standards |

**Permissions disponibles** :
- `users.manage` - Gestion des comptes et groupes
- `forms.view_all` - Voir tous les dossiers
- `forms.read_list` - Lire la liste des dossiers
- `db.manage` - Gestion de la base de données (export/import)
- `unc.view_all` - Voir les UNC

---

## ✅ Vérification du déploiement

### Test de connexion

```bash
curl -X POST http://localhost/login \
  -d "username=admin&password=admin"
```

### Vérifier la base de données

```bash
cd /var/www/dotation
sqlite3 backend/data/dotation.db "SELECT * FROM users LIMIT 1;"
sqlite3 backend/data/users.db "SELECT * FROM groups;"
```

### Consulter les logs

```bash
# Logs nginx
sudo tail -f /var/log/nginx/error.log

# Logs application
journalctl -u dotation -f  # (si service systemd)
```

### Accès à l'application

- **URL** : `http://server-ip`
- **Login** : `admin` / `admin`
- **Admin panel** : Après connexion

---

## 🐛 Troubleshooting

### Erreur : "CSRF invalid" au login

**Cause** : Les cookies de session ne sont pas persistés  
**Solution** :
```python
# Vérifier dans backend/app.py
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
```

### Erreur : "Cannot find users.db"

**Cause** : La base SQLite n'a pas été initialisée  
**Solution** : L'app crée automatiquement `users.db` au premier lancement

```bash
python backend/app.py  # Lance l'initialisation automatique
```

### Erreur : "setup.html not found"

**Cause** : Fichier frontend manquant  
**Solution** : Vérifier que `frontend/setup.html` existe

```bash
ls -la frontend/setup.html
```

### Erreur : "admin/admin ne fonctionne pas"

**Cause** : L'utilisateur `admin` n'a pas été créé automatiquement  
**Solution** : Vérifier la base SQLite

```bash
sqlite3 backend/data/users.db "SELECT * FROM users WHERE username='admin';"
```

Si l'utilisateur n'existe pas, le créer manuellement (voir section Admin)

### Erreur : "Permission denied" sur les fichiers

**Cause** : Les permissions nginx ne sont pas correctes  
**Solution** :
```bash
sudo chown -R www-data:www-data /var/www/dotation
sudo chmod -R 755 /var/www/dotation
sudo chmod -R 775 /var/www/dotation/backend/data
```

---

## 📊 Structure des répertoires

```
/var/www/dotation/
├── backend/
│   ├── app.py                 # Application Flask
│   ├── auth.py                # Authentification
│   ├── database.py            # Gestion BD
│   ├── routes/                # Routes de l'API
│   ├── models/                # Modèles de données
│   ├── data/
│   │   ├── dotation.db       # BD application
│   │   └── users.db          # BD utilisateurs (NEW v3.17.1)
│   └── requirements.txt       # Dépendances Python
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── setup.html             # Setup wizard (NEW v3.17.1)
│   ├── admin.html
│   ├── js/
│   │   ├── login.js
│   │   ├── setup.js           # Script wizard (NEW v3.17.1)
│   │   └── ...
│   ├── css/
│   └── assets/
├── deployment/
│   ├── nginx.conf
│   ├── dotation.service       # Service systemd
│   └── ...
└── README.md / DEPLOYMENT_GUIDE.md
```

---

## 🔐 Sécurité en production

### HTTPS obligatoire

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;
    
    # Rediriger HTTP vers HTTPS
    return 301 https://$host$request_uri;
}
```

### Variables d'environnement recommandées

```bash
export FLASK_ENV=production
export FLASK_DEBUG=0
export SECRET_KEY=$(openssl rand -hex 32)
```

### Firewall

```bash
# UFW (Debian/Ubuntu)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Backup de la base de données

```bash
# Backup quotidien
0 2 * * * /usr/bin/sqlite3 /var/www/dotation/backend/data/dotation.db ".dump" | gzip > /backup/dotation-$(date +\%Y\%m\%d).sql.gz
0 3 * * * /usr/bin/sqlite3 /var/www/dotation/backend/data/users.db ".dump" | gzip > /backup/users-$(date +\%Y\%m\%d).sql.gz
```

---

## 📞 Support

Pour toute question ou problème :

1. **Vérifier les logs** : `/var/log/nginx/error.log`
2. **Consulter le README.md** du repository
3. **Contacter l'éditeur** : via le formulaire Contact de l'application

---

## 📝 Version et branche

| Élément | Valeur |
|--------|--------|
| **Version** | 3.17.1-prod |
| **Branche** | main |
| **Repository** | https://github.com/roussim974100/dotation |
| **Changelog** | Voir git log ou releases GitHub |

---

**Guide préparé pour déploiement chez clients - À jour en mai 2026**
