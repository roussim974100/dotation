# 🚀 Installation automatisée d'À Quai

Ce dossier contient des scripts d'installation automatisée pour déployer À Quai sur différents systèmes d'exploitation.

## 📋 Prérequis

### Debian / Ubuntu
- **Python** 3.11 ou supérieur
- **Git**
- **Accès root** (sudo) pour l'installation
- **Connexion Internet** pour télécharger le code et les dépendances

### Windows
- **Python** 3.11 ou supérieur (à installer manuellement depuis python.org)
- **Git** (à installer manuellement depuis git-scm.com)
- **PowerShell** 5.0+ (inclus dans Windows 10+)
- **Privilèges administrateur** pour l'installation

---

## 🐧 Installation sur Debian / Ubuntu

### Étape 1 : Télécharger le script

```bash
curl -o install-debian.sh https://raw.githubusercontent.com/roussim974100/dotation/main/setup/install-debian.sh
```

### Étape 2 : Rendre le script exécutable

```bash
chmod +x install-debian.sh
```

### Étape 3 : Exécuter l'installation

```bash
sudo bash install-debian.sh
```

Le script va :
- ✅ Vérifier/installer les prérequis (Python 3.11, git, nginx)
- ✅ Cloner ou mettre à jour le code d'À Quai
- ✅ Créer un environnement virtuel Python
- ✅ Installer les dépendances
- ✅ Configurer nginx
- ✅ Créer un service systemd
- ✅ Démarrer l'application

### Étape 4 : Accéder à l'application

```
http://localhost
```

**Identifiants par défaut :**
- Utilisateur : `admin`
- Mot de passe : `admin`

### Gestion du service

```bash
# Vérifier le statut
systemctl status dotation

# Démarrer/arrêter
systemctl start dotation
systemctl stop dotation

# Voir les logs
journalctl -u dotation -f

# Redémarrer après mise à jour
systemctl restart dotation
```

### Mise à jour

Pour mettre à jour l'application vers la dernière version :

```bash
cd /opt/dotation
git pull origin main
systemctl restart dotation
```

---

## 🪟 Installation sur Windows

### Prérequis

1. **Installez Python 3.11+**
   - Téléchargez depuis https://www.python.org/downloads/
   - ⚠️ **Cochez "Add Python to PATH" lors de l'installation**
   - Vérifiez : `python --version`

2. **Installez Git**
   - Téléchargez depuis https://git-scm.com/download/win
   - Acceptez les paramètres par défaut
   - Vérifiez : `git --version`

### Étape 1 : Télécharger le script

Soit téléchargez depuis GitHub directement, soit via PowerShell :

```powershell
$url = "https://raw.githubusercontent.com/roussim974100/dotation/main/setup/install-windows.ps1"
$output = "C:\Users\$env:USERNAME\Downloads\install-windows.ps1"
(New-Object System.Net.WebClient).DownloadFile($url, $output)
```

### Étape 2 : Exécuter l'installation

1. **Ouvrez PowerShell en tant qu'administrateur**
   - Bouton Démarrer → Tapez "PowerShell"
   - Clic droit → "Exécuter en tant qu'administrateur"

2. **Exécutez le script**
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Users\$env:USERNAME\Downloads\install-windows.ps1
   ```

Le script va :
- ✅ Vérifier les prérequis (Python, Git)
- ✅ Cloner ou mettre à jour le code d'À Quai
- ✅ Créer un environnement virtuel Python
- ✅ Installer les dépendances
- ✅ Créer un script de lancement
- ✅ Créer une tâche planifiée de démarrage automatique

### Étape 3 : Lancer l'application

**Option 1 : Lancement manuel**
- Accédez à `C:\dotation`
- Double-cliquez sur `start-app.bat`
- Une fenêtre PowerShell s'ouvre
- L'application démarre sur http://localhost

**Option 2 : Démarrage automatique**
- La tâche planifiée "À Quai" a été créée
- Elle démarre automatiquement au redémarrage de Windows
- Vous pouvez la gérer dans Planificateur de tâches Windows

### Étape 4 : Accéder à l'application

```
http://localhost
```

**Identifiants par défaut :**
- Utilisateur : `admin`
- Mot de passe : `admin`

### Gestion de l'application

**Lancer manuellement :**
```
C:\dotation\start-app.bat
```

**Configurer le démarrage automatique :**
- Ouvrez "Planificateur de tâches" (Ctrl+Shift+Esc → Outils système)
- Cherchez la tâche "À Quai"
- Clic droit → Propriétés → Démarrer/Arrêter comme nécessaire

**Arrêter l'application :**
- Fermez la fenêtre PowerShell ou
- Appuyez sur Ctrl+C dans la fenêtre de l'application

---

## 🔧 Configuration initiale

Après l'installation, accédez à l'application à l'adresse http://localhost

1. **Connectez-vous** avec les identifiants par défaut
   - Utilisateur : `admin`
   - Mot de passe : `admin`

2. **Le wizard de configuration se lance automatiquement**
   - Définissez le type d'organisation
   - Renseignez le nom de votre organisation
   - Configurez les types de bénéficiaires
   - Validez la configuration

3. **Créez les premiers utilisateurs**
   - Accédez à Administration → Comptes
   - Créez des utilisateurs
   - Attribuez les groupes et permissions

---

## 🐛 Troubleshooting

### Debian / Ubuntu

**Erreur : "nginx: command not found"**
```bash
sudo apt-get update
sudo apt-get install -y nginx
```

**Erreur : "Python 3.11 n'est pas trouvé"**
```bash
sudo apt-get install -y python3.11 python3.11-venv
```

**Le service ne démarre pas**
```bash
# Vérifier les logs
journalctl -u dotation -n 50
```

### Windows

**Erreur : "Python n'est pas reconnu"**
- Installez Python depuis https://www.python.org
- ⚠️ Cochez "Add Python to PATH"
- Redémarrez PowerShell

**Erreur : "Git n'est pas reconnu"**
- Installez Git depuis https://git-scm.com
- Redémarrez PowerShell

**Erreur : "Accès refusé" ou "Permission denied"**
- Exécutez PowerShell en tant qu'administrateur
- Utilisez `powershell -ExecutionPolicy Bypass`

**L'application ne démarre pas**
- Vérifiez que le port 80 est libre
- Vérifiez les logs dans la fenêtre PowerShell

---

## 📞 Support

Si vous rencontrez des problèmes :

1. **Consultez les logs**
   - Debian : `journalctl -u dotation -f`
   - Windows : Vérifiez la fenêtre PowerShell

2. **Lisez le DEPLOYMENT_GUIDE.md**
   - Guide complet : https://github.com/roussim974100/dotation/blob/main/DEPLOYMENT_GUIDE.md

3. **Vérifiez les prérequis**
   - Utilisez les commandes de vérification ci-dessus

4. **Contactez le support**
   - Via le formulaire Contact dans l'application

---

## ✨ Après l'installation

- 📖 Consultez le **DEPLOYMENT_GUIDE.md** pour plus de détails
- 🔐 Changez les identifiants par défaut dès que possible
- 🔒 Configurez HTTPS en production (voir DEPLOYMENT_GUIDE.md)
- 💾 Configurez des backups réguliers de la base de données
- 👥 Créez les utilisateurs et les groupes nécessaires

---

**Version :** 3.18.0-dev | **Dernière MAJ :** Mai 2026
