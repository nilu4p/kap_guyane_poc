# Analyses et données

- **Communes** : date de la dernière analyse satellitaire, progression en direct d'une analyse en cours (étapes : repérage des zones habitées, WSF 2019, WSF Evolution, saisons Sentinel-2 une par une, fusion, bâtiments, routes, aires protégées, veille), **qualité** (note, concordance, corrélation). **Analyser / Mettre à jour** (Chargé d'études) : quelques minutes ; une seule analyse par commune à la fois.
- **Données ouvertes** : chaque jeu de données (INSEE, Éducation nationale), nombre de valeurs, date de récupération ; **Synchroniser** lance une mise à jour complète (communes, statistiques, établissements scolaires, équipements OpenStreetMap). Synchronisation automatique selon le paramètre `data_refresh_days`.
- **Journal des traitements** : chaque analyse et synchronisation, son auteur, son statut et son dernier message.

Les fins d'analyse et les échecs sont notifiés sur **#analyses**, les synchronisations sur **#donnees**.
