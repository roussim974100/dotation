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
    & git checkout -B $GitBranch origin/$GitBranch
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  Impossible de checkout vers origin/$GitBranch" -ForegroundColor $Yellow
        & git checkout $GitBranch
    }
    & git pull origin $GitBranch
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
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Erreur lors de la création du venv" -ForegroundColor $Red
        exit 1
    }
}

# Vérifier que pip existe
if (-not (Test-Path "venv\Scripts\pip.exe")) {
    Write-Host "❌ pip n'a pas pu être créé dans venv" -ForegroundColor $Red
    exit 1
}

# Vérifier que requirements.txt existe
if (-not (Test-Path "backend\requirements.txt")) {
    Write-Host "❌ backend\requirements.txt n'existe pas" -ForegroundColor $Red
    exit 1
}

Write-Host "  📦 Installation des dépendances..."
& ".\venv\Scripts\pip.exe" install --upgrade pip setuptools wheel

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors de la mise à jour de pip" -ForegroundColor $Red
    exit 1
}

& ".\venv\Scripts\pip.exe" install -r backend\requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors de l'installation des dépendances" -ForegroundColor $Red
    exit 1
}

Write-Host "  ✓ Dépendances installées" -ForegroundColor $Green

# Initialiser la base de données
Write-Host ""
Write-Host "🗄️  Initialisation de la base de données..." -ForegroundColor $Yellow

& ".\venv\Scripts\python.exe" -c "from backend.app import init_db, init_users_db; init_db(); init_users_db()"

if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Erreur lors de l'initialisation de la base (elle sera créée au premier démarrage)" -ForegroundColor $Yellow
} else {
    Write-Host "  ✓ Base de données initialisée" -ForegroundColor $Green
}

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
Write-Host "✅ Installation complétée !" -ForegroundColor $Green
Write-Host "==================================================" -ForegroundColor $Green
Write-Host ""

Write-Host "🔍 Vérifications finales..." -ForegroundColor $Yellow

# Vérifier que le script de lancement existe
if (Test-Path "$InstallDir\start-app.bat") {
    Write-Host "  ✓ Script de lancement : OK" -ForegroundColor $Green
} else {
    Write-Host "  ❌ Script de lancement : MANQUANT" -ForegroundColor $Red
}

# Vérifier que les dépendances sont installées
if (Test-Path "$InstallDir\venv\Scripts\pip.exe") {
    Write-Host "  ✓ Environnement virtuel : OK" -ForegroundColor $Green
} else {
    Write-Host "  ❌ Environnement virtuel : PROBLÈME" -ForegroundColor $Red
}

# Vérifier que le répertoire data existe
if (Test-Path "$InstallDir\backend\data") {
    Write-Host "  ✓ Répertoire data : OK" -ForegroundColor $Green
} else {
    Write-Host "  ⚠️  Répertoire data : sera créé au premier démarrage" -ForegroundColor $Yellow
}

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
Write-Host "   Elle démarre automatiquement au redémarrage de Windows" -ForegroundColor $Green
Write-Host ""

Write-Host "💡 Conseil :" -ForegroundColor $Yellow
Write-Host "   Pour arrêter l'application : fermez la fenêtre ou Ctrl+C" -ForegroundColor $Green
Write-Host "   Pour voir les logs : consultez la fenêtre PowerShell" -ForegroundColor $Green
Write-Host ""

Write-Host "==================================================" -ForegroundColor $Green

Read-Host "Appuyez sur Entrée pour terminer"
