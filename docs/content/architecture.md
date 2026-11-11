# Architecture

```text
 console (nginx, HTTPS) ──► backend (FastAPI) ──► postgres (PostgreSQL 16)
        │  /docs/ ─► docs        │      ▲
        │  /notifs/ ─► notif-sink▼      │
                              redis (état partagé, verrous, broker Celery)
                                 ▲
     worker (santé des sources, audit horaire, synchronisation, notifications)
     worker-analysis (analyses satellitaires, synchronisations — une à la fois)
     beat (planificateur)
```

| Service | Rôle |
| --- | --- |
| `backend` | API : authentification, territoire, grille, décision, rapports ; migre la base au démarrage, charge l'instantané hors ligne |
| `postgres` | communes, indicateurs, équipements, couches de la grille, analyses, scénarios, documents signés, audit |
| `redis` | santé des sources, verrous (une analyse par commune), limitation de débit, broker |
| `worker-analysis` | analyses de commune : lectures WSF, Sentinel-2 (lectures parallèles par plages HTTP), fusion ; processus renouvelé après chaque tâche (mémoire GDAL) |
| `worker`, `beat` | tâches périodiques et livraison des notifications |
| `console`, `docs`, `notif-sink`, `certbot` | interface, base de connaissances, notifications de démonstration, certificat |

**Mode simple** (développement) : sans `DATABASE_URL` ni `REDIS_URL`, tout tourne dans un seul processus sur SQLite ; les analyses s'exécutent dans un fil d'arrière-plan.

## Organisation du code (backend)

| Paquet | Contenu |
| --- | --- |
| `app/sources/` | connecteurs : geo.api.gouv.fr, Melodi, Éducation nationale, OSM, WSF, empreintes, WDPA, Sentinel-2 (tuiles), sources personnalisées |
| `app/territoire/` | communes, indicateurs, profils, équipements, synchronisation, instantané |
| `app/analyse/` | grille, satellite, fusion du bâti, population, accessibilité / implantation, veille, analyses |
| `app/services/` | notifications, paramètres, planificateur, supervision, catalogue, scénarios, rapports signés |
| `app/core/` | identité, sessions, audit chaîné, coffre chiffré, PKI, sauvegardes |
