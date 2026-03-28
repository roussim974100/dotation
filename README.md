# Parcours agents et elu(e)s

Application interne de gestion des dossiers d'attribution et de restitution pour une collectivite.

## Ce que fait l'application

- creer un dossier pour un agent ou un(e) elu(e)
- enregistrer un dossier en brouillon ou en attribution partielle
- verrouiller un dossier complet une fois signe et valide RGPD
- generer un lien unique de signature a distance pour la remise
- generer un lien unique de signature a distance pour la restitution
- tracer les reouvertures de dossier encore modifiable
- suivre la restitution des ressources materielles
- administrer les comptes, les groupes, les services et les ressources attribuables
- consulter un journal des actions
- restaurer des suppressions via une corbeille reservee aux admins
- exporter les dossiers et les restitutions en PDF
- proteger les signatures dans les exports PDF selon le profil connecte
- exporter les donnees en Excel

## Types de dossier

- `arrivee` : nouvelle arrivee
- `changement_service` : mobilite interne
- `mise_a_jour` : mise a jour de ressources
- `sortie` : sortie ou restitution

## Documents du projet

- `LIVRAISON.md` : vue de remise du projet
- `GUIDE_UTILISATEUR.md` : guide d'usage rapide
- `RECETTE_FONCTIONNELLE.md` : checklist et scenarios de test
- `wikijs.md` : documentation prete a integrer dans Wiki.js
- `version/versions/` : archives documentaires par version

## Architecture

- `frontend/` : interface HTML, CSS et JavaScript servie par Flask
- `backend/` : API Flask, authentification et persistance SQLite

## Fichiers principaux

- `frontend/index.html` : tableau de bord des dossiers
- `frontend/form.html` : creation et mise a jour d'un dossier
- `frontend/restitution.html` : restitution des ressources materielles
- `frontend/signature.html` : page publique de signature via lien securise
- `frontend/admin.html` : portail administration
- `frontend/admin-comptes.html` : gestion des comptes
- `frontend/admin-services.html` : catalogue des services
- `frontend/admin-ressources.html` : catalogue des ressources
- `frontend/logs.html` : journal des actions
- `frontend/trash.html` : corbeille administrateur
- `backend/app.py` : coeur du backend Flask

## Lancement

Depuis la racine du projet :

```powershell
python backend\app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/
```

## Authentification

- la connexion est obligatoire
- un message d'erreur s'affiche si les identifiants sont incorrects
- un message specifique s'affiche si la session ne peut pas etre conservee

En environnement proxy `nginx + gunicorn`, il est recommande de definir :

- `APP_SECRET_KEY`
- `SESSION_COOKIE_SECURE=1` si le contexte HTTPS est stabilise

## Tableau de bord

Le tableau de bord permet de :

- creer un nouveau dossier
- rechercher et filtrer les dossiers
- ouvrir un dossier
- lancer une restitution
- exporter un `PDF dossier`
- exporter un `PDF restitution`
- exporter plusieurs `PDF dossier`
- exporter plusieurs `PDF restitution`
- supprimer une selection de dossiers
- exporter les donnees en Excel

Le tableau de bord se rafraichit automatiquement sans `F5` :

- toutes les 20 secondes si l'onglet est visible
- au retour de focus
- avec signal visuel des nouveaux dossiers
- avec acquittement utilisateur `J'ai vu`
- avec conservation de la selection pendant le rafraichissement

## Dossier

Un dossier peut contenir :

- les informations de la personne
- la qualite `Agent` ou `Elu(e)`
- le type de dossier
- les ressources attribuees par service
- la signature de remise
- un lien de signature a distance a usage unique pour la remise
- un lien de signature de restitution a usage unique
- la validation RGPD
- la tracabilite de reouverture

## Signature a distance

Depuis la fiche dossier, un profil autorise peut :

- generer un lien unique de signature
- copier ce lien
- revoquer le lien
- regenerer un nouveau lien

La page publique de signature permet a la personne concernee de :

- consulter l'identite et les ressources remises
- prendre connaissance du RGPD
- signer le dossier sans compte applicatif

Le lien est :

- limite a un seul dossier
- a usage unique
- expirable
- revocable

Un dossier complet passe en `Attribution active`.

Un dossier incomplet reste en `Attribution partielle` et demeure modifiable.

## Restitution

La restitution est geree sur un ecran separe.

Elle permet de :

- saisir une date de restitution
- definir rapidement l'etat de chaque materiel
- ajouter un commentaire uniquement si necessaire
- signer la restitution ou indiquer pourquoi la signature est impossible ou differee
- exporter un `PDF restitution` distinct

La restitution reste modifiable tant qu'un materiel est `Non restitue`.

## Administration

L'administration permet de :

- creer, modifier, desactiver ou supprimer un compte
- changer le mot de passe d'un compte
- creer, modifier, activer ou desactiver un service
- creer, modifier ou supprimer une ressource attribuable
- consulter le journal
- acceder a la corbeille admin

L'administration est maintenant organisee en sous-pages :

- `admin.html` pour la vue d'ensemble
- `admin-comptes.html` pour les comptes et les groupes
- `admin-services.html` pour les services
- `admin-ressources.html` pour les ressources

## Journal et corbeille

- le journal recense les actions systeme et utilisateur
- la corbeille est reservee au groupe `admin`
- un dossier, un compte ou une ressource supprime(e) peut etre restaure(e)

## Exports

### PDF dossier

Document officiel de remise avec :

- entete institutionnel
- informations de la personne
- ressources attribuees
- RGPD
- signature
- date de signature

Pour un profil non autorise a consulter les signatures, le PDF reste exportable mais la signature est masquee avec une mention reservee aux personnes autorisees.

### PDF restitution

Document distinct avec :

- informations de la personne
- date de restitution
- etat de chaque materiel
- commentaires d'anomalie
- signature de restitution ou motif d'absence

Pour un profil non autorise a consulter les signatures, la signature de restitution est masquee dans le document exporte.

### Export Excel

L'export Excel fournit un classeur lisible avec :

- une feuille `Dossiers`
- une feuille `Ressources`

## Verification technique

Controle minimal recommande apres modification :

```powershell
python -m py_compile backend\app.py
```

