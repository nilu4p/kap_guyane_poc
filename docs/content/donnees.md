# Données et sources

Toutes les sources intégrées sont **ouvertes et sans clé**. Le catalogue complet, avec l'état en direct de chaque source et un bouton de test, est dans **Administration → Sources de données**.

## Sources intégrées

| Source | Données | Licence | Fraîcheur |
| --- | --- | --- | --- |
| geo.api.gouv.fr (IGN Admin Express / INSEE) | contours des 22 communes, population légale, surface, EPCI | Licence Ouverte 2.0 | cache 30 j |
| INSEE — API Melodi | populations municipales 1968-2023 ; naissances et décès ; âges, scolarisation, logements DOM, activité (recensement 2012 / 2017 / 2023) ; BPE | Licence Ouverte 2.0 | synchronisation hebdomadaire |
| Éducation nationale (data.education.gouv.fr) | annuaire géolocalisé des écoles, collèges, lycées ; effectifs et classes des écoles publiques depuis 2009 | Licence Ouverte 2.0 | idem |
| FINESS (ministère de la Santé) | hôpitaux, centres et maisons de santé, pharmacies, PMI, laboratoires, dialyse — géolocalisés | Licence Ouverte 2.0 | synchronisation hebdomadaire |
| IGN Géoplateforme + INSEE | contours IRIS et population / âges par IRIS (calibrage par quartier) | Licence Ouverte 2.0 | à chaque analyse |
| IGN API Carto (cadastre) | résumé agrégé des parcelles des sites proposés | Licence Ouverte 2.0 | cache 30 j |
| OpenStreetMap (Overpass) | santé (en complément de FINESS, doublons écartés), eau, commerces alimentaires, transport, services, crèches ; routes | ODbL | idem (routes : 30 j) ; une réponse partielle d'Overpass est refusée |
| DLR — WSF 2019 | surface bâtie 2019, 10 m | CC BY 4.0 | statique |
| DLR — WSF Evolution | année d'urbanisation 1985-2015, 30 m | CC BY 4.0 | statique |
| Copernicus Sentinel-2 L2A (Earth Search, AWS) | composites de saison sèche, imagerie couleur 10 m | Copernicus (libre) | à chaque analyse |
| Microsoft Global ML Building Footprints | nombre de bâtiments par carreau (aucune emprise conservée) | ODbL | cache 90 j |
| WDPA (UNEP-WCMC / UICN) | aires protégées | conditions WDPA | cache 30 j |
| EOX Sentinel-2 cloudless | fonds de carte annuels 2016-2025 | CC BY 4.0 (2016), CC BY-NC-SA 4.0 (2017+) | — |

## Sources à brancher (droits ou compte nécessaires)

| Source | Intérêt | Procédure |
| --- | --- | --- |
| **SEAS Guyane / DINAMIS** — Pléiades, Pléiades Neo (30 cm), SPOT 6-7 | vérité terrain, contrôle visuel des carreaux | ayant droit institutionnel (commune, CTG, université, IRD) ; diffusion publique d'extraits soumise à licence ; branchement WMS/WMTS en source personnalisée |
| CNES GEODES | catalogue national (Sentinel, Pléiades selon droits) | compte GEODES |
| Google Open Buildings 2.5D Temporal | série annuelle 2016-2023 (couverture Guyane à vérifier) | export Earth Engine |
| Géorisques (PPR) | zones inondables et de mouvement de terrain | API REST / WMS (non joignable depuis l'environnement de développement : à brancher) |
| IGN BD TOPO, OCS GE | bâtiments, routes, occupation du sol | Géoplateforme (WMS/WFS) |
| Hydroweb / SWOT | hauteurs du Maroni et de l'Oyapock (module « Fleuve Info ») | compte Theia |

## Sources exclues ou indisponibles

- **Fichiers fonciers MAJIC** (DGFiP) : volontairement exclus — données personnelles, risque d'usage fiscal ou individuel contraire à la charte.
- **FiLoSoFi** (revenus) : non diffusé pour les communes de Guyane.

## Fonctionnement hors ligne

`backend/app/reference/` contient les contours des communes et un **instantané** des statistiques, des équipements et des analyses satellitaires agrégées (dates à l'intérieur), accompagné de son empreinte SHA-256 (`snapshot_973.json.gz.sha256`). Une instance neuve le charge au premier démarrage **seulement si l'empreinte correspond** (sinon refus, tracé dans l'audit) ; la première synchronisation le remplace. `make snapshot` régénère les deux fichiers.

## Robustesse des synchronisations

- Une réponse **partielle** d'Overpass (dépassement de délai) est refusée : les équipements en base restent inchangés.
- Une synchronisation ne peut pas supprimer plus de 30 % des équipements d'une source d'un coup : au-delà, les suppressions sont retenues et le rapport le signale.
- Les **corrections locales** des équipements issus des données ouvertes (position, capacité, statut, note) sont conservées à part et réappliquées après chaque synchronisation.
