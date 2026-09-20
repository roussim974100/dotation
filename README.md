# À Quai — Gestion des dotations matérielles

> **À Quai** — version `3.59.0`. La même version se **promeut** de `dev` (développement) à `preprod` (préproduction) puis à `prod` (production) : l'environnement d'un serveur est défini par son script de déploiement, pas par les fichiers.
> Pour **déployer ou mettre à jour** : `sudo bash deploy.sh` (production, branche [`prod`](https://github.com/roussim974100/dotation/tree/prod)), `sudo bash deploy-preprod.sh` (préproduction, branche `preprod`) ou `sudo bash deploy-dev.sh` (développement, branche `dev`) — voir [Mise à jour en production](#mise-à-jour-en-production).
> Nouveautés depuis la 3.18 : voir le [CHANGELOG](CHANGELOG.md). Pour contribuer : section [Développement local](#développement-local) en bas de page.

**Version :** `3.59.0` | **Stack :** Flask · SQLite · Vanilla JS | **Licence :** usage interne  
**Statut :** voir l'environnement (pastille DEV / PREPROD, absente en production) | **Dernière MAJ :** 19 septembre 2026

---

## 🔐 Credentials par défaut (après installation)

```
Utilisateur : admin
Mot de passe : admin
```

⚠️ **À changer immédiatement après la première connexion**

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

---

## ✅ Première connexion

**L'application est accessible immédiatement après l'installation.**

### Accès

```
http://<IP_DE_VOTRE_SERVEUR>
```

Remplacez `<IP_DE_VOTRE_SERVEUR>` par l'IP de votre machine (ex: `http://192.168.1.50`).

> **Aucun port à ajouter.** L'installation place nginx (ou IIS sous Windows) sur le **port 80**, celui que le navigateur utilise par défaut : `http://192.168.1.50` suffit. N'essayez pas `http://<IP>:5000` : le service de l'application (gunicorn) n'écoute que **en local** sur le port 5000, par sécurité, et refusera la connexion depuis le réseau (`ERR_CONNECTION_REFUSED`). Derrière un reverse proxy HTTPS (Traefik, HAProxy…), utilisez l'adresse publique configurée, par exemple `https://aquai.exemple.fr`.
>
> Pour vérifier depuis le serveur lui-même que l'application tourne : `curl -sI http://127.0.0.1:5000/login | head -1` doit répondre `200`.

### Identifiants de connexion

Utilisez ces identifiants pour votre première connexion :

```
Utilisateur : admin
Mot de passe : admin
```

---

## 🔒 Sécurité : Changement du mot de passe (OBLIGATOIRE)

**Vous DEVEZ changer le mot de passe `admin` immédiatement après votre première connexion.**

1. Connectez-vous avec `admin` / `admin`
2. Allez dans **Administration → Utilisateurs**
3. Cliquez sur le compte `admin`
4. Changez le mot de passe vers quelque chose de sécurisé (minimum 12 caractères, majuscules, minuscules, chiffres)
5. Enregistrez

> ⚠️ Ne pas sécuriser ce compte immédiatement est un risque de sécurité critique. Cet identifiant par défaut n'existe que pour l'initialisation.

---

## ⚙️ Configuration de l'organisation

Une fois connecté en `admin` avec le nouveau mot de passe, allez dans **Paramètres** pour configurer :

1. **Nom de l'organisation** — Comment s'appelle votre structure
2. **Contexte organisationnel** — Collectivité, entreprise, administration, association
3. **Contacts** — Email support et DPO
4. **Personnalisation** — Couleur thème, logo, nom d'application

Après cela, créez vos utilisateurs métier et assignez-les aux groupes appropriés.

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

### 🗃️ Parc matériel et stocks

Chaque ressource a un **mode de suivi**, choisi dans l'assistant de création (Administration > Ressources) :

- **Objet individuel** (ordinateur, badge, véhicule…) : historique de vie de chaque objet (attribué, restitué, dégradé, perdu, réformé, en réparation…), réservation dans un brouillon, transferts, import CSV du parc initial, indicateurs.
- **Stock par quantité** (vêtements par taille, consommables) : le stock baisse à chaque remise signée, remonte à chaque retour en bon état et revient si le dossier est supprimé. Réception, ajustement d'inventaire (justifié) et perte se saisissent dans *Parc matériel > Stocks*, avec un **seuil d'alerte** par ressource.
- **Sans suivi individuel** et **accès numérique** : pas d'historique par objet.

La consultation est ouverte à qui voit les dossiers ; les actions de gestion demandent le droit `parc.manage`. Les noms des détenteurs sont masqués pour les groupes à portée « masquée » et anonymisés après la durée de conservation réglable (5 ans par défaut).

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

Par défaut, le script utilise la branche `main` (version stable). Pour une autre branche :

```bash
GIT_BRANCH=dev sudo bash setup/install-debian.sh
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
git clone --branch main https://github.com/roussim974100/dotation.git /opt/dotation
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

### Adresse IP des clients et limitation des connexions

**Aucun réglage n'est nécessaire.** À chaque requête, l'application regarde qui l'appelle directement (`backend/proxy.py`) :

| Situation | Adresse de l'appelant direct | Comportement |
|---|---|---|
| Derrière un reverse proxy sur la même machine ou le même réseau privé (cas courant) | loopback ou privée (`127.0.0.1`, `10.x`, `172.16-31.x`, `192.168.x`) | Les en-têtes `X-Forwarded-*` sont lus : l'IP réelle du client est utilisée. |
| Accès direct depuis Internet | IP publique | Les en-têtes `X-Forwarded-*` sont **ignorés** (ils seraient falsifiables). |

La limitation des tentatives de connexion (10 par 10 minutes et par IP) et les limites de débit des API s'appuient sur cette IP fiable. Le même code fonctionne donc derrière un proxy comme en accès direct.

Deux limites : un poste du **même réseau privé** que l'application, sans reverse proxy, peut encore forger `X-Forwarded-For` (exposition limitée au LAN) ; et un proxy à **IP publique** (par exemple un load balancer cloud) n'est pas reconnu automatiquement, il faut alors `APP_TRUSTED_PROXIES=1`.

---

## Mise à jour en production

### Méthode recommandée : les scripts de déploiement

Trois scripts, chacun **figé sur sa branche** (impossible de déployer la mauvaise par erreur) :

| Serveur | Commande | Branche déployée |
|---|---|---|
| **Production** | `cd /opt/dotation && sudo bash deploy.sh` | `prod` |
| **Préproduction** | `cd /opt/dotation && sudo bash deploy-preprod.sh` | `preprod` |
| **Développement** | `cd /opt/dotation && sudo bash deploy-dev.sh` | `dev` |

Option commune : `--force` écrase des modifications locales de fichiers suivis par git (sans elle, le script refuse et les liste).

La logique est partagée dans `setup/deploy-common.sh` ; seuls la branche et le nom changent d'un script à l'autre.

Le script, dans l'ordre :

1. **sauvegarde** cohérente des bases dans `backend/db_backups/avant_maj_<date>/` ;
2. récupère le code de la branche du script (`origin/prod` ou `origin/dev`) ;
3. installe les **dépendances Python dans le venv réellement utilisé par le service** (lu dans le fichier systemd, il n'a donc pas besoin de savoir si le venv est `/opt/dotation/venv` ou `/opt/dotation/backend/venv`) ;
4. redémarre le service et **vérifie qu'il répond** ; sinon il affiche l'erreur et les commandes pour revenir en arrière.

Les bases sont préservées : les tables existantes ne sont jamais supprimées, seules les manquantes sont créées au démarrage.

> **Règle d'or : après chaque `git pull`, toujours réinstaller les dépendances.** Une nouvelle version peut en ajouter (par exemple `cryptography` pour le chiffrement des sauvegardes) ; sans elles, le service ne démarre pas et le reverse proxy répond « 502 Bad Gateway ». Le script s'en charge.

### Méthode manuelle

```bash
cd /opt/dotation
git pull origin main
# Le venv est celui du service : voir la ligne ExecStart de /etc/systemd/system/dotation.service
grep ExecStart /etc/systemd/system/dotation.service
/opt/dotation/backend/venv/bin/pip install -r backend/requirements.txt   # adapter au chemin lu ci-dessus
systemctl reset-failed dotation
systemctl restart dotation
curl -sI http://127.0.0.1:5000/login | head -1                            # doit répondre 200
```

Ne jamais lancer `pip install` sans passer par le `pip` du venv (Debian répond `externally-managed-environment`) et ne jamais utiliser `--break-system-packages`.

### Première mise à jour depuis une ancienne version (à lire)

Les installations existantes ont l'**ancien** `deploy.sh`, qui récupère le code et redémarre **sans installer les dépendances et sans sauvegarder**. Comme c'est lui qui s'exécute lors de la première mise à jour, procéder ainsi :

1. **Sauvegarder les bases** (une migration de schéma ne s'annule pas) : *Administration > Base de données > Exporter*, ou copier `backend/dotation.db` et `backend/users.db` service arrêté.
2. Lancer la mise à jour habituelle : `sudo ./deploy.sh` (ancien script). Le nouveau code, dont le nouveau `deploy.sh`, est alors en place.
3. **Relancer une seconde fois : `sudo bash deploy.sh`.** Ce passage, avec le nouveau script, installe les dépendances manquantes, sauvegarde, redémarre et **vérifie que l'application répond**.

Si une dépendance manque après l'étape 2, l'application **démarre quand même** : seules les sauvegardes chiffrées sont indisponibles (message explicite dans l'administration) jusqu'à l'étape 3. À partir de là, `sudo bash deploy.sh` suffit pour toutes les mises à jour suivantes.

### Publier une nouvelle version (mainteneur)

Les versions avancent d'un environnement à l'autre par **promotion** (`dev` → `preprod` → `prod`), faite **directement sur GitHub** par *Pull Request* :

1. Développer et tester sur `dev` (`python -m pytest tests -q`).
2. **Promouvoir dev vers preprod** : sur GitHub, *Pull requests* → *New pull request* → base `preprod` ← compare `dev` → *Create pull request* → *Merge pull request* (« Create a merge commit »).
3. Déployer sur la **préproduction** : `sudo bash deploy-preprod.sh`, avec une **copie de la base de production** pour vérifier les migrations.
4. Une fois validée : **promouvoir preprod vers prod** de la même façon (base `prod` ← compare `preprod`).
5. Faire d'abord soi-même la mise à jour de sa propre production avec `sudo bash deploy.sh`.
6. Communiquer aux clients : `cd /opt/dotation && sudo bash deploy.sh` (et, pour la toute première mise à jour depuis une ancienne version, la procédure ci-dessus).

Les corrections faites directement sur `preprod` ou `prod` sont à reporter dans `dev`, faute de quoi une promotion ultérieure les écraserait.

> Le dossier `backend/venv/` est suivi par git (héritage) : `deploy.sh` l'ignore dans son contrôle des modifications locales. Ne pas le retirer de git sans protéger les serveurs existants, un `git pull` supprimerait alors leur venv.

### Nouvelle version disponible et mise à jour depuis le navigateur

**Bandeau « nouvelle version »** (activé par défaut) : dans *Administration*, l'application compare sa version à celle de la branche de son canal sur GitHub (`dev` pour une version `-dev`, `preprod` pour `-preprod`, `prod` sinon) et affiche « Nouvelle version X disponible » avec le lien vers les notes de version. La vérification est faite au plus toutes les 6 heures, sans jamais ralentir la page ; sans accès à Internet elle échoue en silence. Pour la couper : `APP_UPDATE_CHECK=0`.

**Bouton « Mettre à jour maintenant »** (facultatif, **désactivé par défaut**) : à activer une seule fois sur le serveur.

```bash
cd /opt/dotation
sudo bash setup/install-web-update.sh          # installe l'unité de surveillance, propose de redémarrer le service
sudo bash setup/install-web-update.sh --uninstall   # pour le retirer
```

Comment ça marche, et pourquoi c'est sûr :
- l'application **ne lance aucune commande** : elle dépose un simple fichier de demande (`<données>/update/request.json`) ;
- une unité systemd (`dotation-update.path`) surveille ce fichier et lance `deploy.sh` (ou `deploy-dev.sh`) **en root** ; la branche est figée, le contenu de la demande n'est jamais lu ;
- l'administrateur doit avoir le droit `users.manage` **et retaper son mot de passe** ; l'action est inscrite au journal d'audit ;
- avant la mise à jour, les bases sont sauvegardées ; si la nouvelle version ne répond pas, **le code et les bases sont rétablis automatiquement** ;
- la page suit la progression (sauvegarde, code, dépendances, redémarrage) et annonce la fin ou l'échec ; le journal complet est dans `<données>/update/update.log`.

Non disponible sous Windows (le bandeau reste affiché, avec la commande à lancer).

### Dépannage après une mise à jour

| Symptôme | Cause probable | Vérification / correctif |
|---|---|---|
| **502 Bad Gateway** (Traefik, nginx…) | Le service ne tourne pas : rien n'écoute sur le port de l'application | `systemctl status dotation` puis `journalctl -u dotation -n 40 --no-pager \| grep -v systemd` |
| `ModuleNotFoundError: No module named '…'` | Dépendance non installée, ou installée dans un autre venv (`cryptography` seule est facultative au démarrage) | `/chemin/du/venv/bin/pip install -r backend/requirements.txt` avec **le venv de la ligne `ExecStart`** |
| `Start request repeated too quickly` | systemd a bloqué le service après 5 échecs | Corriger l'erreur, puis `systemctl reset-failed dotation && systemctl restart dotation` |
| `error: externally-managed-environment` | `pip` du système utilisé au lieu de celui du venv | Utiliser le `pip` du venv (voir ci-dessus) |
| `404 Not Found` sur une page récente (ex. `/parc.html`) | Le serveur tourne avec une ancienne version du code | Vérifier la branche déployée (`git -C /opt/dotation log -1`) et refaire la mise à jour |
| Base corrompue après remplacement d'un `.db` | Anciens fichiers `-wal` / `-shm` laissés à côté | Arrêter le service, supprimer `*.db-wal` et `*.db-shm`, puis copier la base |

Pour revenir en arrière : arrêter le service, recopier les fichiers de `backend/db_backups/avant_maj_<date>/`, supprimer les `-wal` / `-shm`, revenir au commit précédent (`git checkout <commit>`) et redémarrer.

---

# Avancé

## Variables d'environnement

| Variable | Par défaut | Utilité |
|---|---|---|
| `FLASK_ENV` | `production` | Mode de Flask |
| `SESSION_COOKIE_SECURE` | `0` | Forcer les cookies sécurisés (HTTPS seulement) |
| `DEBUG` | `0` | Mode debug (JAMAIS en production) |
| `GIT_BRANCH` | `main` | Branche à déployer (pour le script) |
| `APP_SECRET_KEY` | fichier `.app_secret_key` généré au 1er démarrage | Clé de signature des sessions (à fixer en environnement multi-serveurs) |
| `APP_MAX_UPLOAD_MB` | `100` | Taille maximale d'une requête (import CSV, logo, restauration de base) |
| `APP_UPDATE_CHECK` | `1` | `0` désactive la vérification « nouvelle version » (aucune requête vers GitHub) |
| `APP_UPDATE_CHECK_URL` | GitHub, branche du canal | Adresse (http/https) du fichier `branding.js` à interroger, pour un miroir interne |
| `APP_ALLOW_WEB_UPDATE` | `0` | Posé par `setup/install-web-update.sh` : affiche le bouton de mise à jour (exige l'unité systemd installée) |
| `APP_TRUSTED_PROXIES` | automatique | Surcharge **facultative** de la confiance dans `X-Forwarded-*` : `0` = jamais, `N` = forcer N proxys (proxy à IP publique). Voir « Adresse IP des clients » |

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
- ✅ Limitation des tentatives de connexion fondée sur l'IP réelle (non falsifiable par `X-Forwarded-For`)
- ✅ Exports interdits aux groupes à portée de données « masquée » (RGPD)
- ✅ Échappement HTML des données saisies, plafond de taille des requêtes

Dernier audit : voir [`docs/AUDIT_SECURITE_2026-09.md`](docs/AUDIT_SECURITE_2026-09.md).

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
