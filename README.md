# KAP Guyane — GEOINT multi-sources et aide à la décision territoriale

Plateforme d'aide à la décision pour les **22 communes de Guyane** : où implanter les écoles, les équipements de santé, les points d'eau, les commerces alimentaires, les arrêts de transport et les services publics, à partir de la **fusion** des statistiques officielles, des équipements recensés et de la **croissance du bâti mesurée par satellite**, sur une **grille de 200 m**.

Elle s'appuie sur un socle applicatif complet (FastAPI, PostgreSQL / SQLite, Redis + Celery, console React / Leaflet, IAM, audit chaîné, coffre chiffré, PKI, sauvegardes, déploiement Docker durci, documentation MkDocs) au service du métier territorial décrit dans le dossier *« Pouls des Quartiers »* (pilote : Saint-Laurent-du-Maroni).

> **Pitch** — KAP Guyane montre à chaque maire, carreau par carreau, où sa population a réellement grandi depuis le dernier recensement grâce aux satellites du CNES et de Copernicus, pour décider où ouvrir la prochaine école et quels quartiers signaler à l'INSEE, **sans jamais désigner une seule maison**.

## Socle commun

La console repose sur un socle réutilisable par d'autres plateformes de la même famille : **le même front** (charte graphique, bandeau, navigation desktop et tiroir mobile ☰, connexion, audit, comptes, sources personnalisées, impression) et **le même socle de sécurité** (verrouillage atomique des comptes, adresse client lue de droite à gauche derrière le proxy, cookie de session `__Host-` en HTTPS, CSRF, sonde de session par rôle pour `/docs/` et `/notifs/`, limitation des connexions dès nginx, CSP sans ressource tierce — polices IBM Plex auto-hébergées —, `Permissions-Policy` restrictive, anti-SSRF et anti-*DNS rebinding* des sources personnalisées, tuiles limitées au territoire, audit chaîné vérifié par lots).

- Fichiers du socle commun et règles d'évolution : `frontend/SHARED.md` ; seule l'identité diffère (`frontend/src/platform.js`).
- `make shared-check OTHER=../<projet>` vérifie que ces fichiers sont identiques dans un projet voisin.
- `backend/tests/test_shared_core.py` teste ce socle côté API.

## Ce que fait la plateforme

| Brique | Détail |
| --- | --- |
| **Statistiques réelles des 22 communes** | INSEE Melodi (populations 1968-2023, naissances, âges, scolarisation, logement DOM : électricité, eau, assainissement, habitat précaire ; activité et chômage ; BPE : médecins, pharmacies, commerces, services…), Éducation nationale (écoles, effectifs et classes depuis 2009), **FINESS** (établissements de santé) → **46 indicateurs** comparés à la Guyane et classés |
| **Bâti par satellite 1985 → aujourd'hui** | fusion **WSF Evolution** (Landsat 30 m), **WSF 2019** (10 m, référence) et d'une **série Sentinel-2** de saison sèche calculée par la plateforme (NDBI − NDVI, masques SCL + MNDWI, calibration sur WSF 2019, harmonisation pseudo-invariante, seuil de bruit, régression isotone, garde-fou qualité) |
| **Population par carreau** | population légale INSEE répartie sur le bâti (modèle dasymétrique calibré par quartier IRIS, sinon par commune), prolongée à occupation constante ; enfants par tranche d'âge ; hypothèse communale explicite |
| **Accessibilité** | distance de chaque carreau habité à l'équipement le plus proche (9 familles), trajet estimé (vol d'oiseau × détour) au rayon de la norme locale, **places** des écoles et saturation |
| **Aide à l'implantation** | couverture maximale gloutonne sous contraintes (eau, place, route OSM, protection WDPA stricte / encadrée, résumé cadastral), « pourquoi ici », classes nécessaires, scénarios validés **figés** |
| **Veille** | quartiers en croissance loin des équipements ; **Recensement Éclaireur** : carreaux à signaler à l'INSEE (RIL), règle de secret appliquée aussi à l'écran ; **validation visuelle** à l'aveugle sur 50 carreaux |
| **Documents signés** | diagnostic de commune, dossier d'implantation, liste RIL : figés, hachés (SHA-256), signés (ECDSA), vérifiables |
| **Éthique dès la conception** | agrégation 200 m imposée par le code, aucune emprise conservée, aucune distinction légal / illégal, exports tracés, charte affichée |

