# Parcours agents et elu(e)s

Version documentaire : `2.7.1`

## Type d'archive

- statut : `archive reconstituee`
- source : `reconstitution documentaire a partir de l'etat fonctionnel connu`

## Perimetre

Cette version couvre principalement :

- la gestion des dossiers d'attribution
- la restitution des ressources materielles
- les exports `PDF dossier` et `PDF restitution`
- la protection des signatures dans les PDF pour le groupe `lecture`
- la reouverture tracee des dossiers encore modifiables

## Structure fonctionnelle

- `frontend/index.html` : tableau de bord
- `frontend/form.html` : dossier
- `frontend/restitution.html` : restitution
- `frontend/admin.html` : administration centralisee
- `frontend/logs.html` : journal
- `frontend/trash.html` : corbeille

## Point notable

Le role `lecture` est defini comme un role de consultation seule avec export PDF autorise, mais sans restitution ni modification.
