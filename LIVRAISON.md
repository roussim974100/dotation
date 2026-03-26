# Projet Pret a Remise

Ce document sert de point d'entree pour la remise du projet.

## Contenu livre

- application web interne de gestion des dossiers d'attribution
- backend Flask avec stockage SQLite
- gestion des utilisateurs et des groupes
- workflow d'attribution, signature de remise, RGPD et restitution
- gestion des ressources attribuables
- journal applicatif dedie
- corbeille administrateur avec restauration
- export `PDF dossier` unitaire et multiple
- export `PDF restitution` unitaire et multiple
- masquage des signatures dans les PDF pour les profils non autorises
- export Excel lisible en deux feuilles
- tracabilite de la reouverture des dossiers modifiables

## Documents a consulter

- [README.md](C:/www/dotation/README.md)
- [GUIDE_UTILISATEUR.md](C:/www/dotation/GUIDE_UTILISATEUR.md)
- [RECETTE_FONCTIONNELLE.md](C:/www/dotation/RECETTE_FONCTIONNELLE.md)
- [wikijs.md](C:/www/dotation/wikijs.md)

## Lancement

Depuis la racine du projet :

```powershell
python backend\app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/
```

## Compte d'administration initial

- identifiant : `admin`
- mot de passe : a modifier apres installation

## Recommendation avant remise

- verifier la recette fonctionnelle complete
- definir une vraie valeur `APP_SECRET_KEY`
- stabiliser la configuration `nginx + gunicorn` si necessaire
- changer le mot de passe du compte administrateur initial
