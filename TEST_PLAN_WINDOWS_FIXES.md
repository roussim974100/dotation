# 📋 Plan de test - Script installation Windows amélioré

**Version:** v3.18.0 (branche main)  
**Commit:** e2c4061 - `fix: améliorer install-windows.ps1 avec vérifications robustes`  
**Date:** 2026-05-05

---

## 🎯 Objectif

Tester l'installation améliorée sur Windows pour valider la robustesse du script et les vérifications ajoutées.

### Améliorations apportées
- ✅ Vérification que pip existe
- ✅ Vérification que requirements.txt existe
- ✅ Gestion d'erreurs lors de création venv
- ✅ Vérifications finales de statut
- ✅ Meilleure documentation pour démarrage automatique

---

## 🔧 Prérequis

### Sur la machine Windows
- **Python 3.11+** installé et ajouté au PATH
  ```powershell
  python --version
  ```
- **Git** installé et ajouté au PATH
  ```powershell
  git --version
  ```
- **PowerShell 5.0+** (inclus dans Windows 10+)
- **Droits administrateur** pour exécuter le script

---

## 📋 Étapes de test

### Phase 1 : Préparation (5 min)

#### 1.1 - Nettoyer l'installation précédente (si existe)
```powershell
# Arrêter la tâche planifiée si existe
Get-ScheduledTask -TaskName "À Quai" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false

# Supprimer le répertoire (optionnel)
Remove-Item -Path "C:\dotation" -Recurse -Force -ErrorAction SilentlyContinue
```

#### 1.2 - Télécharger le script amélioré
```powershell
# Option 1 : Via Git
cd C:\Users\$env:USERNAME\Downloads
git clone --branch main https://github.com/roussim974100/dotation.git dotation-test
cd dotation-test

# Option 2 : Télécharger juste le script
$url = "https://raw.githubusercontent.com/roussim974100/dotation/main/setup/install-windows.ps1"
$output = "C:\Users\$env:USERNAME\Downloads\install-windows.ps1"
(New-Object System.Net.WebClient).DownloadFile($url, $output)
```

### Phase 2 : Exécution installation (15-20 min)

#### 2.1 - Ouvrir PowerShell en tant qu'administrateur
1. Clic droit sur PowerShell → "Exécuter en tant qu'administrateur"

#### 2.2 - Exécuter le script
```powershell
# Enregistrer la transcription des logs
$transcript = "C:\Users\$env:USERNAME\Downloads\install-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
Start-Transcript -Path $transcript

# Exécuter le script
powershell -ExecutionPolicy Bypass -File "C:\Users\$env:USERNAME\Downloads\install-windows.ps1"

# Arrêter la transcription
Stop-Transcript
```

#### 2.3 - Observer les étapes
- ✅ Vérification des prérequis (Python, Git)
- ✅ Clonage du code
- ✅ Création venv avec messages
- ✅ Installation dépendances
- ✅ Création script de lancement
- ✅ Création tâche planifiée
- ✅ Vérifications finales

---

## 🔍 Vérifications après installation

### 3.1 - Vérifier le répertoire d'installation
```powershell
# Doit exister et contenir les fichiers
ls C:\dotation\

# Doit avoir ces répertoires clés
Test-Path "C:\dotation\venv"        # Environnement virtuel
Test-Path "C:\dotation\backend"     # Code backend
Test-Path "C:\dotation\start-app.bat"  # Script de lancement
```

### 3.2 - Vérifier Python et pip
```powershell
# Vérifier pip
C:\dotation\venv\Scripts\pip.exe --version

# Vérifier dépendances installées
C:\dotation\venv\Scripts\pip.exe list | findstr flask
```

### 3.3 - Vérifier la tâche planifiée
```powershell
# Doit exister et être créée
Get-ScheduledTask -TaskName "À Quai"

# Voir ses détails
Get-ScheduledTask -TaskName "À Quai" | Get-ScheduledTaskInfo
```

### 3.4 - Vérifier le répertoire data
```powershell
# Doit exister ou sera créé au premier démarrage
Test-Path "C:\dotation\backend\data"
```

---

## 🌐 Tests via navigateur (20 min)

### Phase 1 : Lancement manuel

#### 1.1 - Lancer l'application
```powershell
# Via PowerShell (en admin)
C:\dotation\start-app.bat

# OU via l'Explorateur Windows
# Double-cliquer sur : C:\dotation\start-app.bat
```

#### 1.2 - Observer le démarrage
- Une fenêtre PowerShell doit s'ouvrir
- Doit voir les logs Flask
- Doit voir "Running on http://127.0.0.1:5000/"

