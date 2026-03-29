# Recette Fonctionnelle

Version de reference : `2.10.0`

## Preparation

1. Lancer l'application :

```powershell
python backend\app.py
```

2. Ouvrir `http://127.0.0.1:5000/`
3. Se connecter avec un compte administrateur

## Checklist rapide

- la page de connexion s'affiche correctement
- un message d'erreur apparait si les identifiants sont incorrects
- le tableau de bord se charge
- un nouveau dossier peut etre cree
- un dossier brouillon peut etre enregistre et rouvert
- la reouverture du dossier est tracee dans la fiche
- un dossier signe complet passe en `Attribution active`
- un dossier `Attribution partielle` reste modifiable
- un lien de signature de remise peut etre genere depuis un dossier
- un lien de signature de restitution peut etre genere depuis une restitution preparee
- la restitution fonctionne depuis un dossier actif
- le `PDF dossier` unitaire fonctionne
- le `PDF restitution` unitaire fonctionne
- les signatures sont masquees dans les PDF exportes par un profil `lecture`
- l'export multiple des `PDF dossier` fonctionne
- l'export multiple des `PDF restitution` fonctionne
- la fenetre de chargement d'export s'affiche pendant les lots
- l'export Excel fonctionne
- l'administration des utilisateurs est accessible
- l'administration des services est accessible
- l'administration des ressources est accessible
- une ressource personnalisee peut etre creee avec ses champs obligatoires
- la page d'ordre des ressources est accessible et l'enregistrement du glisser-deposer fonctionne
- la page `Journal` est accessible
- la page `Corbeille` est accessible pour un admin
- le dossier `version/versions/` est present
- la deconnexion fonctionne

## Scenarios de test

### 1. Creation d'un brouillon

1. Cliquer sur `Nouveau dossier`
2. Renseigner seulement le minimum
3. Cliquer sur `Enregistrer`

Attendu :

- le dossier est cree
- il reste modifiable
- il apparait dans le tableau de bord

### 2. Attribution complete

1. Ouvrir un nouveau dossier
2. Renseigner les ressources
3. Saisir la signature
4. Cocher le RGPD
5. Enregistrer

Attendu :

- le dossier passe en `Attribution active`
- il n'est plus editable en mode standard
- le `PDF dossier` est disponible

### 3. Reouverture tracee

1. Ouvrir un dossier encore modifiable
2. Revenir au tableau de bord
3. Rouvrir le meme dossier

Attendu :

- le bloc de reouverture apparait
- le compteur augmente
- la date et l'utilisateur sont affiches

### 4. Restitution

1. Ouvrir un dossier actif
2. Cliquer sur `Restitution`
3. Choisir l'etat de chaque materiel
4. Ajouter un commentaire si necessaire
5. Saisir une signature ou un motif d'absence
6. Enregistrer

Attendu :

- la restitution est enregistree
- le `PDF restitution` est disponible
- le resume apparait dans le dossier

### 4 bis. Signature a distance

1. Ouvrir un dossier modifiable
2. Generer un lien de signature
3. Ouvrir le lien dans un navigateur prive
4. Valider le RGPD
5. Signer
6. Valider

Attendu :

- la page publique s'affiche sans connexion
- les ressources du dossier sont visibles en lecture seule
- la signature est enregistree
- le lien passe a l'etat `utilise`
- la fiche est mise a jour au retour dans l'application

### 5. Export multiple PDF dossier

1. Cocher plusieurs dossiers
2. Cliquer sur `PDF dossiers selectionnes`

Attendu :

- une fenetre de chargement apparait
- un ZIP est propose au telechargement

### 5 bis. Export PDF avec profil lecture

1. Se connecter avec un compte du groupe `lecture`
2. Exporter un `PDF dossier`
3. Exporter un `PDF restitution`

Attendu :

- les PDF sont accessibles
- l'identite reste visible
- la signature image n'apparait pas
- une mention indique que la signature est reservee aux personnes autorisees

### 6. Export multiple PDF restitution

1. Cocher plusieurs dossiers avec restitution
2. Cliquer sur `PDF restitutions selectionnees`

Attendu :

- une fenetre de chargement apparait
- un ZIP est propose au telechargement

### 7. Journal

1. Ouvrir la page `Journal`
2. Rechercher un mot-cle

Attendu :

- les actions correspondantes sont affichees

### 8. Corbeille

1. Supprimer un element de test
2. Ouvrir la `Corbeille`
3. Restaurer l'element

Attendu :

- l'element reapparait dans l'application

### 9. Smartphone

1. Ouvrir l'application sur smartphone
2. Se connecter
3. Ouvrir le tableau de bord
4. Ouvrir un dossier long
5. Tester le bouton `Haut`

Attendu :

- la connexion fonctionne
- le header reste lisible
- pas de scroll lateral parasite
- le bouton `Haut` reste utilisable

