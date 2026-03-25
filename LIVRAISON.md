# Projet Prêt à Remise

Ce document sert de point d'entrée pour la remise du projet.

## Contenu livré

- application web interne de gestion des dossiers d'attribution
- backend Flask avec stockage SQLite
- gestion des utilisateurs et des groupes
- workflow d'attribution, signature de remise, RGPD et restitution
- gestion des ressources attribuables
- journal applicatif dédié
- corbeille administrateur avec restauration
- export PDF unitaire et multiple
- export CSV compatible Excel

## Documents à consulter

- [README.md](C:/www/dotation/README.md)
- [GUIDE_UTILISATEUR.md](C:/www/dotation/GUIDE_UTILISATEUR.md)
- [RECETTE_FONCTIONNELLE.md](C:/www/dotation/RECETTE_FONCTIONNELLE.md)

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
- mot de passe : `admin123!`

## Points couverts par la livraison

- connexion utilisateur
- tableau de bord des dossiers
- création et modification d'un dossier
- séparation agent / élu(e)
- services prédéfinis
- signature de la fiche
- validation RGPD
- verrouillage d'un dossier signé complet
- restitution détaillée
- administration des utilisateurs
- gestion des ressources attribuables
- journal des actions
- export PDF
- export CSV

## Recommandation avant diffusion interne

Faire une recette complète avec [RECETTE_FONCTIONNELLE.md](C:/www/dotation/RECETTE_FONCTIONNELLE.md), puis modifier le mot de passe administrateur initial.