Toutes les sources intégrées sont **ouvertes et sans clé**. Un **instantané hors ligne** réel (statistiques, équipements, analyses satellitaires de 9 communes) est embarqué, avec son empreinte SHA-256 vérifiée au chargement : la plateforme se démontre sans réseau.

## Démarrage

```bash
make up                          # construit et démarre (secrets générés dans secrets/)
make admin-password              # mot de passe temporaire du premier administrateur
# https://localhost → admin → nouveau mot de passe → Administration › Utilisateurs
make sync                        # met à jour les données ouvertes (~1 min)
make analyse COMMUNE=97311       # analyse satellitaire d'une commune (quelques minutes)
```

Développement hors Docker : `make venv`, `make dev` (uvicorn :8000 + Vite :5173), `make test`.

## Architecture

| Service | Rôle |
| --- | --- |
| `backend` | API FastAPI : territoire, grille, analyses, décision, rapports, IAM, audit |
| `postgres` | PostgreSQL 16 (SQLite en mode simple) |
| `redis` | état partagé, verrous, broker Celery |
| `worker-analysis` | analyses satellitaires et synchronisations (une à la fois) |
| `worker`, `beat` | santé des sources, audit horaire, synchronisation automatique, notifications |
| `console` | nginx + React (HTTPS, CSP stricte) |
| `docs` | base de connaissances MkDocs (`/docs/`, connexion exigée) |
| `notif-sink` | serveur de notifications de démonstration (`/notifs/`) |

```text
backend/app/
  sources/     geo.api.gouv.fr · INSEE Melodi · Éducation nationale · OSM Overpass · DLR WSF · Microsoft footprints · WDPA · Sentinel-2
  territoire/  communes · indicateurs · profils (46 KPI) · équipements · synchronisation · instantané hors ligne
  analyse/     grille 200 m · satellite · fusion du bâti · population · accessibilité / implantation · veille · analyses
  services/    notifications · paramètres · planificateur · supervision · catalogue · scénarios · rapports signés
  core/        identité · sessions · audit chaîné · coffre · PKI · sauvegardes
frontend/src/views/  Territoire · Commune · Atlas · Décision · Veille · Équipements · Analyses · Validation · Rapports · Charte · Audit · Administration
```

## Résultats sur données réelles (exemple : Saint-Laurent-du-Maroni)

- Population légale INSEE 2023 : **54 429** ; élèves des écoles publiques : **9 988** (2019) → **12 256** (2025).
- Surface bâtie fusionnée : **401 ha** (2019) → **≈ 580 ha** (2025) ; qualité « bonne » (F1 0,67, concordance 79 % avec WSF 2019 sur le voisinage habité).
- Qualité des 9 communes analysées : bonne (Saint-Laurent, Cayenne), moyenne (Matoury, Kourou), faible (Macouria, Mana, Maripasoula, Apatou, Grand-Santi : série Sentinel-2 non appliquée, référence WSF 2019 conservée).
- Le modèle calé sur l'INSEE 2023 retrouve 54 429 habitants en 2023 ; prolongé au rythme du bâti, il donne une population *possible* d'environ 62 000 habitants en 2025 — indicateur indépendant, **pas un contre-recensement**.
- Écoles (rayon 1,5 km de trajet estimé, soit ≈ 1,15 km à vol d'oiseau) : 72 % des enfants de 3-10 ans sont à portée, mais **64,5 %** seulement ont une place (6 écoles saturées, à 25 élèves par classe) ; 3 écoles bien placées portent ce taux à **82,8 %**.
- Population par quartier (IRIS) : de 63 à 116 habitants par hectare bâti selon les quartiers, au lieu d'une moyenne communale.

Ces chiffres dépendent de la dernière synchronisation et de la dernière analyse ; ils sont recalculés à chaque mise à jour.

## Limites connues

- Bâti à 10-20 m : l'habitat diffus sous couvert arboré échappe en partie aux capteurs ; les petits bourgs obtiennent une qualité « faible » (série Sentinel-2 non appliquée, référence WSF 2019 conservée).
- Équipements hors écoles et santé : OpenStreetMap, complétude inégale — à compléter par les services (corrections conservées entre synchronisations).
- Pas d'itinéraire routier (facteur de détour) ; propriété foncière / PPRI (Géorisques à brancher) / réseaux non connus : chaque proposition est un point de départ, à vérifier.
- Validation de référence : contrôle visuel sur Pléiades (SEAS Guyane / DINAMIS) — à organiser avec un ayant droit institutionnel.

Documentation complète : `docs/content/` (servie sur `/docs/`).

## Licence

Distribué sous licence MIT — voir [`LICENSE`](LICENSE).
