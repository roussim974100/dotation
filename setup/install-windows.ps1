# Installation automatique d'À Quai sur Windows
# Usage: powershell -ExecutionPolicy Bypass -File install-windows.ps1

# Couleurs
$Green = 'Green'
$Red = 'Red'
$Yellow = 'Yellow'

Write-Host "🌊 Installation d'À Quai" -ForegroundColor $Green
Write-Host "==================================================" -ForegroundColor $Green

# Vérifier admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "❌ Ce script doit être exécuté en tant qu'administrateur" -ForegroundColor $Red
    exit 1
}

$InstallDir = "C:\dotation"
$GitRepo = "https://github.com/roussim974100/dotation.git"
$GitBranch = if ($env:GIT_BRANCH) { $env:GIT_BRANCH } else { "dev" }

# Configuration
Write-Host ""
Write-Host "📋 Vérification des prérequis..." -ForegroundColor $Yellow

# Vérifier Python 3.11
$pythonPath = where.exe python 2>$null
if (-not $pythonPath) {
    Write-Host "❌ Python 3.11 n'est pas installé" -ForegroundColor $Red
    Write-Host "   Téléchargez Python 3.11+ depuis https://www.python.org" -ForegroundColor $Yellow
    exit 1
}

$pythonVersion = & python --version 2>&1
Write-Host "  ✓ $pythonVersion" -ForegroundColor $Green

# Vérifier git
$gitPath = where.exe git 2>$null
if (-not $gitPath) {
    Write-Host "❌ Git n'est pas installé" -ForegroundColor $Red
    Write-Host "   Téléchargez Git depuis https://git-scm.com" -ForegroundColor $Yellow
    exit 1
}

Write-Host "  ✓ Git" -ForegroundColor $Green

Write-Host ""
Write-Host "📥 Préparation du répertoire d'installation..." -ForegroundColor $Yellow

# Créer/mettre à jour le répertoire
if (Test-Path $InstallDir) {
    Write-Host "  📁 Répertoire existant trouvé, mise à jour..."
    Set-Location $InstallDir
    & git fetch origin
    & git checkout -B $GitBranch "origin/$GitBranch"
} else {
    Write-Host "  📁 Création du répertoire $InstallDir..."
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Set-Location $InstallDir
    & git clone --branch $GitBranch $GitRepo .
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors du clonage du repository" -ForegroundColor $Red
    exit 1
}

Write-Host "  ✓ Code téléchargé" -ForegroundColor $Green

Write-Host ""
Write-Host "🐍 Configuration Python..." -ForegroundColor $Yellow

# Créer venv
if (-not (Test-Path "venv")) {
    Write-Host "  🔧 Création de l'environnement virtuel..."
    & python -m venv venv
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path ".\venv\Scripts\pip.exe")) {
    Write-Host "❌ Erreur lors de la création du venv ou pip absent" -ForegroundColor $Red
    exit 1
}

# Activer venv et installer dépendances
Write-Host "  🔧 Installation des dépendances..."
& ".\venv\Scripts\pip.exe" install --upgrade pip setuptools wheel
& ".\venv\Scripts\pip.exe" install -r backend\requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors de l'installation des dépendances" -ForegroundColor $Red
    exit 1
}

Write-Host "  ✓ Dépendances installées" -ForegroundColor $Green

Write-Host ""
Write-Host "🔧 Configuration du serveur..." -ForegroundColor $Yellow

# Créer répertoire data s'il n'existe pas
if (-not (Test-Path "backend\data")) {
    New-Item -ItemType Directory -Path "backend\data" -Force | Out-Null
}

# Créer un raccourci pour lancer l'app
$StartScript = @"
@echo off
cd /d "$InstallDir"
call venv\Scripts\activate.bat
set FLASK_ENV=production
python backend\app.py
pause
"@

Set-Content -Path "$InstallDir\start-app.bat" -Value $StartScript
Write-Host "  ✓ Script de lancement créé" -ForegroundColor $Green

# Créer une tâche planifiée (optionnel)
Write-Host ""
Write-Host "⚙️  Création d'une tâche planifiée (optionnel)..." -ForegroundColor $Yellow

$TaskAction = New-ScheduledTaskAction -Execute "$InstallDir\venv\Scripts\python.exe" `
    -Argument "$InstallDir\backend\app.py" `
    -WorkingDirectory $InstallDir

$TaskTrigger = New-ScheduledTaskTrigger -AtStartup

$TaskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable

$TaskName = "À Quai"
$TaskDescription = "Service de gestion des dotations matérielles"

# Vérifier si la tâche existe déjà
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName `
    -Action $TaskAction `
    -Trigger $TaskTrigger `
    -Settings $TaskSettings `
    -Description $TaskDescription `
    -RunLevel Highest -Force | Out-Null

Write-Host "  ✓ Tâche planifiée créée" -ForegroundColor $Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor $Green
Write-Host "✅ Installation complétée avec succès !" -ForegroundColor $Green
Write-Host "==================================================" -ForegroundColor $Green
Write-Host ""

Write-Host "📍 Accès à l'application :" -ForegroundColor $Yellow
Write-Host "   http://localhost" -ForegroundColor $Green
Write-Host ""

Write-Host "🔐 Identifiants par défaut :" -ForegroundColor $Yellow
Write-Host "   Utilisateur : admin" -ForegroundColor $Green
Write-Host "   Mot de passe : admin" -ForegroundColor $Green
Write-Host ""

Write-Host "📖 Première utilisation :" -ForegroundColor $Yellow
Write-Host "   1. Lancez l'application (double-cliquez start-app.bat)" -ForegroundColor $Green
Write-Host "   2. Accédez à http://localhost/login" -ForegroundColor $Green
Write-Host "   3. Connectez-vous avec admin/admin" -ForegroundColor $Green
Write-Host "   4. Suivez le wizard de configuration" -ForegroundColor $Green
Write-Host ""

Write-Host "🚀 Lancer l'application :" -ForegroundColor $Yellow
Write-Host "   Double-cliquez sur : $InstallDir\start-app.bat" -ForegroundColor $Green
Write-Host ""

Write-Host "🔄 Démarrage automatique :" -ForegroundColor $Yellow
Write-Host "   La tâche planifiée 'À Quai' a été créée" -ForegroundColor $Green
Write-Host "   Elle démarre automatiquement au redémarrage" -ForegroundColor $Green
Write-Host ""

Write-Host "==================================================" -ForegroundColor $Green

Read-Host "Appuyez sur Entrée pour terminer"
