# 📋 Plan de test - Script installation Debian corrigé

**Version:** v3.18.0 (branche main)  
**Commit:** 88d709e - `fix: corriger install-debian.sh selon rapport de test`  
**Date:** 2026-05-05

---

## 🎯 Objectif

Re-tester l'installation sur LXC 504 (ou LXC 503 nettoyé) pour valider que **tous les problèmes du premier test sont résolus**.

### Problèmes du premier test (LXC 503)
- ❌ Erreur création venv Python ("ensurep ip not available")
- ❌ Service systemd non créé
- ❌ Base de données non initialisée  
- ❌ Configuration nginx incomplète
- ❌ Application non accessible

---

## 🔧 Corrections apportées

| # | Problème | Solution | Ligne(s) |
|----|----------|----------|----------|
| 1 | Python 3.11 échoue | Fallback 3.10 → 3 | 39-42, 97-106 |
| 2 | Création venv silencieuse | Tests conditionnels + exit 1 | 97-110 |
| 3 | pip manquant | Vérification explicite pip | 110-113 |
| 4 | requirements.txt manquant | Vérification avant install | 122-130 |
| 5 | DB non initialisée | Lancer app.py au démarrage | 197-207 |
| 6 | Systemd non créé | Vérification fichier + daemon-reload | 234-248 |
| 7 | Pas de logs | StandardOutput/StandardError=journal | 227-228 |
| 8 | App non démarre | systemctl start + vérifications | 250-262 |

---

## 📋 Étapes de test

### Phase 1 : Préparation (5 min)

```bash
# 1.1 - Sur la machine Host (Proxmox)
# Créer LXC 504 (ou nettoyer 503)
# Specs: 8 cores, 2048 MB RAM, vmbr1, Debian 12
# Récupérer IP DHCP assignée

# 1.2 - Cloner le code avec les corrections
cd /root
git clone --branch main https://github.com/roussim974100/dotation.git dotation-test
cd dotation-test
```

### Phase 2 : Exécution installation (15-20 min)

```bash
# 2.1 - Lancer l'installation avec logs
sudo bash setup/install-debian.sh 2>&1 | tee install-$(date +%Y%m%d-%H%M%S).log

# 2.2 - Garder la fenêtre ouverte pour voir tous les messages
# (Ne pas fermer avant la fin)
```

### Phase 3 : Vérifications immédiatement après (10 min)

#### ✅ 3.1 - Vérifier Python
```bash
# Doit afficher Python 3.11 ou 3.10
python3 --version

# Vérifier venv
test -f /opt/dotation/venv/bin/pip && echo "✓ pip existe" || echo "❌ pip absent"
```

#### ✅ 3.2 - Vérifier service systemd
```bash
# Doit montrer Created
systemctl status dotation

# Doit montrer active (running)
systemctl is-active dotation

# Voir les logs
journalctl -u dotation -n 30
```

#### ✅ 3.3 - Vérifier base de données
```bash
# Doit exister et être accessible
ls -lah /opt/dotation/backend/data/
sqlite3 /opt/dotation/backend/data/app.db "SELECT count(*) FROM sqlite_master;"
```

#### ✅ 3.4 - Vérifier nginx
```bash
# Doit montrer running
systemctl status nginx

# Tester depuis LXC
curl -s http://localhost/ | head -20
```

#### ✅ 3.5 - Vérifier les ports
```bash
# Port 5000 (Flask)
netstat -tlnp | grep 5000

# Port 80 (Nginx)
netstat -tlnp | grep 80
```

---

## 🌐 Tests via navigateur (depuis LinuxMint - 15 min)

### Étape 1 : Accès initial
1. Ouvrir navigateur → `http://<IP_LXC_504>`
2. ✅ **Vérifier** : Redirection vers `/login`
3. ✅ **Vérifier** : Page login affichée correctement

