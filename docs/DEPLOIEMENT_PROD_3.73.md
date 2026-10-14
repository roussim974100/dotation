# Mise en production de la 3.73.0 — mode d'emploi pas à pas

Pour passer la **production (3.67.1)** à la **3.73.0**. Durée prévue : 15 à 30 minutes, en heure creuse. Le script `deploy.sh` fait lui-même la
sauvegarde, la mise à jour, les dépendances, le redémarrage et le **retour arrière automatique** en cas d'échec : ce document dit quoi vérifier
**avant**, quoi regarder **pendant**, quoi contrôler **après**, et quoi faire si ça tourne mal.

## Ce qui change pour la production (à connaître)

| Changement | Conséquence |
|---|---|
| **Sessions** (3.67.3) | Tout le monde doit **se reconnecter une fois** (les anciens cookies sont refusés). Ensuite : session de 12 h au maximum, fermée après 60 min d'inactivité. |
| **Mot de passe d'origine** | Si le compte `admin` a encore le mot de passe `admin`, il est **obligé de le changer** à la première connexion. |
| **Migrations 9 et 10** (titulaires et tâches de service) | S'appliquent **toutes seules au démarrage**, avec copie de sécurité préalable (`db_backups/`). L'historique est marqué « déjà fait » : aucune tâche n'est créée sur les anciens dossiers. |
| **Nouvelle dépendance** `tzdata` | Le script exécute `pip install -r backend/requirements.txt` : le serveur doit atteindre un dépôt Python (Internet ou miroir interne). |
| **Notifications** | Tant que les ressources ne sont pas rattachées à un service avec des titulaires, **toutes les tâches vont aux administrateurs**. |
| **Blocage d'adresse** | 10 mauvais mots de passe depuis une même adresse la bloquent 15 minutes (le compte, lui, n'est jamais bloqué). Derrière le proxy, vérifier que l'adresse des postes est bien transmise (README, « Adresse IP des clients »). |
| **Plus aucun CDN** | Bootstrap, Chart.js, la fenêtre des cookies sont servis par l'application : aucun accès Internet nécessaire pour l'affichage. |
| **Fuseau horaire** | Réglage « Fuseau horaire » (Administration > Personnalisation), Europe/Paris par défaut ; le fuseau est écrit à côté des heures de signature des PDF. |

Pas de nouvelle variable d'environnement obligatoire (toutes ont une valeur par défaut, voir README).

## 1. Avant (la veille ou le matin)

- [ ] **La préprod est testée** (checklist « À tester en préprod » de `docs/BACKLOG_PRODUIT.md`) et la PR `preprod` → `prod` est **fusionnée par vous**.
- [ ] **Prévenir les utilisateurs** : une coupure de quelques minutes, puis une reconnexion à faire.
- [ ] **Choisir le créneau** : peu d'activité, personne en train de signer.
- [ ] **Sauvegarde manuelle de précaution**, en plus de celle du script : Administration > Base de données > export, ou copie de `backend/dotation.db` et `backend/users.db` (ou du dossier `APP_DATA_DIR`) vers un autre disque. **La garder hors du dépôt git.**
- [ ] **Espace disque** : `df -h` (la sauvegarde du script copie les bases ; quelques dizaines de Mo suffisent).
- [ ] **Accès au dépôt Python** : `pip download tzdata==2026.4 -d /tmp/t` depuis le serveur doit fonctionner (sinon voir « Problèmes connus »).
- [ ] **Noter l'état actuel** : version affichée en pied de page (3.67.1) et `git -C <dossier> rev-parse --short HEAD`.

## 2. Pendant

Se connecter au serveur de production, aller dans le dossier de l'application, puis :

```bash
cd /opt/dotation            # le dossier où se trouve deploy.sh (celui de votre installation)
sudo bash deploy.sh
```