#### 1.3 - Accéder à l'application
1. Ouvrir navigateur → `http://localhost`
2. ✅ **Vérifier** : Redirection vers `/login`
3. ✅ **Vérifier** : Page login affichée

### Phase 2 : Connexion admin
1. Utilisateur : `admin`
2. Mot de passe : `admin`
3. ✅ **Vérifier** : Connexion réussie
4. ✅ **Vérifier** : Redirection vers wizard ou dashboard

### Phase 3 : Wizard de configuration
**Étape 1 - Type d'organisation**
- ✅ Sélectionner : "Collectivité"
- ✅ Cliquer "Suivant"

**Étape 2 - Nom organisation**
- ✅ Entrer : "Test Windows"
- ✅ Cliquer "Suivant"

**Étape 3 - Types de bénéficiaires**
- ✅ Ajouter : "Enfant"
- ✅ Cliquer "Suivant"

**Étape 4 - Équipements**
- ✅ Ajouter : "Fournitures scolaires"
- ✅ Cliquer "Suivant"

**Étape 5 - Résumé**
- ✅ Vérifier les données
- ✅ Cliquer "Valider"

### Phase 4 : Vérifications dans l'app
1. Aller à : Administration → Comptes
2. ✅ Voir les groupes par défaut
3. ✅ Créer nouvel utilisateur
4. Aller à : Dossiers
5. ✅ Créer un dossier test

### Phase 5 : Vérifier les logs de l'application
- Fenêtre PowerShell doit afficher les requêtes HTTP
- ✅ Pas d'erreur Python
- ✅ Status codes 200/302 (pas 500)

---

## 🔄 Tests de démarrage automatique

### Phase 1 : Vérifier la tâche planifiée
```powershell
# Voir le statut
Get-ScheduledTask -TaskName "À Quai" | Select-Object -Property Name, State, LastRunTime, NextRunTime
```

### Phase 2 : Tester le démarrage manuel
```powershell
# Déclencher la tâche manuellement
Get-ScheduledTask -TaskName "À Quai" | Start-ScheduledTask

# Attendre 5 secondes
Start-Sleep -Seconds 5

# Vérifier que l'app répond
curl http://localhost/

# Arrêter la tâche
Get-ScheduledTask -TaskName "À Quai" | Stop-ScheduledTask
```

### Phase 3 : Redémarrage du système (optionnel)
1. Redémarrer Windows
2. Attendre 30 secondes
3. Ouvrir navigateur → `http://localhost`
4. ✅ **Vérifier** : Application accessible automatiquement

---

## 📊 Critères de succès

### ✅ SUCCÈS : Tous ces points valident
1. ✓ Script complété sans erreur
2. ✓ venv créé avec pip fonctionnel
3. ✓ requirements.txt trouvé et installé
4. ✓ Script start-app.bat créé
5. ✓ Tâche planifiée créée
6. ✓ Vérifications finales : OK
7. ✓ Application démarre manuellement
8. ✓ Login admin/admin réussit
9. ✓ Wizard configuration complété
10. ✓ Pas d'erreur dans logs

### ⚠️ AVERTISSEMENTS
- Port 80 occupé sur Windows ? → Modifier le port dans backend/app.py
- Python PATH invalide ? → Réinstaller Python avec "Add to PATH"
- Git PATH invalide ? → Réinstaller Git

### ❌ ÉCHEC : À noter
- Message exact de l'erreur
- Logs complets (sauvegardés par Start-Transcript)
- État du venv
- État de la tâche planifiée

---

## 📝 Rapport de test

### À documenter
```
Environnement:
- OS: Windows version (ex: 11 Pro 22H2)
- Python: __version__
- Git: __version__
- PowerShell: __version__

Résultats installation:
- Durée: __ minutes
- Erreurs: Y/N → détails
- Script batch créé: Y/N
- Tâche planifiée créée: Y/N

Tests navigateur:
- Login: ✓/❌
- Wizard: ✓/❌
- Utilisateur: ✓/❌
- Dossier: ✓/❌

Démarrage automatique:
- Tâche s'exécute: Y/N
- Port répond: Y/N

Logs:
[Attacher transcript complet]
[Attacher logs PowerShell si erreurs]

Conclusion:
✅ SUCCÈS - Application fonctionnelle
ou
❌ ÉCHEC - [Détails des problèmes]
```

---

## 🚀 Prochaines étapes après test réussi

1. ✅ Valider les deux scripts (Debian + Windows)
2. ✅ Fusionner branche dev vers main
3. ✅ Fusionner main vers prod
4. ✅ Mettre à jour la documentation
5. ✅ Notifier les utilisateurs