### Étape 2 : Connexion admin
1. Utilisateur : `admin`
2. Mot de passe : `admin`
3. ✅ **Vérifier** : Connexion réussie
4. ✅ **Vérifier** : Redirection vers wizard de configuration

### Étape 3 : Wizard de configuration (5 étapes)
**Étape 1 - Type d'organisation**
- ✅ Sélectionner : "Collectivité"
- ✅ Cliquer "Suivant"

**Étape 2 - Nom organisation**
- ✅ Entrer : "Test LXC 504"
- ✅ Cliquer "Suivant"

**Étape 3 - Types de bénéficiaires**
- ✅ Ajouter au moins 1 type
- ✅ Cliquer "Suivant"

**Étape 4 - Équipements**
- ✅ Ajouter au moins 1 catégorie
- ✅ Cliquer "Suivant"

**Étape 5 - Résumé**
- ✅ Vérifier les données
- ✅ Cliquer "Valider"

### Étape 4 : Créer un utilisateur
1. Aller à : Administration → Comptes
2. ✅ Créer nouvel utilisateur
   - Nom : "User Test"
   - Email : "test@localhost"
   - Mot de passe : "Test123!"
3. ✅ Assigner un groupe
4. ✅ Sauvegarder

### Étape 5 : Créer un dossier test
1. Aller à : Dossiers
2. ✅ Créer nouveau dossier
   - Nom : "Test Dossier"
   - Bénéficiaire : sélectionner
3. ✅ Ajouter équipement
4. ✅ Sauvegarder

### Étape 6 : Vérifier logs côté serveur
```bash
# Depuis LXC 504 - voir les logs Flask
journalctl -u dotation -f
# (Doit montrer les requêtes HTTP 200, pas d'erreur Python)
```

---

## 📊 Critères de succès

### ✅ SUCCÈS : Tous ces points valident
1. ✓ Script complété sans erreur
2. ✓ Service systemd actif (systemctl status)
3. ✓ Port 5000 écoute (netstat)
4. ✓ Port 80 accessible (curl)
5. ✓ Base de données initialisée (sqlite3)
6. ✓ Login admin/admin réussit
7. ✓ Wizard configuration complété
8. ✓ Utilisateur créé
9. ✓ Dossier créé
10. ✓ Pas d'erreur Python dans logs (journalctl)

### ❌ ÉCHEC : Notez les détails
- Ligne/message exact de l'erreur
- État du service (systemctl status)
- Logs Flask (journalctl -u dotation -n 100)
- État des ports (netstat)

---

## 📝 Rapport de test

### À documenter
```
Environnement:
- LXC: 503 ou 504?
- OS: Debian version?
- Branche: dev
- Commit: 88d709e

Résultats installation:
- Durée: __ minutes
- Erreurs: Y/N → détails
- Services actifs: Y/N
- Ports en écoute: Y/N

Tests navigateur:
- Login: ✓/❌
- Wizard: ✓/❌
- Utilisateur: ✓/❌
- Dossier: ✓/❌

Logs:
[Attacher install.log complet]
[Attacher journalctl si erreurs]

Conclusion:
✅ SUCCÈS - Application fonctionnelle
ou
❌ ÉCHEC - [Détails des problèmes]
```

---

## 🔍 Troubleshooting rapide

| Symptôme | Diagnostic |
|----------|-----------|
| Erreur "pip not found" | `journalctl -u dotation -n 50` |
| Service ne démarre pas | `systemctl start dotation` + logs |
| Port 5000 ne répond pas | Vérifier: `curl http://localhost:5000` |
| DB vide ou errors | `sqlite3 /opt/dotation/backend/data/app.db ".schema"` |
| Nginx 502 Bad Gateway | `journalctl -u dotation -f` lors requête |

---

## 📞 Prochaines actions

1. **Vert complet** → Fusionner dev → main → prod
2. **Problèmes** → Identifier + corriger + nouveau commit
3. **Problèmes récurrents** → Documenter dans DEPLOYMENT_GUIDE.md