Le script, dans l'ordre : sauvegarde cohérente des bases (`db_backups/avant_maj_<date>/`) → récupère `origin/prod` → installe les dépendances dans le
venv **lu dans le fichier systemd du service** → redémarre → **vérifie que l'application répond**. En cas d'échec, il revient tout seul à
l'ancienne version et le dit. À lire dans sa sortie :

- `Déploiement de la branche prod (version actuelle : 3.67.1 …)` au début, et **`3.73.0`** à la fin ;
- aucune ligne rouge.

Si le script refuse à cause de « modifications locales » : ne pas forcer sans regarder (`git -C <dossier> status`). `--force` écrase les modifications
de fichiers suivis par git.

## 3. Après (10 à 15 minutes de contrôles)

1. **Pied de page** : `3.73.0` (pastille « prod »).
2. **Connexion** avec un compte administrateur ; si `admin` avait encore `admin`, le changement de mot de passe est demandé : le faire.
3. **Administration > Base de données > Contrôle général de la base** : aucun problème signalé.
4. **Les dossiers sont intacts** : les quatre tableaux de bord affichent les mêmes effectifs qu'avant ; ouvrir un dossier signé.
5. **PDF** : télécharger le PDF d'un dossier signé : l'heure de signature porte « (heure de Paris, UTC+x) ».
6. **Administration > Personnalisation** : vérifier le fuseau horaire (Europe/Paris), enregistrer.
7. **Administration > Services** : rattacher les ressources aux services et **saisir les titulaires** de chaque service ; la cloche et « Mes tâches » se remplissent ensuite.
8. **Bouton « Cookies »** du pied de page : la fenêtre s'ouvre (si rien ne se passe sur un poste, tester en navigation privée : une extension peut la masquer).
9. **Journal** : `journalctl -u dotation -n 100 --no-pager` ne montre aucune erreur ; `<dossier de données>/logs/aquai.log` non plus.
10. **Paquet de diagnostic** (Administration > Base de données) : le générer et le garder en cas de besoin.

## 4. Si quelque chose ne va pas

- **Le script a échoué** : il a déjà rétabli l'ancienne version (sinon il l'écrit et donne la sauvegarde). Relever le code d'erreur affiché (`E-XXXXXX`) et la sortie du script.
- **Retour arrière manuel** (après coup) : `systemctl stop dotation`, restaurer les deux bases depuis `db_backups/avant_maj_<date>/` (supprimer les fichiers `*.db-wal` et `*.db-shm`), `git checkout` de l'ancien commit noté plus haut, `systemctl start dotation`. **Les saisies faites depuis le déploiement sont perdues** : ne le décider qu'en dernier recours.
- **502 Bad Gateway** : `journalctl -u dotation -n 100` ; presque toujours un module Python manquant (le venv utilisé n'est pas celui où `pip install` a été lancé : lire `ExecStart` dans `/etc/systemd/system/dotation.service`).
- **Les gens sont déconnectés en boucle** : l'horloge du serveur est-elle à l'heure ? Vider les cookies du site sur le poste.
- **« Trop de tentatives de connexion… 15 minutes »** pour tout un service : les postes arrivent avec la même adresse (proxy qui ne transmet pas l'adresse réelle). Voir README, « Adresse IP des clients » ; en attendant, `APP_LOGIN_IP_MAX_FAILURES=0` désactive ce blocage.
- **Pas d'accès Internet pour `pip`** : déposer le fichier `tzdata-2026.4-py2.py3-none-any.whl` sur le serveur et l'installer dans le venv du service (`<venv>/bin/pip install ./tzdata-…whl`), puis relancer `deploy.sh`.

## 5. Après quelques jours de recul

- [ ] Fusionner `preprod` → `main` (c'est seulement l'affichage du README sur GitHub ; **pas avant** la mise en production).
- [ ] Mettre à jour `docs/BACKLOG_PRODUIT.md` (état des branches) et dire à l'assistant que la production est en 3.73.0.
- [ ] Supprimer les anciennes sauvegardes `avant_maj_*` devenues inutiles (garder la dernière).
