# Recette Fonctionnelle

## Préparation

1. Lancer l'application :

```powershell
python backend\app.py
```

2. Ouvrir `http://127.0.0.1:5000/`
3. Se connecter avec un compte administrateur

## Checklist rapide

- la page de connexion s'affiche correctement
- l'authentification fonctionne
- le tableau de bord se charge
- un nouveau dossier peut être créé
- un dossier brouillon peut être enregistré et rouvert
- un dossier signé complet passe en `Attribution active`
- un dossier `Attribution active` n'est plus modifiable
- un dossier `Attribution partielle` reste modifiable
- la restitution fonctionne depuis un dossier actif
- l'export PDF unitaire fonctionne
- l'export PDF multiple fonctionne
- l'export CSV fonctionne
- l'administration des utilisateurs est accessible
- l'administration des ressources est accessible
- la page `Journal` est accessible
- la page `Corbeille` est accessible pour un admin
- la déconnexion fonctionne

## Scénarios de test

### 1. Création d'un brouillon

1. Créer un dossier sans signature
2. Ne pas cocher le RGPD
3. Enregistrer

Résultat attendu :

- le dossier est en `Brouillon`
- il apparaît dans les dossiers modifiables
- il peut être rouvert

### 2. Attribution partielle

1. Ouvrir un dossier
2. Saisir une signature
3. Cocher le RGPD
4. Choisir `attribution partielle`

Résultat attendu :

- le dossier passe en `Attribution partielle`
- il reste modifiable

### 3. Attribution active verrouillée

1. Ouvrir un dossier
2. Saisir une signature
3. Cocher le RGPD
4. Choisir `attribution complète`

Résultat attendu :

- le dossier passe en `Attribution active`
- le dossier devient verrouillé
- le bouton `Restitution` apparaît depuis l'accueil

### 4. Restitution

1. Depuis l'accueil, ouvrir la restitution d'un dossier actif
2. Saisir une date
3. Définir l'état de plusieurs éléments
4. Enregistrer

Résultat attendu :

- le dossier reflète la restitution
- les informations sont conservées à la réouverture

### 5. Administration des utilisateurs

1. Ouvrir `Administration`
2. Créer un utilisateur
3. Modifier ses groupes
4. Changer son mot de passe
5. Désactiver puis réactiver le compte

Résultat attendu :

- les droits correspondent au groupe choisi
- le mot de passe est bien pris en compte
- l'état du compte change correctement

### 6. Administration des ressources

1. Ouvrir `Administration`
2. Ajouter une ressource attribuable
3. Modifier cette ressource
4. Ouvrir un dossier
5. Vérifier que la ressource est disponible dans le formulaire

Résultat attendu :

- la ressource est visible dans le référentiel
- la modification est prise en compte
- elle peut être attribuée dans un dossier

### 7. Journal applicatif

1. Ouvrir `Journal`
2. Rechercher un identifiant utilisateur ou une ressource
3. Vérifier la présence des actions récentes

Résultat attendu :

- les entrées sont visibles
- la recherche filtre correctement
- les actions d'administration et de dossier remontent bien

### 8. Corbeille administrateur

1. Supprimer un dossier, une ressource ou un utilisateur de test
2. Ouvrir `Corbeille`
3. Restaurer l'élément

Résultat attendu :

- l'élément supprimé apparaît dans la corbeille
- la restauration fonctionne
- l'élément redevient disponible dans l'application

## Vérifications complémentaires recommandées

- test sur écran bureau
- test sur tablette
- test sur smartphone
- test d'impression PDF
- test de réouverture après redémarrage du serveur
- sauvegarde CSV puis contrôle dans Excel

## Validation de remise

Le projet peut être considéré prêt à remise si :

- tous les scénarios ci-dessus sont validés
- le compte administrateur initial est sécurisé
- les services, ressources et droits sont conformes au besoin
