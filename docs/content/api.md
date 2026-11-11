# API

API REST JSON sous `/api/v1`, authentifiée par la session de la console (cookie `kap_session` HttpOnly) et protégée contre la falsification de requêtes (en-tête `X-CSRF-Token` sur toute écriture). Documentation interactive : `http://127.0.0.1:8000/docs` en environnement de développement.

| Domaine | Points d'entrée principaux |
| --- | --- |
| Authentification | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/password` |
| Territoire | `GET /communes`, `GET /communes/{code}`, `GET /communes/{code}/contour`, `GET /territoire/kpis`, `PUT/DELETE /communes/{code}/hypothese`, `GET /donnees`, `POST /donnees/sync` |
| Équipements | `GET /equipements`, `GET /equipements/categories`, `POST /equipements`, `PUT/DELETE /equipements/{id}` |
| Analyses | `POST /analyses`, `GET /analyses`, `GET /analyses/{id}` |
| Grille | `GET /grille/{code}/meta`, `GET /grille/{code}/couche?layer=…&year=…`, `GET /grille/{code}/carreau/{cellule}`, `GET /grille/{code}/veille`, `GET /grille/{code}/recensement[?format=csv]`, `GET /grille/{code}/contraintes` |
| Validation | `GET /validation/{code}?year=…` (échantillon, sans la réponse de la plateforme), `POST /validation/{code}` (vote ; renvoie la réponse de la plateforme) |
| Décision | `POST /decision/implantation`, `POST /decision/evaluer`, `GET /decision/acces`, `GET/POST /scenarios`, `PUT/DELETE /scenarios/{id}`, `POST /scenarios/{id}/statut` |
| Rapports | `GET /rapports`, `POST /rapports/projet`, `POST /rapports/emettre`, `GET /rapports/{id}`, `POST /rapports/{id}/verifier`, `GET /rapports/{id}/export`, `GET /rapports/certificat` (certificat racine PEM, en-tête `X-Root-Fingerprint-SHA256`) |
| Imagerie | `GET /imagery/layers`, `GET /imagery/sentinel2/scenes?commune=…`, `GET /imagery/sentinel2/tiles/{scène}/{z}/{x}/{y}.png` |
| Administration | `GET/PUT /settings/keys`, `POST /settings/keys/test/{service}`, `GET/PUT /system/settings`, `GET /system/health`, `GET /system/supervision`, `GET /system/catalogue`, `GET /system/ethique`, `/users`, `/audit`, `/custom-sources` |

**Format des couches de la grille** : `{"grid": {"lat0", "lon0", "dlat", "dlon", "cell_m": 200}, "fields": [...], "cells": [[ligne, colonne, valeur, …], …]}` — le carreau `ligne, colonne` couvre `[lat0 + ligne·dlat, lat0 + (ligne+1)·dlat] × [lon0 + colonne·dlon, …]`. Aucune géométrie plus fine que le carreau n'est servie.
