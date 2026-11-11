# Rôles et droits

Les rôles sont **cumulatifs** : chacun hérite des droits des rôles précédents. Les droits sont vérifiés par le serveur sur chaque requête ; l'interface ne fait que les refléter.

| Capacité | Consultation | Chargé d'études | Responsable | Administrateur |
| --- | :---: | :---: | :---: | :---: |
| Consulter fiches communes, atlas, veille, scénarios, registre | ✔ | ✔ | ✔ | ✔ |
| Obtenir une proposition d'implantation, évaluer des sites | ✔ | ✔ | ✔ | ✔ |
| Lancer une analyse satellitaire, synchroniser les données ouvertes | | ✔ | ✔ | ✔ |
| Ajouter des équipements, corriger ceux des données ouvertes (position, capacité, statut) | | ✔ | ✔ | ✔ |
| Exporter la liste Recensement Éclaireur (export tracé) | | ✔ | ✔ | ✔ |
| Juger des carreaux dans l'écran Validation | | ✔ | ✔ | ✔ |
| Enregistrer, modifier, supprimer un scénario non validé ; préparer un document | | ✔ | ✔ | ✔ |
| Saisir l'hypothèse de population de la commune | | | ✔ | ✔ |
| Valider / archiver un scénario ; **émettre et signer** un document | | | ✔ | ✔ |
| Consulter et vérifier le journal d'audit | | | ✔ | ✔ |
| Comptes, paramètres, sources personnalisées, webhook, supervision | | | | ✔ |

Correspondance usuelle : *Consultation* pour les élus et partenaires, *Chargé d'études* pour les services urbanisme / SIG / affaires scolaires, *Responsable* pour la direction (DGS, DST) qui valide et signe.
